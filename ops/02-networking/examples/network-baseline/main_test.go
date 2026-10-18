package main

import (
	"bytes"
	"encoding/json"
	"net"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestHandlerReturnsObservedSourceAndPayload(t *testing.T) {
	t.Setenv("NODE_NAME", "worker01")
	t.Setenv("POD_NAME", "echo-one")
	body := bytes.Repeat([]byte("x"), 128*1024)
	request := httptest.NewRequest(http.MethodPost, "/", bytes.NewReader(body))
	request.RemoteAddr = "10.244.8.5:12345"
	writer := httptest.NewRecorder()
	handler(writer, request)
	var value echo
	if err := json.Unmarshal(writer.Body.Bytes(), &value); err != nil {
		t.Fatal(err)
	}
	if value.Peer != request.RemoteAddr || value.Node != "worker01" || value.Pod != "echo-one" || value.Bytes != len(body) || value.SHA256 != digest(body) {
		t.Fatalf("wrong echo: %+v", value)
	}
}

func TestHTTPProbeRejectsCorruptBackendAndUnexpectedSNAT(t *testing.T) {
	for _, test := range []struct{ name, peer, hash, expected string }{
		{"wrong backend", "127.0.0.1:1234", digest(nil), "another-node"},
		{"corrupt payload", "127.0.0.1:1234", "corrupt", "server"},
		{"unexpected SNAT", "192.168.9.109:1234", digest(nil), "server"},
	} {
		t.Run(test.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
				_ = json.NewEncoder(w).Encode(echo{Node: "server", Peer: test.peer, SHA256: test.hash})
			}))
			defer server.Close()
			err := httpProbe(probe{Name: "pod-http", Target: server.URL, Expected: test.expected, Timeout: 1000}, &result{}, nil)
			if err == nil {
				t.Fatal("bad response was accepted")
			}
		})
	}
}

func TestHTTPProbeTimeoutAndSizeLimit(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(handler))
	defer server.Close()
	start := time.Now()
	err := httpProbe(probe{Target: server.URL + "/delay", Timeout: 50}, &result{}, nil)
	if err == nil || time.Since(start) > time.Second {
		t.Fatalf("bounded timeout not enforced: %v", err)
	}
	request := httptest.NewRequest(http.MethodPost, "/", bytes.NewReader(make([]byte, 256*1024+1)))
	writer := httptest.NewRecorder()
	handler(writer, request)
	if writer.Code != http.StatusBadRequest {
		t.Fatalf("oversized request accepted: %d", writer.Code)
	}
}

func TestUDPProbeChecksBackendPayloadAndSource(t *testing.T) {
	t.Setenv("NODE_NAME", "udp-server")
	listener, err := net.ListenPacket("udp4", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	done := make(chan error, 1)
	go func() {
		body := make([]byte, 8192)
		n, peer, e := listener.ReadFrom(body)
		if e != nil {
			done <- e
			return
		}
		encoded, _ := json.Marshal(response(peer.String(), body[:n]))
		_, e = listener.WriteTo(encoded, peer)
		done <- e
	}()
	body := bytes.Repeat([]byte("x"), 4096)
	if err = udpProbe(probe{Target: listener.LocalAddr().String(), Expected: "udp-server", Timeout: 1000}, &result{}, body); err != nil {
		t.Fatal(err)
	}
	if err = <-done; err != nil {
		t.Fatal(err)
	}
}
