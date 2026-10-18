package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
)

func TestCommitConflictAndConcurrentRedeliveryHaveOneEffect(t *testing.T) {
	t.Setenv("CORE_RUN", "run")
	var mu sync.Mutex
	version := 1
	effects := map[string]any{}
	conflict := true
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		if r.URL.Path != "/api/v1/namespaces/isolated/configmaps/p09-ledger" || r.Header.Get("Authorization") != "Bearer fixture" {
			t.Error("request escaped ledger scope")
			w.WriteHeader(403)
			return
		}
		if r.Method == "GET" {
			_ = json.NewEncoder(w).Encode(map[string]any{"metadata": map[string]any{"resourceVersion": fmt.Sprint(version), "labels": map[string]any{"cnpl.io/core-run": "run"}}, "data": effects})
			return
		}
		var body map[string]any
		if json.NewDecoder(r.Body).Decode(&body) != nil {
			w.WriteHeader(400)
			return
		}
		if conflict || body["metadata"].(map[string]any)["resourceVersion"] != fmt.Sprint(version) {
			conflict = false
			w.WriteHeader(409)
			return
		}
		version++
		effects = body["data"].(map[string]any)
		_, _ = w.Write([]byte("{}"))
	}))
	defer server.Close()
	c := &apiClient{client: server.Client(), base: server.URL, namespace: "isolated", token: "fixture"}
	var committed atomic.Int32
	var callers sync.WaitGroup
	for i := 0; i < 12; i++ {
		callers.Add(1)
		go func() {
			defer callers.Done()
			first, err := c.commit("p09-ledger", "business-0")
			if err != nil {
				t.Error(err)
			}
			if first {
				committed.Add(1)
			}
		}()
	}
	callers.Wait()
	if committed.Load() != 1 || effects["business-0"] != "1" || len(effects) != 1 {
		t.Fatalf("duplicate effects: %v / %d", effects, committed.Load())
	}
}

func TestForeignLedgerIsNeverWritten(t *testing.T) {
	t.Setenv("CORE_RUN", "ours")
	var writes atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != "GET" {
			writes.Add(1)
		}
		_, _ = w.Write([]byte(`{"metadata":{"labels":{"cnpl.io/core-run":"other"}},"data":{}}`))
	}))
	defer server.Close()
	c := &apiClient{client: server.Client(), base: server.URL, namespace: "isolated"}
	if _, err := c.commit("p09-ledger", "business-0"); err == nil || writes.Load() != 0 {
		t.Fatal("foreign ledger changed")
	}
}

func TestMemoryHoldReusesAllocationAndOffReleasesIt(t *testing.T) {
	a := &application{}
	a.load("memory")
	original := &a.memory[0]
	a.load("hold")
	if len(a.memory) != 96*1024*1024 || original != &a.memory[0] {
		t.Fatal("hold allocated a second buffer")
	}
	a.load("off")
	if a.memory != nil {
		t.Fatal("memory was not released")
	}
	a.load("cpu")
	stop := a.cpuStop
	defer a.load("off")
	a.load("cpu")
	if stop != a.cpuStop {
		t.Fatal("duplicate CPU worker")
	}
	a.load("off")
	select {
	case <-stop:
	default:
		t.Fatal("CPU worker not stopped")
	}
}

func TestIdentityDoesNotExposeSecretAndReadinessIsSeparate(t *testing.T) {
	t.Setenv("APP_WORK", t.TempDir())
	t.Setenv("SECRET_VALUE", "fixture-secret-must-stay-private")
	t.Setenv("APP_CONFIG", "v1")
	t.Setenv("POD_NAME", "p07-state-0")
	a := &application{}
	w := httptest.NewRecorder()
	a.ServeHTTP(w, httptest.NewRequest("GET", "/identity", nil))
	if strings.Contains(w.Body.String(), os.Getenv("SECRET_VALUE")) || !strings.Contains(w.Body.String(), "p07-state-0") {
		t.Fatal("identity leaked a secret or lost identity")
	}
	if code, err := run([]string{"ready", "false"}); code != 0 || err != nil {
		t.Fatal(err)
	}
	w = httptest.NewRecorder()
	a.ServeHTTP(w, httptest.NewRequest("GET", "/ready", nil))
	if w.Code != 503 {
		t.Fatal("readiness did not fail")
	}
	w = httptest.NewRecorder()
	a.ServeHTTP(w, httptest.NewRequest("GET", "/live", nil))
	if w.Code != 200 {
		t.Fatal("readiness changed liveness")
	}
	if _, err := run([]string{"ready", "true"}); err != nil {
		t.Fatal(err)
	}
	w = httptest.NewRecorder()
	a.ServeHTTP(w, httptest.NewRequest("GET", "/ready", nil))
	if w.Code != 200 {
		t.Fatal("readiness not restored")
	}
	if code, err := run([]string{"job", "permanent"}); code != 42 || err != nil {
		t.Fatal("permanent exit policy changed")
	}
}
