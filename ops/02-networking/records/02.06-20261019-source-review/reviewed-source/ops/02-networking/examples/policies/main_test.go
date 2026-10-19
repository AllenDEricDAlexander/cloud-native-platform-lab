package main

import (
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func testProbe(target string) probe {
	return probe{Protocol: "http", Target: target, Nonce: "unit-test-nonce", Timeout: 1000}
}

func TestEchoIdentity(t *testing.T) {
	t.Setenv("POD_UID", "test-uid")
	server := httptest.NewServer(http.HandlerFunc(handler))
	defer server.Close()
	p := testProbe(server.URL + "/allowed")
	p.Method = "POST"
	out, err := run(p)
	if err != nil || out.Error != "" || out.Status != 200 {
		t.Fatalf("%+v %v", out, err)
	}
	var body map[string]string
	if err = json.Unmarshal([]byte(out.Body), &body); err != nil {
		t.Fatal(err)
	}
	if body["nonce"] != p.Nonce || body["uid"] != "test-uid" || body["path"] != "/allowed" || body["method"] != "POST" || out.Local == "" || out.Remote == "" {
		t.Fatalf("%+v %+v", out, body)
	}
}

func TestExplicitProxyOverridesEnvironment(t *testing.T) {
	var calls atomic.Int32
	proxy := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls.Add(1)
		if r.URL.Host != "public.invalid" {
			t.Errorf("target=%s", r.URL)
		}
		w.WriteHeader(204)
	}))
	defer proxy.Close()
	t.Setenv("HTTP_PROXY", "http://127.0.0.1:1")
	t.Setenv("HTTPS_PROXY", "http://127.0.0.1:1")
	t.Setenv("NO_PROXY", "*")
	p := testProbe("http://public.invalid/generate_204")
	p.Proxy = proxy.URL
	out, err := run(p)
	if err != nil || out.Error != "" || out.Status != 204 || calls.Load() != 1 {
		t.Fatalf("%+v %v", out, err)
	}
	// 未指定代理时只使用目标直连；错误的环境代理不会接管请求。
	direct := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(204) }))
	defer direct.Close()
	out, err = run(testProbe(direct.URL))
	if err != nil || out.Error != "" || out.Status != 204 || calls.Load() != 1 {
		t.Fatalf("%+v %v", out, err)
	}
}

func trustedCA(t *testing.T, s *httptest.Server) string {
	t.Helper()
	cert, err := x509.ParseCertificate(s.TLS.Certificates[0].Certificate[0])
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(t.TempDir(), "root.crt")
	if err = os.WriteFile(path, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: cert.Raw}), 0600); err != nil {
		t.Fatal(err)
	}
	return path
}

func TestTLSVerificationAndConnectProxy(t *testing.T) {
	backend := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(204) }))
	defer backend.Close()
	p := testProbe(backend.URL)
	out, err := run(p)
	if err != nil || out.Error == "" || out.Status != 0 {
		t.Fatalf("untrusted server accepted: %+v %v", out, err)
	}
	p.CA = trustedCA(t, backend)
	out, err = run(p)
	if err != nil || out.Error != "" || out.Status != 204 {
		t.Fatalf("trusted TLS failed: %+v %v", out, err)
	}
	var connects atomic.Int32
	proxy := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != "CONNECT" || r.Host != strings.TrimPrefix(backend.URL, "https://") {
			t.Errorf("bad CONNECT %s %s", r.Method, r.Host)
			http.Error(w, "bad CONNECT", 400)
			return
		}
		up, err := net.Dial("tcp", r.Host)
		if err != nil {
			http.Error(w, "connect", 502)
			return
		}
		conn, _, err := w.(http.Hijacker).Hijack()
		if err != nil {
			_ = up.Close()
			return
		}
		connects.Add(1)
		_, _ = conn.Write([]byte("HTTP/1.1 200 Connection Established\r\n\r\n"))
		go func() { defer conn.Close(); defer up.Close(); _, _ = io.Copy(up, conn) }()
		_, _ = io.Copy(conn, up)
		_ = conn.Close()
		_ = up.Close()
	}))
	defer proxy.Close()
	p.Proxy = proxy.URL
	out, err = run(p)
	if err != nil || out.Error != "" || out.Status != 204 || connects.Load() != 1 {
		t.Fatalf("CONNECT TLS failed: %+v %v", out, err)
	}
}

func TestBoundedFailureIsEvidenceNotCommandFailure(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { <-r.Context().Done() }))
	defer server.Close()
	p := testProbe(server.URL)
	p.Timeout = 100
	start := time.Now()
	out, err := run(p)
	if err != nil || !out.Timeout || out.Error == "" || time.Since(start) > time.Second {
		t.Fatalf("%+v %v", out, err)
	}
	listener, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	address := listener.Addr().String()
	_ = listener.Close()
	p.Protocol = "tcp"
	p.Target = address
	out, err = run(p)
	if err != nil || out.Error == "" || out.Timeout {
		t.Fatalf("refusal must not be a policy timeout: %+v %v", out, err)
	}
	p.Protocol = "unknown"
	if _, err = run(p); err == nil {
		t.Fatal("unknown protocol accepted")
	}
	p.Protocol = "http"
	p.Timeout = 0
	if _, err = run(p); err == nil {
		t.Fatal("unbounded probe accepted")
	}
}
