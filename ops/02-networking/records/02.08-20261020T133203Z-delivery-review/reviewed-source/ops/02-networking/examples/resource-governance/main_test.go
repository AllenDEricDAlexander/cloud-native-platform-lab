package main

import (
	"context"
	"encoding/json"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestResourceBounds(t *testing.T) {
	for _, v := range []struct {
		mode string
		n    int
	}{{"cpu", 0}, {"cpu", 21}, {"memory", 257}, {"disk", 65}, {"unknown", 1}} {
		if workload(v.mode, v.n) == nil {
			t.Fatalf("unbounded workload accepted %+v", v)
		}
	}
	if stream("127.0.0.1:1", 1201) == nil {
		t.Fatal("unbounded stream accepted")
	}
}

func TestNonceRetryAccountingAndFailure(t *testing.T) {
	t.Setenv("POD_UID", "backend-uid")
	for i := 0; i < 3; i++ {
		req := httptest.NewRequest("GET", "/fail", nil)
		req.Header.Set("X-Cnpl-Nonce", "retry-unit")
		w := httptest.NewRecorder()
		handler(w, req)
		if w.Code != 503 || !strings.Contains(w.Body.String(), "backend-uid") {
			t.Fatal(w.Code, w.Body.String())
		}
	}
	w := httptest.NewRecorder()
	handler(w, httptest.NewRequest("GET", "/counts?nonce=retry-unit", nil))
	var value map[string]int
	if err := json.Unmarshal(w.Body.Bytes(), &value); err != nil {
		t.Fatal(err)
	}
	if value["count"] != 3 {
		t.Fatal(value)
	}
}

func TestHealthAndSlowCancellation(t *testing.T) {
	req := httptest.NewRequest("GET", "/healthz", nil)
	w := httptest.NewRecorder()
	handler(w, req)
	if w.Code != 200 {
		t.Fatal(w.Code)
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	req = httptest.NewRequest("GET", "/slow", nil).WithContext(ctx)
	start := time.Now()
	handler(httptest.NewRecorder(), req)
	if time.Since(start) > 250*time.Millisecond {
		t.Fatal("cancelled request remained active")
	}
}
