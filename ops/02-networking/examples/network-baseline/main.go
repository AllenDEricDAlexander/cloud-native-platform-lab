// 02.01 的有界 HTTP/UDP/DNS 探测；只使用标准库，不需要特权或主机挂载。
package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptrace"
	"os"
	"os/signal"
	"sort"
	"strconv"
	"strings"
	"syscall"
	"time"
)

type echo struct {
	Node   string `json:"node"`
	Pod    string `json:"pod"`
	Peer   string `json:"peer"`
	Bytes  int    `json:"bytes"`
	SHA256 string `json:"sha256"`
}

func digest(b []byte) string {
	s := sha256.Sum256(b)
	return hex.EncodeToString(s[:])
}

func response(peer string, b []byte) echo {
	return echo{os.Getenv("NODE_NAME"), os.Getenv("POD_NAME"), peer, len(b), digest(b)}
}

func handler(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path == "/delay" {
		select {
		case <-r.Context().Done():
			return
		case <-time.After(3 * time.Second):
		}
	}
	b, err := io.ReadAll(http.MaxBytesReader(w, r.Body, 256*1024))
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(response(r.RemoteAddr, b))
}

func serve() error {
	udp, err := net.ListenPacket("udp4", ":9090")
	if err != nil {
		return err
	}
	defer udp.Close()
	go func() {
		b := make([]byte, 8192)
		for {
			n, peer, err := udp.ReadFrom(b)
			if err != nil {
				return
			}
			out, _ := json.Marshal(response(peer.String(), b[:n]))
			_, _ = udp.WriteTo(out, peer)
		}
	}()
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer stop()
	server := &http.Server{Addr: ":8080", Handler: http.HandlerFunc(handler), ReadHeaderTimeout: 3 * time.Second}
	go func() {
		<-ctx.Done()
		cancelCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		_ = server.Shutdown(cancelCtx)
	}()
	err = server.ListenAndServe()
	if err == http.ErrServerClosed {
		return nil
	}
	return err
}

type probe struct {
	Name     string `json:"name"`
	Protocol string `json:"protocol"`
	Target   string `json:"target"`
	Expected string `json:"expected"`
	Size     int    `json:"size"`
	Count    int    `json:"count"`
	Timeout  int    `json:"timeout_ms"`
	CA       string `json:"ca"`
}

type result struct {
	Name      string   `json:"name"`
	Protocol  string   `json:"protocol"`
	Target    string   `json:"target"`
	At        string   `json:"at"`
	ElapsedMS float64  `json:"elapsed_ms"`
	Local     string   `json:"local"`
	Status    int      `json:"status"`
	Echo      *echo    `json:"echo,omitempty"`
	Addresses []string `json:"addresses,omitempty"`
	Error     string   `json:"error,omitempty"`
	Passed    bool     `json:"passed"`
}

func httpProbe(p probe, out *result, body []byte) error {
	transport := &http.Transport{Proxy: nil, DisableKeepAlives: true}
	defer transport.CloseIdleConnections()
	if p.CA != "" {
		pem, err := os.ReadFile(p.CA)
		if err != nil {
			return err
		}
		roots := x509.NewCertPool()
		if !roots.AppendCertsFromPEM(pem) {
			return fmt.Errorf("invalid CA")
		}
		transport.TLSClientConfig = &tls.Config{RootCAs: roots, MinVersion: tls.VersionTLS12}
	}
	request, err := http.NewRequest(http.MethodPost, p.Target, bytes.NewReader(body))
	if err != nil {
		return err
	}
	if p.CA != "" {
		request.Method = http.MethodGet
	}
	request = request.WithContext(httptrace.WithClientTrace(request.Context(), &httptrace.ClientTrace{
		GotConn: func(info httptrace.GotConnInfo) { out.Local = info.Conn.LocalAddr().String() },
	}))
	client := &http.Client{Transport: transport, Timeout: time.Duration(p.Timeout) * time.Millisecond,
		CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse }}
	resp, err := client.Do(request)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	out.Status = resp.StatusCode
	if p.CA != "" {
		if resp.StatusCode != 200 && resp.StatusCode != 401 {
			return fmt.Errorf("registry status=%d", resp.StatusCode)
		}
		return nil
	}
	if resp.StatusCode != 200 {
		return fmt.Errorf("HTTP status=%d", resp.StatusCode)
	}
	var value echo
	if err = json.NewDecoder(io.LimitReader(resp.Body, 8192)).Decode(&value); err != nil {
		return err
	}
	out.Echo = &value
	if value.SHA256 != digest(body) || value.Bytes != len(body) || (p.Expected != "" && value.Node != p.Expected) {
		return fmt.Errorf("wrong backend or payload")
	}
	localIP, _, _ := net.SplitHostPort(out.Local)
	peerIP, _, _ := net.SplitHostPort(value.Peer)
	if strings.HasPrefix(p.Name, "pod-") && localIP != peerIP {
		return fmt.Errorf("unexpected Pod-to-Pod SNAT: local=%s peer=%s", localIP, peerIP)
	}
	return nil
}

func udpProbe(p probe, out *result, body []byte) error {
	conn, err := net.DialTimeout("udp4", p.Target, time.Duration(p.Timeout)*time.Millisecond)
	if err != nil {
		return err
	}
	defer conn.Close()
	out.Local = conn.LocalAddr().String()
	_ = conn.SetDeadline(time.Now().Add(time.Duration(p.Timeout) * time.Millisecond))
	if _, err = conn.Write(body); err != nil {
		return err
	}
	buffer := make([]byte, 8192)
	n, err := conn.Read(buffer)
	if err != nil {
		return err
	}
	var value echo
	if err = json.Unmarshal(buffer[:n], &value); err != nil {
		return err
	}
	out.Echo = &value
	if value.Node != p.Expected || value.Bytes != len(body) || value.SHA256 != digest(body) || value.Peer != out.Local {
		return fmt.Errorf("UDP backend, payload or source mismatch")
	}
	return nil
}

func dnsProbe(p probe, out *result) error {
	resolver := &net.Resolver{PreferGo: true, Dial: func(ctx context.Context, _, _ string) (net.Conn, error) {
		return (&net.Dialer{}).DialContext(ctx, strings.TrimPrefix(p.Protocol, "dns-"), "192.168.20.10:53")
	}}
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(p.Timeout)*time.Millisecond)
	defer cancel()
	addresses, err := resolver.LookupHost(ctx, p.Target)
	if err != nil {
		return err
	}
	sort.Strings(addresses)
	out.Addresses = addresses
	if p.Expected != "" {
		for _, address := range addresses {
			if address == p.Expected {
				return nil
			}
		}
		return fmt.Errorf("missing DNS address %s", p.Expected)
	}
	return nil
}

func matrix() error {
	var probes []probe
	if err := json.NewDecoder(io.LimitReader(os.Stdin, 1024*1024)).Decode(&probes); err != nil {
		return err
	}
	failed := false
	for _, p := range probes {
		if p.Count < 1 || p.Count > 20 || p.Size < 0 || p.Size > 128*1024 || p.Timeout < 100 || p.Timeout > 10000 {
			return fmt.Errorf("invalid probe bounds")
		}
		body := bytes.Repeat([]byte("x"), p.Size)
		for i := 0; i < p.Count; i++ {
			start := time.Now()
			out := result{Name: p.Name, Protocol: p.Protocol, Target: p.Target, At: start.UTC().Format(time.RFC3339Nano)}
			var err error
			switch p.Protocol {
			case "http":
				err = httpProbe(p, &out, body)
			case "udp":
				err = udpProbe(p, &out, body)
			case "dns-udp", "dns-tcp":
				err = dnsProbe(p, &out)
			default:
				return fmt.Errorf("unknown protocol %s", p.Protocol)
			}
			out.ElapsedMS = float64(time.Since(start).Microseconds()) / 1000
			out.Passed = err == nil
			if err != nil {
				out.Error = err.Error()
				if e, ok := err.(net.Error); ok && e.Timeout() && p.Expected == "timeout" {
					out.Passed = true
				}
			}
			if err == nil && p.Expected == "timeout" {
				out.Passed = false
				out.Error = "expected timeout but request succeeded"
			}
			failed = failed || !out.Passed
			_ = json.NewEncoder(os.Stdout).Encode(out)
		}
	}
	if failed {
		return fmt.Errorf("one or more probes failed")
	}
	return nil
}

func main() {
	var err error
	if len(os.Args) != 2 {
		err = fmt.Errorf("usage: /net-lab serve|matrix|info")
	} else {
		switch os.Args[1] {
		case "serve":
			err = serve()
		case "matrix":
			err = matrix()
		case "info":
			interfaces, e := net.Interfaces()
			err = e
			routes, _ := os.ReadFile("/proc/net/route")
			dns, _ := os.ReadFile("/etc/resolv.conf")
			_ = json.NewEncoder(os.Stdout).Encode(map[string]any{"interfaces": interfaces, "routes": string(routes), "resolv_conf": string(dns)})
		default:
			err = fmt.Errorf("unknown mode %s", strconv.Quote(os.Args[1]))
		}
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
