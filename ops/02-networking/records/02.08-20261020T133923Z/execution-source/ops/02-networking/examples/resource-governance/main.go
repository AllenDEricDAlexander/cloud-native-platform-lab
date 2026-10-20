// 有界 CPU/内存/空卷实验及 02.09/10 通信探测；不读取 token 或代理环境变量。
package main

import (
	"bufio"
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"net"
	"net/http"
	"net/http/httptrace"
	"os"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

var requests sync.Map
var requestKeys atomic.Int32

func handler(w http.ResponseWriter, r *http.Request) {
	nonce := r.Header.Get("X-Cnpl-Nonce")
	if r.URL.Path == "/counts" {
		value, _ := requests.Load(r.URL.Query().Get("nonce"))
		count := int64(0)
		if value != nil {
			count = value.(*atomic.Int64).Load()
		}
		_ = json.NewEncoder(w).Encode(map[string]any{"count": count})
		return
	}
	if nonce != "" {
		if value, ok := requests.Load(nonce); ok {
			value.(*atomic.Int64).Add(1)
		} else if requestKeys.Add(1) <= 1024 {
			counter := new(atomic.Int64)
			counter.Store(1)
			value, loaded := requests.LoadOrStore(nonce, counter)
			if loaded {
				value.(*atomic.Int64).Add(1)
			}
		}
	}
	if r.URL.Path == "/slow" {
		select {
		case <-r.Context().Done():
			return
		case <-time.After(2 * time.Second):
		}
	}
	w.Header().Set("Content-Type", "application/json")
	if r.URL.Path == "/fail" {
		w.WriteHeader(503)
	}
	_ = json.NewEncoder(w).Encode(map[string]any{"nonce": nonce, "uid": os.Getenv("POD_UID"), "pod": os.Getenv("POD_NAME"), "node": os.Getenv("NODE_NAME"), "path": r.URL.Path, "method": r.Method, "peer": r.RemoteAddr})
}

func serve() error {
	listener, err := net.Listen("tcp4", ":9000")
	if err != nil {
		return err
	}
	defer listener.Close()
	go func() {
		for {
			conn, err := listener.Accept()
			if err != nil {
				return
			}
			go func(c net.Conn) {
				defer c.Close()
				scanner := bufio.NewScanner(c)
				for scanner.Scan() {
					_ = c.SetDeadline(time.Now().Add(15 * time.Second))
					if json.NewEncoder(c).Encode(map[string]string{"nonce": scanner.Text(), "uid": os.Getenv("POD_UID")}) != nil {
						return
					}
				}
			}(conn)
		}
	}()
	return (&http.Server{Addr: ":8080", Handler: http.HandlerFunc(handler), ReadHeaderTimeout: 3 * time.Second}).ListenAndServe()
}

func cpuStats() (map[string]int64, error) {
	out := map[string]int64{}
	raw, err := os.ReadFile("/sys/fs/cgroup/cpu.stat")
	if err != nil {
		return nil, err
	}
	for _, line := range strings.Split(string(raw), "\n") {
		fields := strings.Fields(line)
		if len(fields) == 2 {
			value, _ := strconv.ParseInt(fields[1], 10, 64)
			out[fields[0]] = value
		}
	}
	return out, nil
}

func workload(mode string, n int) error {
	switch mode {
	case "cpu":
		if n < 1 || n > 20 {
			return fmt.Errorf("CPU seconds must be 1..20")
		}
		before, err := cpuStats()
		if err != nil {
			return fmt.Errorf("cgroup v2 cpu.stat: %w", err)
		}
		deadline := time.Now().Add(time.Duration(n) * time.Second)
		value := 0.1
		for time.Now().Before(deadline) {
			for i := 0; i < 1000; i++ {
				value = math.Sqrt(value + 1.1)
			}
		}
		after, err := cpuStats()
		if err != nil {
			return err
		}
		return json.NewEncoder(os.Stdout).Encode(map[string]any{"mode": mode, "before": before, "after": after, "result": value})
	case "memory":
		if n < 1 || n > 256 {
			return fmt.Errorf("memory MiB must be 1..256")
		}
		b := make([]byte, n*1024*1024)
		for i := 0; i < len(b); i += 4096 {
			b[i] = 42
		}
		_ = json.NewEncoder(os.Stdout).Encode(map[string]any{"mode": mode, "allocated": len(b)})
		time.Sleep(120 * time.Second)
		runtime.KeepAlive(b)
		return nil
	case "disk":
		if n < 1 || n > 64 {
			return fmt.Errorf("disk MiB must be 1..64")
		}
		f, err := os.OpenFile("/work/payload", os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0600)
		if err != nil {
			return err
		}
		defer f.Close()
		block := make([]byte, 1024*1024)
		for i := 0; i < n; i++ {
			if _, err = f.Write(block); err != nil {
				return err
			}
		}
		if err = f.Sync(); err != nil {
			return err
		}
		_ = json.NewEncoder(os.Stdout).Encode(map[string]any{"mode": mode, "bytes": n * len(block)})
		time.Sleep(180 * time.Second)
		return nil
	}
	return fmt.Errorf("unknown workload")
}

type request struct {
	Target  string `json:"target"`
	Nonce   string `json:"nonce"`
	Method  string `json:"method"`
	CA      string `json:"ca"`
	Timeout int    `json:"timeout_ms"`
}

func probe() error {
	var p request
	if err := json.NewDecoder(io.LimitReader(os.Stdin, 8192)).Decode(&p); err != nil {
		return err
	}
	if p.Timeout < 100 || p.Timeout > 15000 || len(p.Nonce) < 8 || len(p.Nonce) > 80 {
		return fmt.Errorf("invalid probe")
	}
	start := time.Now()
	result := map[string]any{"nonce": p.Nonce, "target": p.Target, "at": start.UTC().Format(time.RFC3339Nano)}
	transport := &http.Transport{Proxy: nil, DisableKeepAlives: true}
	defer transport.CloseIdleConnections()
	if p.CA != "" {
		data, err := os.ReadFile(p.CA)
		if err != nil {
			return err
		}
		pool := x509.NewCertPool()
		if !pool.AppendCertsFromPEM(data) {
			return fmt.Errorf("invalid CA")
		}
		transport.TLSClientConfig = &tls.Config{RootCAs: pool, MinVersion: tls.VersionTLS12}
	}
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(p.Timeout)*time.Millisecond)
	defer cancel()
	if p.Method == "" {
		p.Method = "GET"
	}
	req, err := http.NewRequestWithContext(ctx, p.Method, p.Target, nil)
	if err != nil {
		return err
	}
	req.Header.Set("X-Cnpl-Nonce", p.Nonce)
	req = req.WithContext(httptrace.WithClientTrace(ctx, &httptrace.ClientTrace{GotConn: func(info httptrace.GotConnInfo) {
		result["local"] = info.Conn.LocalAddr().String()
		result["remote"] = info.Conn.RemoteAddr().String()
	}}))
	response, err := (&http.Client{Transport: transport, CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse }}).Do(req)
	if err != nil {
		result["error"] = err.Error()
	} else {
		defer response.Body.Close()
		body, readErr := io.ReadAll(io.LimitReader(response.Body, 16385))
		if readErr != nil {
			return readErr
		}
		if len(body) > 16384 {
			return fmt.Errorf("response too large")
		}
		result["status"] = response.StatusCode
		result["body"] = string(body)
	}
	result["elapsed_ms"] = time.Since(start).Milliseconds()
	if os.Getenv("CNPL_ARP_PROBE") == "true" {
		if arp, readErr := os.ReadFile("/proc/net/arp"); readErr == nil {
			result["arp"] = string(arp)
		} else {
			result["arp_error"] = readErr.Error()
		}
	}
	return json.NewEncoder(os.Stdout).Encode(result)
}

func stream(target string, seconds int) error {
	if seconds < 1 || seconds > 1200 {
		return fmt.Errorf("stream seconds must be 1..1200")
	}
	var conn net.Conn
	defer func() {
		if conn != nil {
			_ = conn.Close()
		}
	}()
	deadline := time.Now().Add(time.Duration(seconds) * time.Second)
	for seq := 0; time.Now().Before(deadline); seq++ {
		nonce := fmt.Sprintf("stream-%d-%d", time.Now().UnixNano(), seq)
		row := map[string]any{"at": time.Now().UTC().Format(time.RFC3339Nano), "nonce": nonce, "seq": seq}
		var err error
		if conn == nil {
			conn, err = net.DialTimeout("tcp4", target, 2*time.Second)
			row["new_connection"] = true
		}
		if err == nil {
			_ = conn.SetDeadline(time.Now().Add(2 * time.Second))
			_, err = fmt.Fprintln(conn, nonce)
		}
		if err == nil {
			var echo map[string]string
			err = json.NewDecoder(conn).Decode(&echo)
			if err == nil && (echo["nonce"] != nonce || echo["uid"] == "") {
				err = fmt.Errorf("invalid echo")
			}
			row["backend"] = echo
		}
		if err != nil {
			row["error"] = err.Error()
			if conn != nil {
				_ = conn.Close()
				conn = nil
			}
		}
		if err = json.NewEncoder(os.Stdout).Encode(row); err != nil {
			return err
		}
		time.Sleep(time.Second)
	}
	return nil
}

func main() {
	var err error
	if len(os.Args) < 2 {
		err = fmt.Errorf("usage: phase-lab serve|probe|cpu|memory|disk|stream")
	} else {
		switch os.Args[1] {
		case "serve":
			err = serve()
		case "probe":
			err = probe()
		case "cpu", "memory", "disk":
			n := 0
			if len(os.Args) == 3 {
				n, err = strconv.Atoi(os.Args[2])
			}
			if err == nil {
				err = workload(os.Args[1], n)
			}
		case "stream":
			n := 0
			if len(os.Args) == 4 {
				n, err = strconv.Atoi(os.Args[3])
			} else {
				err = fmt.Errorf("stream target seconds")
			}
			if err == nil {
				err = stream(os.Args[2], n)
			}
		default:
			err = fmt.Errorf("unknown mode")
		}
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
