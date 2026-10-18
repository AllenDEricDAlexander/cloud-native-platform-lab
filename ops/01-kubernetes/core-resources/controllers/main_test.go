package main

import (
	"bufio"
	"encoding/json"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

func invoke(a *app, method, target string) *httptest.ResponseRecorder {
	w := httptest.NewRecorder()
	a.ServeHTTP(w, httptest.NewRequest(method, target, nil))
	return w
}
func example(t *testing.T, version string) *app {
	return &app{Version: version, UID: "uid-example", Name: "example", Started: time.Now().Add(-time.Minute), Local: filepath.Join(t.TempDir(), "local")}
}

func TestVersionsAndHealthyProbeDoNotHideBusinessFailure(t *testing.T) {
	for _, version := range []string{"v1", "v2", "bad"} {
		a := example(t, version)
		if invoke(a, "GET", "/ready").Code != 200 {
			t.Fatal("probe should pass", version)
		}
		r := invoke(a, "GET", "/work?id=test")
		expected := 200
		if version == "bad" {
			expected = 500
		}
		if r.Code != expected || !strings.Contains(r.Body.String(), version) {
			t.Fatalf("version=%s result=%s", version, r.Body.String())
		}
	}
}

func TestStartupReadinessAndDrainAreIndependent(t *testing.T) {
	a := example(t, "v1")
	a.Started = time.Now()
	a.Delay = time.Hour
	if invoke(a, "GET", "/startup").Code != 503 {
		t.Fatal("slow startup")
	}
	a.Started = time.Now().Add(-2 * time.Hour)
	a.NotReady = true
	if invoke(a, "GET", "/ready").Code != 503 || invoke(a, "GET", "/live").Code != 200 {
		t.Fatal("readiness must not break liveness")
	}
	a.NotReady = false
	if invoke(a, "GET", "/drain").Code != 405 {
		t.Fatal("GET must not mutate drain")
	}
	if invoke(a, "POST", "/drain").Code != 200 || !a.Draining || a.PreStop.IsZero() {
		t.Fatal("prestop must remove readiness")
	}
	if invoke(a, "GET", "/ready").Code != 503 || invoke(a, "GET", "/work").Code != 200 {
		t.Fatal("propagation window requests should still complete")
	}
}

func TestLocalDataIsFileBackedAndWorkIsBounded(t *testing.T) {
	a := example(t, "v1")
	if invoke(a, "POST", "/local?value=temporary-data").Code != 200 {
		t.Fatal("write local")
	}
	b, err := os.ReadFile(a.Local)
	if err != nil || string(b) != "temporary-data" {
		t.Fatal("not file backed", err)
	}
	if !strings.Contains(invoke(a, "GET", "/local").Body.String(), "temporary-data") {
		t.Fatal("read local")
	}
	if invoke(a, "GET", "/work?seconds=99").Code != 400 || invoke(a, "POST", "/local?value="+strings.Repeat("x", 201)).Code != 400 {
		t.Fatal("unbounded input")
	}
}

type memoryListener struct {
	net.Conn
	once sync.Once
	done chan struct{}
}

func (l *memoryListener) Accept() (net.Conn, error) {
	var c net.Conn
	l.once.Do(func() { c = l.Conn })
	if c != nil {
		return c, nil
	}
	<-l.done
	return nil, net.ErrClosed
}
func (l *memoryListener) Close() error {
	select {
	case <-l.done:
	default:
		close(l.done)
	}
	return nil
}
func (l *memoryListener) Addr() net.Addr { return l.Conn.LocalAddr() }

func TestRelayedLongRequestDrainsAndWritesUIDReceipt(t *testing.T) {
	server, upstream := net.Pipe()
	downstream, client := net.Pipe()
	defer client.Close()
	go forward(downstream, upstream)
	l := &memoryListener{Conn: server, done: make(chan struct{})}
	a := example(t, "v2")
	s := &http.Server{Handler: a}
	go func() { _ = s.Serve(l) }()
	defer s.Close()
	finished := make(chan error, 1)
	go func() {
		_, e := io.WriteString(client, "GET /work?seconds=1&id=scale HTTP/1.1\r\nHost: lab\r\n\r\n")
		if e == nil {
			var r *http.Response
			r, e = http.ReadResponse(bufio.NewReader(client), nil)
			if e == nil {
				var b []byte
				b, e = io.ReadAll(r.Body)
				r.Body.Close()
				if !strings.Contains(string(b), "completed") {
					e = io.ErrUnexpectedEOF
				}
			}
		}
		finished <- e
	}()
	deadline := time.Now().Add(2 * time.Second)
	for {
		a.mu.Lock()
		active := a.Active == 1
		a.mu.Unlock()
		if active {
			break
		}
		if time.Now().After(deadline) {
			t.Fatal("request never entered")
		}
		time.Sleep(time.Millisecond)
	}
	a.mu.Lock()
	a.Term = time.Now()
	a.Draining = true
	a.mu.Unlock()
	path := filepath.Join(t.TempDir(), "receipt")
	if err := a.shutdown(s, path, 3*time.Second); err != nil {
		t.Fatal(err)
	}
	if err := <-finished; err != nil {
		t.Fatal(err)
	}
	b, _ := os.ReadFile(path)
	var receipt map[string]any
	if e := json.Unmarshal(b, &receipt); e != nil || receipt["uid"] != a.UID || receipt["signal"] != "TERM" || receipt["drained"] != true {
		t.Fatalf("bad receipt %s %v", b, e)
	}
}

func TestActiveWorkCannotReportDrainSuccess(t *testing.T) {
	a := example(t, "v1")
	a.Active = 1
	path := filepath.Join(t.TempDir(), "receipt")
	if err := a.shutdown(&http.Server{}, path, time.Millisecond); err != nil {
		t.Fatal(err)
	}
	b, _ := os.ReadFile(path)
	var receipt map[string]any
	_ = json.Unmarshal(b, &receipt)
	if receipt["drained"] != false {
		t.Fatal("active work must not be reported drained")
	}
}

func TestRelayRejectsForeignTargetBeforeListening(t *testing.T) {
	t.Setenv("RELAY_TARGET", "example.com:8080")
	if err := relay(); err == nil {
		t.Fatal("open relay")
	}
}

func TestActualHTTPDrainTimeoutWritesFailure(t *testing.T) {
	server, client := net.Pipe()
	defer client.Close()
	l := &memoryListener{Conn: server, done: make(chan struct{})}
	a := example(t, "v1")
	s := &http.Server{Handler: a}
	go func() { _ = s.Serve(l) }()
	defer s.Close()
	completed := make(chan struct{})
	go func() {
		defer close(completed)
		_, _ = io.WriteString(client, "GET /work?seconds=1 HTTP/1.1\r\nHost: lab\r\n\r\n")
		r, e := http.ReadResponse(bufio.NewReader(client), nil)
		if e == nil {
			_, _ = io.Copy(io.Discard, r.Body)
			r.Body.Close()
		}
	}()
	deadline := time.Now().Add(2 * time.Second)
	for {
		a.mu.Lock()
		active := a.Active == 1
		a.mu.Unlock()
		if active {
			break
		}
		if time.Now().After(deadline) {
			t.Fatal("request did not enter")
		}
		time.Sleep(time.Millisecond)
	}
	path := filepath.Join(t.TempDir(), "receipt")
	if err := a.shutdown(s, path, 20*time.Millisecond); err == nil {
		t.Fatal("expected a real Shutdown deadline")
	}
	b, _ := os.ReadFile(path)
	var receipt map[string]any
	_ = json.Unmarshal(b, &receipt)
	if receipt["drained"] != false {
		t.Fatal("timeout reported success")
	}
	_ = s.Close()
	<-completed
}

type commandTransport func(*http.Request) (*http.Response, error)

func (f commandTransport) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

func TestNativeLocalCommandEscapesValueAndUsesPOST(t *testing.T) {
	originalArgs, originalClient := os.Args, localClient
	defer func() { os.Args = originalArgs; localClient = originalClient }()
	called := false
	localClient = &http.Client{Transport: commandTransport(func(r *http.Request) (*http.Response, error) {
		called = true
		if r.Method != "POST" || r.URL.Host != "127.0.0.1:8080" || r.URL.Path != "/local" || r.URL.Query().Get("value") != "uid & data/1" {
			t.Fatal(r.URL)
		}
		return &http.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader(`{"ok":true}`)), Header: http.Header{}}, nil
	})}
	os.Args = []string{"controller-app", "set-local", "uid & data/1"}
	main()
	if !called {
		t.Fatal("command did not call fixture")
	}
}
