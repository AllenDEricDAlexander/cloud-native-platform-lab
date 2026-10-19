// 02.05 的独立 Go TLS 客户端；只信任指定根证书，不使用系统代理。
package main

import (
	"context"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"time"
)

type config struct {
	Target, Name, CA, Path, Nonce string
}

type result struct {
	Valid       bool            `json:"tls_valid"`
	ErrorClass  string          `json:"error_class,omitempty"`
	Error       string          `json:"error,omitempty"`
	Status      int             `json:"status"`
	PeerSHA256  string          `json:"tls_peer_sha256,omitempty"`
	SPKISHA256  string          `json:"spki_sha256,omitempty"`
	ChainLength int             `json:"peer_chain_length,omitempty"`
	Body        json.RawMessage `json:"body,omitempty"`
}

func errorClass(err error) string {
	var host x509.HostnameError
	var trust x509.UnknownAuthorityError
	var validity x509.CertificateInvalidError
	switch {
	case errors.As(err, &host):
		return "hostname"
	case errors.As(err, &trust):
		return "unknown_authority"
	case errors.As(err, &validity):
		if validity.Reason == x509.Expired {
			return "validity"
		}
		return "certificate"
	default:
		return "network"
	}
}

func request(cfg config) (result, error) {
	pem, err := os.ReadFile(cfg.CA)
	if err != nil {
		return result{}, err
	}
	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(pem) {
		return result{}, fmt.Errorf("root CA file contains no certificate")
	}
	dialer := &net.Dialer{Timeout: 4 * time.Second}
	transport := &http.Transport{
		TLSClientConfig: &tls.Config{RootCAs: roots, ServerName: cfg.Name, MinVersion: tls.VersionTLS12},
		DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
			return dialer.DialContext(ctx, "tcp", cfg.Target)
		},
		DisableKeepAlives: true,
	}
	defer transport.CloseIdleConnections()
	client := &http.Client{Transport: transport, Timeout: 6 * time.Second, CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse }}
	req, err := http.NewRequest(http.MethodGet, "https://"+cfg.Name+cfg.Path, nil)
	if err != nil {
		return result{}, err
	}
	req.Header.Set("X-Cnpl-Nonce", cfg.Nonce)
	response, err := client.Do(req)
	if err != nil {
		return result{ErrorClass: errorClass(err), Error: err.Error()}, err
	}
	defer response.Body.Close()
	body, err := io.ReadAll(io.LimitReader(response.Body, 32769))
	if err != nil || len(body) > 32768 {
		return result{}, fmt.Errorf("invalid or excessive response body")
	}
	cert := response.TLS.PeerCertificates[0]
	peer := sha256.Sum256(cert.Raw)
	spki := sha256.Sum256(cert.RawSubjectPublicKeyInfo)
	value := result{Valid: true, Status: response.StatusCode, PeerSHA256: hex.EncodeToString(peer[:]), SPKISHA256: hex.EncodeToString(spki[:]), ChainLength: len(response.TLS.PeerCertificates)}
	if json.Valid(body) {
		value.Body = body
	}
	return value, nil
}

func main() {
	cfg := config{}
	flag.StringVar(&cfg.Target, "target", "", "IP:port")
	flag.StringVar(&cfg.Name, "name", "", "TLS SNI and HTTP Host")
	flag.StringVar(&cfg.CA, "ca", "", "explicit public root CA")
	flag.StringVar(&cfg.Path, "path", "/v1", "request path")
	flag.StringVar(&cfg.Nonce, "nonce", "", "unique request identity")
	flag.Parse()
	if cfg.Target == "" || cfg.Name == "" || cfg.CA == "" || cfg.Nonce == "" {
		fmt.Fprintln(os.Stderr, "target, name, ca and nonce are required")
		os.Exit(2)
	}
	value, err := request(cfg)
	_ = json.NewEncoder(os.Stdout).Encode(value)
	if err != nil {
		os.Exit(1)
	}
}
