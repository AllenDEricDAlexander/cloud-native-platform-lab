// 01.06 的版本、临时数据和请求排空应用；只依赖标准库。
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"strconv"
	"sync"
	"syscall"
	"time"
)

type app struct {
	mu                        sync.Mutex
	Version, Name, UID, Local string
	Started, PreStop, Term    time.Time
	Delay                     time.Duration
	NotReady, Draining        bool
	Active                    int
}

func bounded(s string, fallback, max int) (int, error) {
	if s == "" {
		return fallback, nil
	}
	n, e := strconv.Atoi(s)
	if e != nil || n < 0 || n > max {
		return 0, fmt.Errorf("invalid bounded duration %q", s)
	}
	return n, nil
}

func reply(w http.ResponseWriter, code int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(value)
}

func (a *app) identity() map[string]any {
	return map[string]any{"version": a.Version, "pod": a.Name, "uid": a.UID}
}

func (a *app) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	a.mu.Lock()
	now := time.Now()
	value := a.identity()
	switch r.URL.Path {
	case "/startup", "/live", "/ready":
		ok := now.Sub(a.Started) >= a.Delay
		if r.URL.Path == "/ready" {
			ok = ok && !a.NotReady && !a.Draining
		}
		a.mu.Unlock()
		if ok {
			reply(w, 200, value)
		} else {
			reply(w, 503, value)
		}
		return
	case "/identity":
		a.mu.Unlock()
		reply(w, 200, value)
		return
	case "/metrics":
		value["active"] = a.Active
		value["draining"] = a.Draining
		value["prestop_at"] = a.PreStop
		value["term_at"] = a.Term
		a.mu.Unlock()
		reply(w, 200, value)
		return
	case "/local":
		if r.Method == http.MethodPost {
			data := r.URL.Query().Get("value")
			if len(data) > 200 {
				a.mu.Unlock()
				http.Error(w, "local value too long", 400)
				return
			}
			if err := os.WriteFile(a.Local, []byte(data), 0600); err != nil {
				a.mu.Unlock()
				http.Error(w, err.Error(), 500)
				return
			}
		}
		b, err := os.ReadFile(a.Local)
		a.mu.Unlock()
		if err != nil {
			http.Error(w, err.Error(), 500)
			return
		}
		value["value"] = string(b)
		reply(w, 200, value)
		return
	case "/drain":
		if r.Method != http.MethodPost {
			a.mu.Unlock()
			http.Error(w, "POST required", 405)
			return
		}
		a.Draining = true
		if a.PreStop.IsZero() {
			a.PreStop = now
		}
		a.mu.Unlock()
		reply(w, 200, value)
		return
	case "/work":
		seconds, err := bounded(r.URL.Query().Get("seconds"), 0, 20)
		if err != nil {
			a.mu.Unlock()
			http.Error(w, err.Error(), 400)
			return
		}
		if now.Sub(a.Started) < a.Delay {
			a.mu.Unlock()
			reply(w, 503, value)
			return
		}
		// bad 镜像故意保持探针健康，用于证明 rollout 完成并不等于业务正确。
		if a.Version == "bad" {
			a.mu.Unlock()
			value["error"] = "intentional business regression"
			reply(w, 500, value)
			return
		}
		a.Active++
		a.mu.Unlock()
		defer func() { a.mu.Lock(); a.Active--; a.mu.Unlock() }()
		select {
		case <-time.After(time.Duration(seconds) * time.Second):
			value["result"] = "completed"
			value["id"] = r.URL.Query().Get("id")
			value["completed_at"] = time.Now().UTC()
			reply(w, 200, value)
		case <-r.Context().Done():
		}
		return
	default:
		a.mu.Unlock()
		http.NotFound(w, r)
		return
	}
}

var localClient = &http.Client{Timeout: 2 * time.Second, Transport: &http.Transport{Proxy: nil}}

func fetch(target, method string) error {
	r, err := http.NewRequest(method, target, nil)
	if err != nil {
		return err
	}
	response, err := localClient.Do(r)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	_, err = io.Copy(os.Stdout, io.LimitReader(response.Body, 8192))
	if err != nil {
		return err
	}
	if response.StatusCode != 200 {
		return fmt.Errorf("HTTP %d", response.StatusCode)
	}
	return nil
}

func (a *app) shutdown(s *http.Server, path string, budget time.Duration) error {
	ctx, cancel := context.WithTimeout(context.Background(), budget)
	defer cancel()
	err := s.Shutdown(ctx)
	a.mu.Lock()
	value := a.identity()
	value["signal"] = "TERM"
	value["drained"] = err == nil && a.Active == 0
	value["prestop_at"] = a.PreStop
	value["term_at"] = a.Term
	value["finished_at"] = time.Now()
	b, e := json.Marshal(value)
	a.mu.Unlock()
	if e != nil {
		return e
	}
	if e = os.WriteFile(path, b, 0666); e != nil {
		return e
	}
	log.Print(string(b))
	return err
}

func serve() error {
	version := os.Getenv("APP_VERSION")
	if version != "v1" && version != "v2" && version != "bad" {
		return fmt.Errorf("missing locked APP_VERSION")
	}
	delay := 2
	if version != "v1" {
		delay = 4
	}
	if raw := os.Getenv("START_SECONDS"); raw != "" {
		n, e := bounded(raw, delay, 20)
		if e != nil {
			return e
		}
		delay = n
	}
	work := os.Getenv("APP_WORK")
	if work == "" {
		work = "/work"
	}
	a := &app{Version: version, Name: os.Getenv("POD_NAME"), UID: os.Getenv("POD_UID"), Started: time.Now(), Delay: time.Duration(delay) * time.Second,
		NotReady: os.Getenv("FORCE_NOT_READY") == "true", Local: filepath.Join(work, "local")}
	// 首次由 Pod UID 初始化；容器重启复用卷，Pod 重建会获得新 emptyDir。
	if _, err := os.Stat(a.Local); os.IsNotExist(err) {
		if err = os.WriteFile(a.Local, []byte(a.UID), 0600); err != nil {
			return err
		}
	} else if err != nil {
		return err
	}
	s := &http.Server{Addr: ":8080", Handler: a, ReadHeaderTimeout: 3 * time.Second, IdleTimeout: 30 * time.Second}
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGTERM)
	defer signal.Stop(sig)
	failed := make(chan error, 1)
	go func() { failed <- s.ListenAndServe() }()
	select {
	case e := <-failed:
		return e
	case <-sig:
		a.mu.Lock()
		a.Draining = true
		a.Term = time.Now()
		a.mu.Unlock()
	}
	return a.shutdown(s, "/dev/termination-log", 18*time.Second)
}

func forward(a, b net.Conn) {
	defer a.Close()
	defer b.Close()
	done := make(chan struct{}, 2)
	go func() { _, _ = io.Copy(a, b); done <- struct{}{} }()
	go func() { _, _ = io.Copy(b, a); done <- struct{}{} }()
	<-done
}

func relay() error {
	target := os.Getenv("RELAY_TARGET")
	host, port, err := net.SplitHostPort(target)
	ip := net.ParseIP(host).To4()
	serviceIP := err == nil && port == "8080" && ip != nil && ip[0] == 192 && ip[1] == 168 && ip[2] == 20
	if !serviceIP && target != "p06-entry:8080" && target != "p06-stable:8080" && target != "p06-canary:8080" {
		return fmt.Errorf("relay target outside experiment")
	}
	l, err := net.Listen("tcp", ":8080")
	if err != nil {
		return err
	}
	defer l.Close()
	for {
		a, e := l.Accept()
		if e != nil {
			return e
		}
		go func() {
			b, e := net.DialTimeout("tcp", target, 2*time.Second)
			if e != nil {
				log.Print(e)
				a.Close()
				return
			}
			forward(a, b)
		}()
	}
}

func main() {
	if len(os.Args) < 2 {
		log.Fatal("server | relay | probe URL | prestop SECONDS")
	}
	var err error
	switch os.Args[1] {
	case "server":
		err = serve()
	case "relay":
		err = relay()
	case "probe":
		if len(os.Args) != 3 {
			log.Fatal("probe URL")
		}
		err = fetch(os.Args[2], http.MethodGet)
	case "prestop":
		if len(os.Args) != 3 {
			log.Fatal("prestop SECONDS")
		}
		var n int
		n, err = bounded(os.Args[2], 0, 10)
		if err == nil {
			err = fetch("http://127.0.0.1:8080/drain", http.MethodPost)
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
