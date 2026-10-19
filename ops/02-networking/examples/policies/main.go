// 02.06 有界探测器与回显服务；不读取代理环境变量，不使用特权或集群凭据。
package main

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptrace"
	"net/url"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"
)

type probe struct {
	Protocol string `json:"protocol"`
	Target   string `json:"target"`
	Method   string `json:"method"`
	Proxy    string `json:"proxy"`
	CA       string `json:"ca"`
	Nonce    string `json:"nonce"`
	Timeout  int    `json:"timeout_ms"`
}

type result struct {
	Protocol  string   `json:"protocol"`
	Target    string   `json:"target"`
	Nonce     string   `json:"nonce"`
	At        string   `json:"at"`
	ElapsedMS int64    `json:"elapsed_ms"`
	Local     string   `json:"local,omitempty"`
	Remote    string   `json:"remote,omitempty"`
	Status    int      `json:"status,omitempty"`
	RCode     int      `json:"rcode"`
	Addresses []string `json:"addresses,omitempty"`
	Body      string   `json:"body,omitempty"`
	Error     string   `json:"error,omitempty"`
	Timeout   bool     `json:"timeout"`
}

func resolver() *net.Resolver {
	return &net.Resolver{PreferGo: true, Dial: func(ctx context.Context, _, _ string) (net.Conn, error) {
		return (&net.Dialer{}).DialContext(ctx, "udp", "192.168.20.10:53")
	}}
}

// DNS 只查询 A，显式保留 RCODE，避免把拒绝、NXDOMAIN、超时混成同一个结果。
func dns(ctx context.Context, p probe, out *result) error {
	if len(p.Target) > 253 {
		return fmt.Errorf("DNS name too long")
	}
	wire := []byte{0x26, 0x06, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0}
	for _, label := range strings.Split(strings.TrimSuffix(p.Target, "."), ".") {
		if len(label) == 0 || len(label) > 63 {
			return fmt.Errorf("invalid DNS label")
		}
		wire = append(wire, byte(len(label)))
		wire = append(wire, []byte(label)...)
	}
	wire = append(wire, 0, 0, 1, 0, 1)
	network := strings.TrimPrefix(p.Protocol, "dns-")
	c, err := (&net.Dialer{}).DialContext(ctx, network, "192.168.20.10:53")
	if err != nil {
		return err
	}
	defer c.Close()
	out.Local, out.Remote = c.LocalAddr().String(), c.RemoteAddr().String()
	deadline, _ := ctx.Deadline()
	_ = c.SetDeadline(deadline)
	if network == "tcp" {
		wire = append([]byte{byte(len(wire) >> 8), byte(len(wire))}, wire...)
	}
	if _, err = c.Write(wire); err != nil {
		return err
	}
	buf := make([]byte, 4096)
	n := 0
	if network == "tcp" {
		if _, err = io.ReadFull(c, buf[:2]); err != nil {
			return err
		}
		n = int(binary.BigEndian.Uint16(buf[:2]))
		if n > len(buf) {
			return fmt.Errorf("DNS frame too big")
		}
		_, err = io.ReadFull(c, buf[:n])
	} else {
		n, err = c.Read(buf)
	}
	if err != nil {
		return err
	}
	buf = buf[:n]
	if n < 12 || binary.BigEndian.Uint16(buf[:2]) != 0x2606 || buf[2]&0x80 == 0 {
		return fmt.Errorf("invalid DNS response")
	}
	out.RCode = int(buf[3] & 15)
	skipName := func(offset int) (int, error) {
		for offset < len(buf) {
			v := int(buf[offset])
			offset++
			if v == 0 {
				return offset, nil
			}
			if v&192 == 192 {
				if offset >= len(buf) {
					break
				}
				return offset + 1, nil
			}
			if v > 63 || offset+v > len(buf) {
				break
			}
			offset += v
		}
		return 0, fmt.Errorf("truncated DNS name")
	}
	offset := 12
	for i := 0; i < int(binary.BigEndian.Uint16(buf[4:6])); i++ {
		offset, err = skipName(offset)
		if err != nil {
			return err
		}
		offset += 4
		if offset > n {
			return fmt.Errorf("truncated DNS question")
		}
	}
	for i := 0; i < int(binary.BigEndian.Uint16(buf[6:8])); i++ {
		offset, err = skipName(offset)
		if err != nil {
			return err
		}
		if offset+10 > n {
			return fmt.Errorf("truncated DNS answer")
		}
		typ := binary.BigEndian.Uint16(buf[offset : offset+2])
		size := int(binary.BigEndian.Uint16(buf[offset+8 : offset+10]))
		offset += 10
		if offset+size > n {
			return fmt.Errorf("truncated DNS data")
		}
		if typ == 1 && size == 4 {
			out.Addresses = append(out.Addresses, net.IP(buf[offset:offset+4]).String())
		}
		offset += size
	}
	return nil
}

func run(p probe) (result, error) {
	out := result{Protocol: p.Protocol, Target: p.Target, Nonce: p.Nonce, At: time.Now().UTC().Format(time.RFC3339Nano), RCode: -1}
	if p.Timeout < 100 || p.Timeout > 15000 || len(p.Nonce) < 8 || len(p.Nonce) > 80 {
		return out, fmt.Errorf("invalid probe bounds")
	}
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(p.Timeout)*time.Millisecond)
	defer cancel()
	dialer := &net.Dialer{Resolver: resolver()}
	start := time.Now()
	var err error
	switch p.Protocol {
	case "dns-udp", "dns-tcp":
		err = dns(ctx, p, &out)
	case "tcp":
		var c net.Conn
		c, err = dialer.DialContext(ctx, "tcp4", p.Target)
		if err == nil {
			out.Local, out.Remote = c.LocalAddr().String(), c.RemoteAddr().String()
			_ = c.Close()
		}
	case "http":
		transport := &http.Transport{Proxy: nil, DisableKeepAlives: true, DialContext: dialer.DialContext, ForceAttemptHTTP2: false}
		defer transport.CloseIdleConnections()
		if p.Proxy != "" {
			var proxyURL *url.URL
			proxyURL, err = url.Parse(p.Proxy)
			if err == nil && (proxyURL.Scheme != "http" || proxyURL.User != nil || proxyURL.Host == "") {
				err = fmt.Errorf("invalid explicit proxy")
			}
			if err == nil {
				transport.Proxy = http.ProxyURL(proxyURL)
			}
		}
		if err == nil && p.CA != "" {
			var data []byte
			data, err = os.ReadFile(p.CA)
			if err == nil {
				pool := x509.NewCertPool()
				if !pool.AppendCertsFromPEM(data) {
					err = fmt.Errorf("invalid CA bundle")
				}
				transport.TLSClientConfig = &tls.Config{RootCAs: pool, MinVersion: tls.VersionTLS12}
			}
		}
		if p.Method == "" {
			p.Method = http.MethodGet
		}
		if err == nil {
			var req *http.Request
			req, err = http.NewRequestWithContext(ctx, p.Method, p.Target, nil)
			if err == nil {
				req.Header.Set("X-Cnpl-Nonce", p.Nonce)
				req = req.WithContext(httptrace.WithClientTrace(req.Context(), &httptrace.ClientTrace{GotConn: func(info httptrace.GotConnInfo) {
					out.Local, out.Remote = info.Conn.LocalAddr().String(), info.Conn.RemoteAddr().String()
				}}))
				client := &http.Client{Transport: transport, CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse }}
				var reply *http.Response
				reply, err = client.Do(req)
				if err == nil {
					out.Status = reply.StatusCode
					var data []byte
					data, err = io.ReadAll(io.LimitReader(reply.Body, 8193))
					_ = reply.Body.Close()
					if len(data) > 8192 {
						err = fmt.Errorf("response too large")
					}
					out.Body = string(data)
				}
			}
		}
	default:
		return out, fmt.Errorf("unknown protocol")
	}
	out.ElapsedMS = time.Since(start).Milliseconds()
	if err != nil {
		out.Error = err.Error()
		if e, ok := err.(net.Error); ok {
			out.Timeout = e.Timeout()
		}
	}
	return out, nil
}

func handler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]string{"pod": os.Getenv("POD_NAME"), "uid": os.Getenv("POD_UID"), "node": os.Getenv("NODE_NAME"), "peer": r.RemoteAddr, "nonce": r.Header.Get("X-Cnpl-Nonce"), "path": r.URL.Path, "method": r.Method})
}

func serve() error {
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer stop()
	errors := make(chan error, 2)
	for _, address := range []string{":8080", ":9090"} {
		server := &http.Server{Addr: address, Handler: http.HandlerFunc(handler), ReadHeaderTimeout: 3 * time.Second}
		go func() { errors <- server.ListenAndServe() }()
		go func() {
			<-ctx.Done()
			shutdown, cancel := context.WithTimeout(context.Background(), 2*time.Second)
			defer cancel()
			_ = server.Shutdown(shutdown)
		}()
	}
	select {
	case <-ctx.Done():
		return nil
	case err := <-errors:
		if err == http.ErrServerClosed {
			return nil
		}
		return err
	}
}

func main() {
	var err error
	if len(os.Args) != 2 {
		err = fmt.Errorf("usage: policy-lab serve|probe")
	} else if os.Args[1] == "serve" {
		err = serve()
	} else if os.Args[1] == "probe" {
		var p probe
		err = json.NewDecoder(io.LimitReader(os.Stdin, 8192)).Decode(&p)
		if err == nil {
			var out result
			out, err = run(p)
			if err == nil {
				err = json.NewEncoder(os.Stdout).Encode(out)
			}
		}
	} else {
		err = fmt.Errorf("unknown command")
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
