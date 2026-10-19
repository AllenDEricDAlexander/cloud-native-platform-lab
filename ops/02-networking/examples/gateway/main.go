// 02.04 的协议测试后端与真实 gRPC 客户端；身份来自 Downward API，不依赖反射。
package main

import (
	"bufio"
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/credentials/insecure"
	healthpb "google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/metadata"
)

type identity struct {
	Pod      string              `json:"pod"`
	UID      string              `json:"uid"`
	Node     string              `json:"node"`
	Version  string              `json:"version"`
	Protocol string              `json:"protocol"`
	Nonce    string              `json:"nonce"`
	Path     string              `json:"path,omitempty"`
	Host     string              `json:"host,omitempty"`
	TLS      string              `json:"tls,omitempty"`
	Headers  map[string][]string `json:"headers,omitempty"`
}

func observed(protocol, nonce string) identity {
	return identity{Pod: os.Getenv("POD_NAME"), UID: os.Getenv("POD_UID"), Node: os.Getenv("NODE_NAME"), Version: os.Getenv("VERSION"), Protocol: protocol, Nonce: nonce}
}

func handler(w http.ResponseWriter, r *http.Request) {
	if strings.HasPrefix(r.URL.Path, "/slow") {
		select {
		case <-r.Context().Done():
			return
		case <-time.After(3 * time.Second):
		}
	}
	value := observed("http", r.Header.Get("X-Cnpl-Nonce"))
	value.Path, value.Host, value.Headers = r.URL.Path, r.Host, r.Header
	if r.TLS != nil {
		value.Protocol, value.TLS = "https", tls.VersionName(r.TLS.Version)
	}
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	_ = json.NewEncoder(w).Encode(value)
}

type healthService struct {
	healthpb.UnimplementedHealthServer
}

func (healthService) Check(ctx context.Context, _ *healthpb.HealthCheckRequest) (*healthpb.HealthCheckResponse, error) {
	_ = grpc.SetHeader(ctx, metadata.Pairs("x-cnpl-pod", os.Getenv("POD_NAME"), "x-cnpl-uid", os.Getenv("POD_UID"), "x-cnpl-version", os.Getenv("VERSION")))
	return &healthpb.HealthCheckResponse{Status: healthpb.HealthCheckResponse_SERVING}, nil
}

func tcpServe(listener net.Listener) error {
	for {
		connection, err := listener.Accept()
		if err != nil {
			return err
		}
		go func() {
			defer connection.Close()
			_ = connection.SetDeadline(time.Now().Add(3 * time.Second))
			line, err := bufio.NewReader(io.LimitReader(connection, 4097)).ReadString('\n')
			if err == nil && len(line) <= 4096 {
				_ = json.NewEncoder(connection).Encode(observed("tcp", strings.TrimSuffix(line, "\n")))
			}
		}()
	}
}

func udpServe(listener net.PacketConn) error {
	buffer := make([]byte, 4097)
	for {
		n, peer, err := listener.ReadFrom(buffer)
		if err != nil {
			return err
		}
		if n <= 4096 {
			data, _ := json.Marshal(observed("udp", string(buffer[:n])))
			_, _ = listener.WriteTo(data, peer)
		}
	}
}

func serve() error {
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer stop()
	httpServer := &http.Server{Addr: ":8080", Handler: http.HandlerFunc(handler), ReadHeaderTimeout: 3 * time.Second, WriteTimeout: 5 * time.Second, IdleTimeout: 10 * time.Second, MaxHeaderBytes: 8192}
	grpcListener, err := net.Listen("tcp", ":50051")
	if err != nil {
		return err
	}
	defer grpcListener.Close()
	tcpListener, err := net.Listen("tcp", ":9000")
	if err != nil {
		return err
	}
	defer tcpListener.Close()
	udpListener, err := net.ListenPacket("udp4", ":9001")
	if err != nil {
		return err
	}
	defer udpListener.Close()
	server := grpc.NewServer()
	healthpb.RegisterHealthServer(server, healthService{})
	defer server.Stop()
	failures := make(chan error, 5)
	go func() { failures <- httpServer.ListenAndServe() }()
	go func() { failures <- server.Serve(grpcListener) }()
	go func() { failures <- tcpServe(tcpListener) }()
	go func() { failures <- udpServe(udpListener) }()
	var secure *http.Server
	if cert, key := os.Getenv("TLS_CERT"), os.Getenv("TLS_KEY"); cert != "" && key != "" {
		secure = &http.Server{Addr: ":8443", Handler: http.HandlerFunc(handler), ReadHeaderTimeout: 3 * time.Second, WriteTimeout: 5 * time.Second, IdleTimeout: 10 * time.Second, TLSConfig: &tls.Config{MinVersion: tls.VersionTLS12}}
		go func() { failures <- secure.ListenAndServeTLS(cert, key) }()
	}
	select {
	case <-ctx.Done():
	case err = <-failures:
	}
	shutdown, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	_ = httpServer.Shutdown(shutdown)
	if secure != nil {
		_ = secure.Shutdown(shutdown)
	}
	if errors.Is(err, http.ErrServerClosed) || errors.Is(err, net.ErrClosed) {
		return nil
	}
	return err
}

func grpcProbe(args []string) error {
	flags := flag.NewFlagSet("grpc", flag.ContinueOnError)
	target := flags.String("target", "", "VIP:port")
	name := flags.String("name", "", "TLS SNI and gRPC authority")
	ca := flags.String("ca", "", "trusted root CA file; empty only for unit tests")
	if err := flags.Parse(args); err != nil {
		return err
	}
	if *target == "" || *name == "" {
		return fmt.Errorf("target and name required")
	}
	var transport credentials.TransportCredentials = insecure.NewCredentials()
	if *ca != "" {
		pem, err := os.ReadFile(*ca)
		if err != nil {
			return err
		}
		roots := x509.NewCertPool()
		if !roots.AppendCertsFromPEM(pem) {
			return fmt.Errorf("invalid CA")
		}
		transport = credentials.NewTLS(&tls.Config{RootCAs: roots, ServerName: *name, MinVersion: tls.VersionTLS12})
	}
	connection, err := grpc.NewClient("passthrough:///"+*target, grpc.WithAuthority(*name), grpc.WithTransportCredentials(transport))
	if err != nil {
		return err
	}
	defer connection.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	var headers metadata.MD
	reply, err := healthpb.NewHealthClient(connection).Check(ctx, &healthpb.HealthCheckRequest{}, grpc.Header(&headers))
	if err != nil {
		return err
	}
	first := func(key string) string {
		if values := headers.Get(key); len(values) > 0 {
			return values[0]
		}
		return ""
	}
	if reply.Status != healthpb.HealthCheckResponse_SERVING || first("x-cnpl-uid") == "" || first("x-cnpl-pod") == "" {
		return fmt.Errorf("gRPC health or backend identity missing")
	}
	return json.NewEncoder(os.Stdout).Encode(map[string]any{"passed": true, "protocol": "grpc", "status": reply.Status.String(), "pod": first("x-cnpl-pod"), "uid": first("x-cnpl-uid"), "version": first("x-cnpl-version"), "authority": *name})
}

func main() {
	var err error
	if len(os.Args) >= 2 && os.Args[1] == "grpc" {
		err = grpcProbe(os.Args[2:])
	} else if len(os.Args) == 2 && os.Args[1] == "serve" {
		err = serve()
	} else {
		err = fmt.Errorf("usage: gateway-fixture serve | grpc --target VIP:port --name hostname --ca file")
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
