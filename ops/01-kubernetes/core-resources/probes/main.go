// 01.05 的可控应用和租约队列；仅依赖标准库，不使用业务集群的数据库或消息系统。
package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"path/filepath"
	"strconv"
	"sync"
	"sync/atomic"
	"syscall"
	"time"
)

type job struct {
	ID          string    `json:"id"`
	Seconds     int       `json:"seconds"`
	Lease       int       `json:"lease"`
	Owner       string    `json:"owner"`
	Token       string    `json:"token"`
	Until       time.Time `json:"until"`
	Attempts    int       `json:"attempts"`
	Effects     int       `json:"effects"`
	CommittedAt time.Time `json:"committed_at"`
}

type queue struct {
	mu   sync.Mutex
	Jobs map[string]*job
	Path string
}

func number(s string, fallback, max int) (int, error) {
	if s == "" {
		return fallback, nil
	}
	n, err := strconv.Atoi(s)
	if err != nil || n < 0 || n > max {
		return 0, fmt.Errorf("invalid bounded integer: %q", s)
	}
	return n, nil
}

func jsonReply(w http.ResponseWriter, value any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(value)
}

func (q *queue) persist() error {
	b, err := json.Marshal(q.Jobs)
	if err != nil {
		return err
	}
	f, err := os.CreateTemp(filepath.Dir(q.Path), ".queue-")
	if err != nil {
		return err
	}
	name := f.Name()
	defer os.Remove(name)
	if _, err = f.Write(b); err == nil {
		err = f.Sync()
	}
	closeErr := f.Close()
	if err != nil {
		return err
	}
	if closeErr != nil {
		return closeErr
	}
	return os.Rename(name, q.Path)
}

func (q *queue) claim(owner string, now time.Time) *job {
	for _, j := range q.Jobs {
		if j.Effects == 0 && (j.Owner == "" || !j.Until.After(now)) {
			j.Owner = owner
			j.Attempts++
			j.Token = fmt.Sprintf("%s/%d", owner, j.Attempts)
			j.Until = now.Add(time.Duration(j.Lease) * time.Second)
			copy := *j
			return &copy
		}
	}
	return nil
}

func (q *queue) commit(id, token string) error {
	j := q.Jobs[id]
	if j == nil || j.Token != token {
		return fmt.Errorf("unknown id or stale lease")
	}
	// 消费者重发相同提交不会产生第二次效果；过期消费者持旧 token 不能提交。
	if j.Effects == 0 {
		j.Effects = 1
		j.CommittedAt = time.Now()
	}
	return nil
}

func (q *queue) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	q.mu.Lock()
	defer q.mu.Unlock()
	v := r.URL.Query()
	if r.URL.Path == "/status" {
		jsonReply(w, q.Jobs)
		return
	}
	if r.Method != http.MethodPost {
		http.Error(w, "POST required", 405)
		return
	}
	switch r.URL.Path {
	case "/submit":
		id := v.Get("id")
		seconds, e := number(v.Get("seconds"), 3, 30)
		lease, e2 := number(v.Get("lease"), 30, 60)
		if id == "" || len(id) > 80 || seconds < 1 || lease < 2 || e != nil || e2 != nil {
			http.Error(w, "invalid job", 400)
			return
		}
		if q.Jobs[id] == nil {
			q.Jobs[id] = &job{ID: id, Seconds: seconds, Lease: lease}
		}
	case "/claim":
		if v.Get("owner") == "" {
			http.Error(w, "missing owner", 400)
			return
		}
		j := q.claim(v.Get("owner"), time.Now())
		if j == nil {
			w.WriteHeader(204)
			return
		}
		if err := q.persist(); err != nil {
			http.Error(w, err.Error(), 500)
			return
		}
		jsonReply(w, j)
		return
	case "/commit":
		if err := q.commit(v.Get("id"), v.Get("token")); err != nil {
			http.Error(w, err.Error(), 409)
			return
		}
	default:
		http.NotFound(w, r)
		return
	}
	if err := q.persist(); err != nil {
		http.Error(w, err.Error(), 500)
		return
	}
	jsonReply(w, q.Jobs[v.Get("id")])
}

type connectionKey struct{}
type app struct {
	mu                                          sync.Mutex
	Ready, Dependency, Business, Hang, Draining bool
	Started, Heartbeat, PreStop, Term           time.Time
	Delay                                       time.Duration
	Counts                                      map[string]int
	Active                                      int
	CurrentJob                                  string
	DependencyFailures                          int
	DependencyElapsed                           float64
	Completed                                   []string
	Name, UID                                   string
	stop                                        chan struct{}
}

func newApp(delay time.Duration) *app {
	now := time.Now()
	return &app{Ready: true, Started: now, Heartbeat: now, Delay: delay, Counts: map[string]int{},
		Name: os.Getenv("POD_NAME"), UID: os.Getenv("POD_UID"), stop: make(chan struct{})}
}

func (a *app) live(now time.Time) bool {
	return now.Sub(a.Started) >= a.Delay && now.Sub(a.Heartbeat) < 3*time.Second
}
func (a *app) ready(now time.Time) bool {
	return now.Sub(a.Started) >= a.Delay && a.Ready && !a.Dependency && !a.Business && !a.Draining && a.live(now)
}

func (a *app) tick() {
	ticker := time.NewTicker(200 * time.Millisecond)
	defer ticker.Stop()
	for {
		select {
		case <-a.stop:
			return
		case now := <-ticker.C:
			a.mu.Lock()
			if !a.Hang {
				a.Heartbeat = now
			}
			a.mu.Unlock()
		}
	}
}

func (a *app) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	a.mu.Lock()
	now := time.Now()
	path := r.URL.Path
	// 只有真实 kubelet 调用计入探针次数；教学控制请求不能冒充 kubelet 证据。
	if len(r.UserAgent()) >= 11 && r.UserAgent()[:11] == "kube-probe/" {
		a.Counts[path]++
	}
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("X-Pod-Name", a.Name)
	w.Header().Set("X-Pod-UID", a.UID)
	if id, ok := r.Context().Value(connectionKey{}).(int64); ok {
		w.Header().Set("X-Connection-ID", strconv.FormatInt(id, 10))
	}
	switch path {
	case "/startup", "/live", "/ready":
		ok := now.Sub(a.Started) >= a.Delay
		if path == "/live" {
			ok = a.live(now)
		}
		if path == "/ready" {
			ok = a.ready(now)
		}
		a.mu.Unlock()
		if !ok {
			w.WriteHeader(503)
		}
		jsonReply(w, map[string]bool{"ok": ok})
		return
	case "/metrics":
		// 在锁内编码，避免 map/slice 与后台消费者并发写。
		jsonReply(w, map[string]any{"uid": a.UID, "pod": a.Name, "uptime": now.Sub(a.Started).Seconds(), "counts": a.Counts,
			"ready": a.ready(now), "live": a.live(now), "active": a.Active, "current_job": a.CurrentJob,
			"completed": a.Completed, "prestop_at": a.PreStop, "term_at": a.Term,
			"dependency_failures": a.DependencyFailures, "dependency_elapsed_ms": a.DependencyElapsed})
		a.mu.Unlock()
		return
	case "/control":
		if r.Method != http.MethodPost {
			a.mu.Unlock()
			http.Error(w, "POST required", 405)
			return
		}
		on, err := strconv.ParseBool(r.URL.Query().Get("value"))
		if err != nil {
			a.mu.Unlock()
			http.Error(w, "invalid bool", 400)
			return
		}
		switch r.URL.Query().Get("kind") {
		case "ready":
			a.Ready = on
		case "dependency":
			a.Dependency = on
		case "business":
			a.Business = on
		case "hang":
			a.Hang = on
		case "drain":
			a.Draining = on
			if on && a.PreStop.IsZero() {
				a.PreStop = now
				log.Printf("PRESTOP uid=%s", a.UID)
			}
		default:
			a.mu.Unlock()
			http.Error(w, "invalid control", 400)
			return
		}
		a.mu.Unlock()
		jsonReply(w, map[string]bool{"ok": true})
		return
	case "/dependency":
		stalled := a.Dependency
		a.mu.Unlock()
		if stalled {
			select {
			case <-time.After(2 * time.Second):
			case <-r.Context().Done():
				return
			}
		}
		jsonReply(w, map[string]bool{"ok": true})
		return
	case "/identity":
		a.mu.Unlock()
		jsonReply(w, map[string]string{"pod": a.Name, "uid": a.UID})
		return
	case "/work":
		seconds, err := number(r.URL.Query().Get("seconds"), 0, 30)
		if err != nil {
			a.mu.Unlock()
			http.Error(w, err.Error(), 400)
			return
		}
		if a.Hang || a.Business || a.Dependency {
			a.mu.Unlock()
			http.Error(w, "local worker or dependency unavailable", 503)
			return
		}
		a.Active++
		a.mu.Unlock()
		defer func() { a.mu.Lock(); a.Active--; a.mu.Unlock() }()
		select {
		case <-time.After(time.Duration(seconds) * time.Second):
			jsonReply(w, map[string]string{"pod": a.Name, "uid": a.UID, "id": r.URL.Query().Get("id"), "result": "completed", "completed_at": time.Now().UTC().Format(time.RFC3339Nano)})
		case <-r.Context().Done():
			return
		}
		return
	default:
		a.mu.Unlock()
		http.NotFound(w, r)
		return
	}
}

// 所有内部客户端忽略代理环境；消息超时不会使本地 liveness 失败。
var internalClient = &http.Client{Timeout: 2 * time.Second, Transport: &http.Transport{Proxy: nil}}

func (a *app) monitorDependency(target string) {
	client := &http.Client{Timeout: 500 * time.Millisecond, Transport: &http.Transport{Proxy: nil}}
	defer client.CloseIdleConnections()
	for {
		a.checkDependency(client, target)
		select {
		case <-a.stop:
			return
		case <-time.After(500 * time.Millisecond):
		}
	}
}

func (a *app) checkDependency(client *http.Client, target string) {
	start := time.Now()
	r, err := client.Get(target)
	if err == nil {
		_, err = io.Copy(io.Discard, r.Body)
		r.Body.Close()
		if r.StatusCode != 200 {
			err = fmt.Errorf("HTTP %d", r.StatusCode)
		}
	}
	a.mu.Lock()
	defer a.mu.Unlock()
	a.Dependency = err != nil
	a.DependencyElapsed = float64(time.Since(start).Microseconds()) / 1000
	if err != nil {
		a.DependencyFailures++
	}
}

func post(target string, result any) (int, error) {
	r, err := internalClient.Post(target, "application/json", nil)
	if err != nil {
		return 0, err
	}
	defer r.Body.Close()
	if r.StatusCode >= 300 {
		b, _ := io.ReadAll(io.LimitReader(r.Body, 1024))
		return r.StatusCode, fmt.Errorf("HTTP %d: %s", r.StatusCode, b)
	}
	if result != nil && r.StatusCode != 204 {
		err = json.NewDecoder(r.Body).Decode(result)
	}
	return r.StatusCode, err
}

func (a *app) consume(broker string, done chan<- struct{}) {
	defer close(done)
	for {
		a.mu.Lock()
		stop := a.Draining
		a.mu.Unlock()
		if stop {
			return
		}
		var j job
		code, err := post(broker+"/claim?owner="+url.QueryEscape(a.UID), &j)
		if err != nil || code == 204 {
			select {
			case <-a.stop:
				return
			case <-time.After(200 * time.Millisecond):
			}
			continue
		}
		a.mu.Lock()
		a.CurrentJob = j.ID
		a.mu.Unlock()
		log.Printf("CLAIM id=%s uid=%s token=%s", j.ID, a.UID, j.Token)
		// 排空只停止下一次领取，不取消已经领取的消息。
		time.Sleep(time.Duration(j.Seconds) * time.Second)
		_, err = post(broker+"/commit?id="+url.QueryEscape(j.ID)+"&token="+url.QueryEscape(j.Token), nil)
		a.mu.Lock()
		if err == nil {
			a.Completed = append(a.Completed, j.ID)
		}
		a.CurrentJob = ""
		a.mu.Unlock()
		if err != nil {
			log.Printf("COMMIT FAILED id=%s: %v", j.ID, err)
		} else {
			log.Printf("COMMIT id=%s uid=%s", j.ID, a.UID)
		}
	}
}

func runApp() error {
	n, err := number(os.Getenv("START_SECONDS"), 0, 60)
	if err != nil {
		return err
	}
	a := newApp(time.Duration(n) * time.Second)
	go a.tick()
	if target := os.Getenv("DEPENDENCY_URL"); target != "" {
		go a.monitorDependency(target)
	}
	var next atomic.Int64
	s := &http.Server{Addr: ":8080", Handler: a, ReadHeaderTimeout: 3 * time.Second, IdleTimeout: 120 * time.Second,
		ConnContext: func(ctx context.Context, c net.Conn) context.Context {
			return context.WithValue(ctx, connectionKey{}, next.Add(1))
		}}
	done := make(chan struct{})
	broker := os.Getenv("BROKER_URL")
	if broker != "" {
		go a.consume(broker, done)
	} else {
		close(done)
	}
	signals := make(chan os.Signal, 1)
	signal.Notify(signals, syscall.SIGTERM, syscall.SIGINT)
	defer signal.Stop(signals)
	serverErr := make(chan error, 1)
	go func() { serverErr <- s.ListenAndServe() }()
	received := "TERM"
	select {
	case err = <-serverErr:
		return err
	case sig := <-signals:
		if sig == syscall.SIGINT {
			received = "INT"
		}
		a.mu.Lock()
		a.Draining = true
		a.Term = time.Now()
		a.mu.Unlock()
		log.Printf("SIGNAL %s uid=%s", sig, a.UID)
	}
	path := os.Getenv("TERMINATION_PATH")
	if path == "" {
		path = "/dev/termination-log"
	}
	return a.shutdown(s, done, path, received, 20*time.Second)
}

func (a *app) shutdown(s *http.Server, done <-chan struct{}, path, received string, budget time.Duration) error {
	ctx, cancel := context.WithTimeout(context.Background(), budget)
	defer cancel()
	err := s.Shutdown(ctx)
	select {
	case <-done:
	case <-ctx.Done():
		err = ctx.Err()
	}
	a.mu.Lock()
	receipt := map[string]any{"uid": a.UID, "signal": received, "drained": err == nil && a.Active == 0 && a.CurrentJob == "",
		"prestop_at": a.PreStop, "term_at": a.Term, "finished_at": time.Now(), "completed": a.Completed}
	b, encodeErr := json.Marshal(receipt)
	a.mu.Unlock()
	close(a.stop)
	if encodeErr != nil {
		return encodeErr
	}
	if writeErr := os.WriteFile(path, b, 0666); writeErr != nil {
		return writeErr
	}
	fmt.Println(string(b))
	return err
}

// 每条入口连接对应一条 Pod 内发出的 TCP 连接，不解析 HTTP、不复用其他会话。
func forward(local, remote net.Conn) {
	defer local.Close()
	defer remote.Close()
	done := make(chan struct{}, 2)
	go func() { _, _ = io.Copy(remote, local); done <- struct{}{} }()
	go func() { _, _ = io.Copy(local, remote); done <- struct{}{} }()
	<-done
}

func runRelay() error {
	target := os.Getenv("RELAY_TARGET")
	if target != "p05-route:8080" && target != "p05-term:8080" {
		return fmt.Errorf("relay target outside this experiment")
	}
	listener, err := net.Listen("tcp", ":8080")
	if err != nil {
		return err
	}
	defer listener.Close()
	for {
		local, err := listener.Accept()
		if err != nil {
			return err
		}
		go func() {
			remote, err := net.DialTimeout("tcp", target, 3*time.Second)
			if err != nil {
				log.Printf("RELAY %v", err)
				local.Close()
				return
			}
			forward(local, remote)
		}()
	}
}

func main() {
	log.SetFlags(log.LstdFlags | log.LUTC | log.Lmicroseconds)
	if len(os.Args) < 2 {
		log.Fatal("server | broker | relay | probe URL | prestop SECONDS")
	}
	var err error
	switch os.Args[1] {
	case "server":
		err = runApp()
	case "relay":
		err = runRelay()
	case "broker":
		q := &queue{Jobs: map[string]*job{}, Path: "/work/queue.json"}
		if b, e := os.ReadFile(q.Path); e == nil {
			err = json.Unmarshal(b, &q.Jobs)
		} else if !errors.Is(e, os.ErrNotExist) {
			err = e
		}
		if err == nil {
			err = http.ListenAndServe(":9090", q)
		}
	case "probe":
		if len(os.Args) != 3 {
			log.Fatal("probe URL")
		}
		var r *http.Response
		r, err = internalClient.Get(os.Args[2])
		if err == nil {
			_, err = io.Copy(os.Stdout, io.LimitReader(r.Body, 8192))
			r.Body.Close()
			if r.StatusCode != 200 {
				err = fmt.Errorf("HTTP %d", r.StatusCode)
			}
		}
	case "prestop":
		if len(os.Args) != 3 {
			log.Fatal("prestop SECONDS")
		}
		var n int
		n, err = number(os.Args[2], 0, 20)
		if err == nil {
			_, err = post("http://127.0.0.1:8080/control?kind=drain&value=true", nil)
		}
		if err == nil {
			time.Sleep(time.Duration(n) * time.Second)
		}
	default:
		err = fmt.Errorf("unknown command")
	}
	if err != nil {
		log.Fatal(err)
	}
}
