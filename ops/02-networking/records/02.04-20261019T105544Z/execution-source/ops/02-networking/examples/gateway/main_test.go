package main

import (
	"context"
	"encoding/json"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	healthpb "google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/metadata"
)

func TestHTTPIdentityPathHeadersAndTLS(t *testing.T) {
	t.Setenv("POD_NAME", "pod")
	t.Setenv("POD_UID", "uid")
	t.Setenv("VERSION", "v1")
	server := httptest.NewTLSServer(http.HandlerFunc(handler))
	defer server.Close()
	request, _ := http.NewRequest(http.MethodGet, server.URL+"/v1/test", nil)
	request.Host = "demo.svc.internal.egon.top"
	request.Header.Set("X-Cnpl-Nonce", "unique")
	response, err := server.Client().Do(request)
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	var value identity
	if err := json.NewDecoder(response.Body).Decode(&value); err != nil {
		t.Fatal(err)
	}
	if value.UID != "uid" || value.Nonce != "unique" || value.Version != "v1" || value.Protocol != "https" || value.TLS == "" || value.Path != "/v1/test" || value.Host != request.Host {
		t.Fatalf("wrong observed backend: %+v", value)
	}
}

func TestCanceledSlowRequestReturnsPromptly(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	request := httptest.NewRequest(http.MethodGet, "/slow", nil).WithContext(ctx)
	start := time.Now()
	handler(httptest.NewRecorder(), request)
	if time.Since(start) > time.Second {
		t.Fatal("canceled request continued sleeping")
	}
}

func TestActualGRPCHealthAndIdentityMetadata(t *testing.T) {
	t.Setenv("POD_NAME", "grpc-pod")
	t.Setenv("POD_UID", "grpc-uid")
	t.Setenv("VERSION", "v1")
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	server := grpc.NewServer()
	healthpb.RegisterHealthServer(server, healthService{})
	go func() { _ = server.Serve(listener) }()
	defer server.Stop()
	connection, err := grpc.NewClient("passthrough:///"+listener.Addr().String(), grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		t.Fatal(err)
	}
	defer connection.Close()
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	var headers metadata.MD
	reply, err := healthpb.NewHealthClient(connection).Check(ctx, &healthpb.HealthCheckRequest{}, grpc.Header(&headers))
	if err != nil || reply.Status != healthpb.HealthCheckResponse_SERVING || len(headers.Get("x-cnpl-uid")) != 1 || headers.Get("x-cnpl-uid")[0] != "grpc-uid" {
		t.Fatalf("gRPC health/metadata mismatch: %v %v %v", reply, headers, err)
	}
	if err := grpcProbe([]string{"--target", listener.Addr().String(), "--name", "grpc.test"}); err != nil {
		t.Fatal(err)
	}
}

func TestTCPAndUDPEchoCarryNonceAndUID(t *testing.T) {
	t.Setenv("POD_NAME", "net-pod")
	t.Setenv("POD_UID", "net-uid")
	tcp, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer tcp.Close()
	go func() { _ = tcpServe(tcp) }()
	connection, err := net.DialTimeout("tcp", tcp.Addr().String(), time.Second)
	if err != nil {
		t.Fatal(err)
	}
	defer connection.Close()
	_ = connection.SetDeadline(time.Now().Add(time.Second))
	_, _ = connection.Write([]byte("tcp-nonce\n"))
	var value identity
	if err := json.NewDecoder(connection).Decode(&value); err != nil || value.Nonce != "tcp-nonce" || value.UID != "net-uid" || value.Protocol != "tcp" {
		t.Fatalf("TCP echo mismatch: %+v %v", value, err)
	}
	udp, err := net.ListenPacket("udp4", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer udp.Close()
	go func() { _ = udpServe(udp) }()
	client, err := net.DialTimeout("udp4", udp.LocalAddr().String(), time.Second)
	if err != nil {
		t.Fatal(err)
	}
	defer client.Close()
	_ = client.SetDeadline(time.Now().Add(time.Second))
	_, _ = client.Write([]byte("udp-nonce"))
	buffer := make([]byte, 4096)
	n, err := client.Read(buffer)
	if err != nil {
		t.Fatal(err)
	}
	if err := json.NewDecoder(strings.NewReader(string(buffer[:n]))).Decode(&value); err != nil || value.Nonce != "udp-nonce" || value.UID != "net-uid" || value.Protocol != "udp" {
		t.Fatalf("UDP echo mismatch: %+v %v", value, err)
	}
}
