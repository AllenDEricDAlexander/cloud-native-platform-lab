// SPIRE Workload API 的真实 SVID、轮换与 mTLS；私钥仅保存在进程内存中。
package main

import (
	"context"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/spiffe/go-spiffe/v2/bundle/x509bundle"
	"github.com/spiffe/go-spiffe/v2/spiffeid"
	"github.com/spiffe/go-spiffe/v2/spiffetls/tlsconfig"
	"github.com/spiffe/go-spiffe/v2/svid/x509svid"
	"github.com/spiffe/go-spiffe/v2/workloadapi"
)

type fixedSVID struct{ svid *x509svid.SVID }

func (f fixedSVID) GetX509SVID() (*x509svid.SVID, error) { return f.svid, nil }

func metadata(svid *x509svid.SVID) map[string]any {
	cert := svid.Certificates[0]
	return map[string]any{"spiffe_id": svid.ID.String(), "serial": cert.SerialNumber.String(), "not_before": cert.NotBefore.UTC().Format(time.RFC3339), "not_after": cert.NotAfter.UTC().Format(time.RFC3339)}
}

func source(ctx context.Context) (*workloadapi.X509Source, error) {
	return workloadapi.NewX509Source(ctx, workloadapi.WithClientOptions(workloadapi.WithAddr("unix:///run/spire/sockets/agent.sock")))
}

func call(ctx context.Context, source x509svid.Source, bundles x509bundle.Source, target, serverID string) map[string]any {
	id, err := spiffeid.FromString(serverID)
	out := map[string]any{"at": time.Now().UTC().Format(time.RFC3339)}
	if err != nil {
		out["error"] = err.Error()
		return out
	}
	tlsConfig := tlsconfig.MTLSClientConfig(source, bundles, tlsconfig.AuthorizeID(id))
	transport := &http.Transport{Proxy: nil, DisableKeepAlives: true, TLSClientConfig: tlsConfig}
	defer transport.CloseIdleConnections()
	request, err := http.NewRequestWithContext(ctx, "GET", target, nil)
	if err == nil {
		nonce := fmt.Sprint(time.Now().UnixNano())
		request.Header.Set("X-Cnpl-Nonce", nonce)
		out["nonce"] = nonce
		var response *http.Response
		response, err = (&http.Client{Transport: transport, Timeout: 5 * time.Second}).Do(request)
		if err == nil {
			defer response.Body.Close()
			data, readErr := io.ReadAll(io.LimitReader(response.Body, 4096))
			err = readErr
			out["status"], out["body"] = response.StatusCode, string(data)
			if response.TLS != nil && len(response.TLS.PeerCertificates) > 0 {
				peer, peerErr := x509svid.IDFromCert(response.TLS.PeerCertificates[0])
				if peerErr == nil {
					out["peer_id"] = peer.String()
				}
			}
		}
	}
	if err != nil {
		out["error"] = err.Error()
	}
	return out
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "serve|call|watch|hold")
		os.Exit(1)
	}
	mode := os.Args[1]
	if mode == "idle" {
		time.Sleep(20 * time.Minute)
		return
	}
	duration := 100 * time.Second
	if mode == "serve" {
		duration = 24 * time.Hour
	}
	if mode == "call" {
		duration = 10 * time.Second
	}
	ctx, cancel := context.WithTimeout(context.Background(), duration)
	defer cancel()
	src, err := source(ctx)
	if err != nil {
		message := err.Error()
		class := "workload_api_error"
		if strings.Contains(strings.ToLower(message), "permissiondenied") || strings.Contains(strings.ToLower(message), "no identity") {
			class = "identity_denied"
		}
		_ = json.NewEncoder(os.Stdout).Encode(map[string]any{"error": message, "class": class})
		return
	}
	defer src.Close()
	first, err := src.GetX509SVID()
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	switch mode {
	case "watch":
		serial := first.Certificates[0].SerialNumber.String()
		rows := []map[string]any{metadata(first)}
		for i := 0; i < 90; i++ {
			time.Sleep(time.Second)
			next, err := src.GetX509SVID()
			if err != nil {
				fmt.Fprintln(os.Stderr, err)
				os.Exit(1)
			}
			if next.Certificates[0].SerialNumber.String() != serial {
				rows = append(rows, metadata(next))
				_ = json.NewEncoder(os.Stdout).Encode(map[string]any{"rotated": true, "samples": rows})
				return
			}
		}
		_ = json.NewEncoder(os.Stdout).Encode(map[string]any{"rotated": false, "samples": rows})
	case "call", "hold":
		if len(os.Args) != 4 {
			fmt.Fprintln(os.Stderr, "call|hold URL expected-server-id")
			os.Exit(1)
		}
		if mode == "call" {
			out := call(ctx, src, src, os.Args[2], os.Args[3])
			out["identity"] = metadata(first)
			_ = json.NewEncoder(os.Stdout).Encode(out)
			return
		}
		bundle, err := src.GetX509BundleForTrustDomain(first.ID.TrustDomain())
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		held := fixedSVID{first}
		bundles := x509bundle.NewSet(bundle)
		for time.Now().Before(first.Certificates[0].NotAfter.Add(5 * time.Second)) {
			out := call(ctx, held, bundles, os.Args[2], os.Args[3])
			out["identity"] = metadata(first)
			_ = json.NewEncoder(os.Stdout).Encode(out)
			time.Sleep(time.Second)
		}
	case "serve":
		allowed, err := spiffeid.FromString("spiffe://internal.egon.top/ns/lab-spire/sa/allowed")
		if err != nil {
			panic(err)
		}
		verifier, err := spiffeid.FromString("spiffe://internal.egon.top/ns/lab-spire/sa/verifier")
		if err != nil {
			panic(err)
		}
		tlsConfig := tlsconfig.MTLSServerConfig(src, src, tlsconfig.AuthorizeOneOf(allowed, verifier))
		listener, err := tls.Listen("tcp4", ":8443", tlsConfig)
		if err != nil {
			panic(err)
		}
		go func() {
			_ = http.ListenAndServe(":8080", http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if _, err := src.GetX509SVID(); err != nil {
					w.WriteHeader(503)
				} else {
					w.WriteHeader(200)
				}
			}))
		}()
		server := &http.Server{ReadHeaderTimeout: 3 * time.Second, Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			peer, err := x509svid.IDFromCert(r.TLS.PeerCertificates[0])
			if err != nil {
				http.Error(w, "identity", 403)
				return
			}
			_ = json.NewEncoder(w).Encode(map[string]string{"peer_id": peer.String(), "nonce": r.Header.Get("X-Cnpl-Nonce"), "uid": os.Getenv("POD_UID")})
		})}
		if err = server.Serve(listener); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
	default:
		fmt.Fprintln(os.Stderr, "unknown mode")
		os.Exit(1)
	}
}
