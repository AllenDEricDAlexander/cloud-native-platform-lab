package main

import (
	"bufio"
	"context"
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

func invoke(a http.Handler, method, target, agent string) *httptest.ResponseRecorder {
	r := httptest.NewRequest(method, target, nil)
	r.Header.Set("User-Agent", agent)
	w := httptest.NewRecorder()
	a.ServeHTTP(w, r)
	return w
}

func TestHealthBoundaries(t *testing.T) {
	a := newApp(12 * time.Second)
	if invoke(a, "GET", "/startup", "kube-probe/1.36").Code != 503 {
		t.Fatal("startup should fail before measured delay")
	}
	if invoke(a, "GET", "/live", "kube-probe/1.36").Code != 503 {
		t.Fatal("slow initialization would fail liveness without startup protection")
	}
	a.Started = time.Now().Add(-15 * time.Second)
	if invoke(a, "GET", "/ready", "").Code != 200 {
		t.Fatal("startup completed")
	}
	for _, kind := range []string{"business", "dependency"} {
		if invoke(a, "POST", "/control?kind="+kind+"&value=true", "").Code != 200 {
			t.Fatal(kind)
		}
		if invoke(a, "GET", "/ready", "").Code != 503 || invoke(a, "GET", "/live", "").Code != 200 {
			t.Fatal("dependency/business must affect readiness but not local liveness")
		}
		invoke(a, "POST", "/control?kind="+kind+"&value=false", "")
	}
	a.Heartbeat = time.Now().Add(-4 * time.Second)
	if invoke(a, "GET", "/live", "").Code != 503 {
		t.Fatal("stale local heartbeat")
	}
	if a.Counts["/live"] != 1 || a.Counts["/startup"] != 1 {
		t.Fatal("manual calls must not fabricate kubelet counts")
	}
}

func TestControlsAndBoundedWork(t *testing.T) {
	a := newApp(0)
	for _, path := range []string{"/control?kind=oops&value=true", "/control?kind=ready&value=oops"} {
		if invoke(a, "POST", path, "").Code != 400 {
			t.Fatal(path)
		}
	}
	if invoke(a, "GET", "/control?kind=ready&value=false", "").Code != 405 {
		t.Fatal("control requires POST")
	}
	if invoke(a, "GET", "/work?seconds=1000", "").Code != 400 {
		t.Fatal("unbounded work")
	}
	invoke(a, "POST", "/control?kind=drain&value=true", "")
	if a.PreStop.IsZero() || !a.Draining || invoke(a, "GET", "/ready", "").Code != 503 {
		t.Fatal("drain must remove readiness and stop claiming")
	}
	if invoke(a, "GET", "/work?seconds=0&id=last", "").Code != 200 || a.Active != 0 {
		t.Fatal("prestop must allow propagation-window requests to finish")
	}
}

func TestLeasedQueueCompensatesAndDeduplicates(t *testing.T) {
	q := &queue{Jobs: map[string]*job{}, Path: filepath.Join(t.TempDir(), "queue.json")}
	if invoke(q, "POST", "/submit?id=x&seconds=3&lease=6", "").Code != 200 {
		t.Fatal("submit")
	}
	now := time.Now()
	first := q.claim("killed", now)
	if q.claim("replacement", now.Add(5*time.Second)) != nil {
		t.Fatal("must respect outstanding lease")
	}
	second := q.claim("replacement", now.Add(7*time.Second))
	if second == nil || second.Attempts != 2 || second.Token == first.Token {
		t.Fatal("redelivery")
	}
	if q.commit("x", first.Token) == nil {
		t.Fatal("stale consumer must not commit")
	}
	for i := 0; i < 3; i++ {
		if err := q.commit("x", second.Token); err != nil {
			t.Fatal(err)
		}
	}
	if q.Jobs["x"].Effects != 1 || q.claim("other", now.Add(time.Minute)) != nil {
		t.Fatal("same effect committed more than once")
	}
	if err := q.persist(); err != nil {
		t.Fatal(err)
	}
	if invoke(q, "GET", "/submit?id=y", "").Code != 405 {
		t.Fatal("mutation requires POST")
	}
	if invoke(q, "POST", "/submit?id=y&seconds=31", "").Code != 400 {
		t.Fatal("invalid input")
	}
}

// 有界内存连接模拟 HTTP/1.1；不监听 TCP，不启动实验应用进程。
type pipeListener struct {
	net.Conn
	once sync.Once
	done chan struct{}
}

func (l *pipeListener) Accept() (net.Conn, error) {
	var c net.Conn
	l.once.Do(func() { c = l.Conn })
	if c != nil {
		return c, nil
	}
	<-l.done
	return nil, net.ErrClosed
}
func (l *pipeListener) Close() error {
	select {
	case <-l.done:
	default:
		close(l.done)
	}
	return nil
}
func (l *pipeListener) Addr() net.Addr { return l.Conn.LocalAddr() }

func TestUnreadyDoesNotCloseRelayedHTTPConnection(t *testing.T) {
	server, relayRemote := net.Pipe()
	relayLocal, client := net.Pipe()
	go forward(relayLocal, relayRemote)
	defer client.Close()
	listener := &pipeListener{Conn: server, done: make(chan struct{})}
	a := newApp(0)
	a.Name = "chosen-pod"
	s := &http.Server{Handler: a, ConnContext: func(ctx context.Context, _ net.Conn) context.Context {
		return context.WithValue(ctx, connectionKey{}, int64(77))
	}}
	finished := make(chan struct{})
	go func() { defer close(finished); _ = s.Serve(listener) }()
	defer func() { _ = s.Close(); <-finished }()
	_ = client.SetDeadline(time.Now().Add(3 * time.Second))
	reader := bufio.NewReader(client)
	for i := 0; i < 2; i++ {
		if i == 1 {
			invoke(a, "POST", "/control?kind=ready&value=false", "")
		}
		_, err := io.WriteString(client, "GET /identity HTTP/1.1\r\nHost: lab\r\n\r\n")
		if err != nil {
			t.Fatal(err)
		}
		r, err := http.ReadResponse(reader, nil)
		if err != nil {
			t.Fatal(err)
		}
		b, err := io.ReadAll(r.Body)
		r.Body.Close()
		if err != nil || r.StatusCode != 200 || r.Header.Get("X-Connection-ID") != "77" || !strings.Contains(string(b), "chosen-pod") {
			t.Fatalf("existing connection: %s %v", b, err)
		}
	}
}

func TestMetricsIdentityAndDrainReceiptInputs(t *testing.T) {
	a := newApp(0)
	a.UID = "test-uid"
	invoke(a, "POST", "/control?kind=drain&value=true", "")
	var metrics map[string]any
	if err := json.Unmarshal(invoke(a, "GET", "/metrics", "").Body.Bytes(), &metrics); err != nil {
		t.Fatal(err)
	}
	if metrics["uid"] != "test-uid" || metrics["prestop_at"] == "0001-01-01T00:00:00Z" {
		t.Fatal(metrics)
	}
}

func TestActualDependencyTimeoutPreservesLocalLiveness(t *testing.T) {
	server, remote := net.Pipe()
	listener := &pipeListener{Conn: server, done: make(chan struct{})}
	dependency := newApp(0)
	dependency.Dependency = true
	s := &http.Server{Handler: dependency}
	finished := make(chan struct{})
	go func() { defer close(finished); _ = s.Serve(listener) }()
	defer func() { _ = s.Close(); <-finished }()
	transport := &http.Transport{DialContext: func(context.Context, string, string) (net.Conn, error) { return remote, nil }}
	defer transport.CloseIdleConnections()
	a := newApp(0)
	a.checkDependency(&http.Client{Timeout: 500 * time.Millisecond, Transport: transport}, "http://dependency/dependency")
	if !a.Dependency || a.DependencyFailures != 1 || a.DependencyElapsed < 450 || !a.live(time.Now()) {
		t.Fatalf("timeout/liveness: %+v", a)
	}
}

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

func TestConsumerDrainsCurrentJobAndStopsFetching(t *testing.T) {
	q := &queue{Jobs: map[string]*job{"first": {ID: "first", Seconds: 1, Lease: 5}}, Path: filepath.Join(t.TempDir(), "queue.json")}
	old := internalClient
	defer func() { internalClient = old }()
	internalClient = &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		w := httptest.NewRecorder()
		q.ServeHTTP(w, r)
		return w.Result(), nil
	})}
	a := newApp(0)
	a.UID = "consumer-uid"
	done := make(chan struct{})
	go a.consume("http://broker", done)
	deadline := time.Now().Add(2 * time.Second)
	for {
		a.mu.Lock()
		active := a.CurrentJob == "first"
		a.mu.Unlock()
		if active {
			break
		}
		if time.Now().After(deadline) {
			t.Fatal("consumer did not claim")
		}
		time.Sleep(time.Millisecond)
	}
	q.mu.Lock()
	q.Jobs["next"] = &job{ID: "next", Seconds: 1, Lease: 5}
	q.mu.Unlock()
	invoke(a, "POST", "/control?kind=drain&value=true", "")
	a.Term = time.Now()
	path := filepath.Join(t.TempDir(), "termination")
	if err := a.shutdown(&http.Server{}, done, path, "TERM", 2*time.Second); err != nil {
		t.Fatal(err)
	}
	q.mu.Lock()
	defer q.mu.Unlock()
	if q.Jobs["first"].Effects != 1 || q.Jobs["next"].Attempts != 0 {
		t.Fatal("drain lost current work or fetched another message")
	}
	b, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var receipt map[string]any
	if err = json.Unmarshal(b, &receipt); err != nil || receipt["drained"] != true || receipt["uid"] != a.UID {
		t.Fatalf("receipt: %s %v", b, err)
	}
}

func TestHTTPShutdownWaitsForLongRequest(t *testing.T) {
	server, client := net.Pipe()
	defer client.Close()
	listener := &pipeListener{Conn: server, done: make(chan struct{})}
	a := newApp(0)
	s := &http.Server{Handler: a}
	go func() { _ = s.Serve(listener) }()
	defer s.Close()
	response := make(chan error, 1)
	go func() {
		_, err := io.WriteString(client, "GET /work?seconds=1&id=drain HTTP/1.1\r\nHost: lab\r\n\r\n")
		if err == nil {
			var r *http.Response
			r, err = http.ReadResponse(bufio.NewReader(client), nil)
			if err == nil {
				var b []byte
				b, err = io.ReadAll(r.Body)
				r.Body.Close()
				if !strings.Contains(string(b), "completed") {
					err = io.ErrUnexpectedEOF
				}
			}
		}
		response <- err
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
			t.Fatal("request did not start")
		}
		time.Sleep(time.Millisecond)
	}
	done := make(chan struct{})
	close(done)
	a.Term = time.Now()
	if err := a.shutdown(s, done, filepath.Join(t.TempDir(), "term"), "TERM", 3*time.Second); err != nil {
		t.Fatal(err)
	}
	if err := <-response; err != nil {
		t.Fatal(err)
	}
}

func TestInsufficientDrainBudgetCannotReportSuccess(t *testing.T) {
	a := newApp(0)
	a.CurrentJob = "stuck"
	path := filepath.Join(t.TempDir(), "term")
	if err := a.shutdown(&http.Server{}, make(chan struct{}), path, "TERM", 20*time.Millisecond); err == nil {
		t.Fatal("must report deadline failure")
	}
	b, _ := os.ReadFile(path)
	var receipt map[string]any
	_ = json.Unmarshal(b, &receipt)
	if receipt["drained"] != false {
		t.Fatal("partial shutdown fabricated successful drain")
	}
}

func TestProbeHistorySurvivesLateObserver(t *testing.T) {
	a := newApp(6 * time.Second)
	invoke(a, "GET", "/startup", "kube-probe/1.36")
	invoke(a, "GET", "/metrics", "manual")
	a.Started = time.Now().Add(-8 * time.Second)
	invoke(a, "GET", "/startup", "kube-probe/1.36")
	invoke(a, "GET", "/ready", "kube-probe/1.36")
	var m struct {
		Trace []probeSample `json:"probe_trace"`
	}
	if err := json.Unmarshal(invoke(a, "GET", "/metrics", "").Body.Bytes(), &m); err != nil {
		t.Fatal(err)
	}
	if len(m.Trace) != 3 || m.Trace[0].Path != "/startup" || m.Trace[0].StartupComplete || !m.Trace[2].StartupComplete {
		t.Fatal(m.Trace)
	}
	for i := 0; i < 600; i++ {
		invoke(a, "GET", "/startup", "kube-probe/1.36")
	}
	if len(a.ProbeTrace) != 512 {
		t.Fatal("trace must be bounded")
	}
}

type commandTransport func(*http.Request) (*http.Response, error)

func (f commandTransport) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

func TestNativeCommandsUseExactPOSTAndEscapedValues(t *testing.T) {
	originalArgs, originalClient := os.Args, internalClient
	defer func() { os.Args = originalArgs; internalClient = originalClient }()
	cases := []struct {
		args                   []string
		host, path, key, value string
	}{
		{[]string{"control", "ready", "false"}, "127.0.0.1:8080", "/control", "value", "false"},
		{[]string{"queue-submit", "a&b", "12", "30"}, "127.0.0.1:9090", "/submit", "id", "a&b"},
		{[]string{"queue-commit", "a&b", "uid/2&x"}, "127.0.0.1:9090", "/commit", "token", "uid/2&x"},
	}
	for _, c := range cases {
		called := false
		internalClient = &http.Client{Transport: commandTransport(func(r *http.Request) (*http.Response, error) {
			called = true
			if r.Method != "POST" || r.URL.Host != c.host || r.URL.Path != c.path || r.URL.Query().Get(c.key) != c.value {
				t.Fatal(r.URL)
			}
			return &http.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader(`{"ok":true}`)), Header: http.Header{}}, nil
		})}
		os.Args = append([]string{"probe-lab"}, c.args...)
		main()
		if !called {
			t.Fatal("command did not call fixture")
		}
	}
}
