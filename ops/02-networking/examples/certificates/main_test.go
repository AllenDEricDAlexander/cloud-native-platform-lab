package main

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"fmt"
	"math/big"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func certificate(t *testing.T, root *x509.Certificate, rootKey *ecdsa.PrivateKey, expired bool) tls.Certificate {
	t.Helper()
	key, _ := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	template := &x509.Certificate{SerialNumber: big.NewInt(2), DNSNames: []string{"demo.svc.internal.egon.top"}, NotBefore: time.Now().Add(-2 * time.Hour), NotAfter: time.Now().Add(time.Hour), KeyUsage: x509.KeyUsageDigitalSignature, ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}}
	if expired {
		template.NotAfter = time.Now().Add(-time.Hour)
	}
	der, err := x509.CreateCertificate(rand.Reader, template, root, key.Public(), rootKey)
	if err != nil {
		t.Fatal(err)
	}
	return tls.Certificate{Certificate: [][]byte{der}, PrivateKey: key}
}

func TestRealTLSValidationAndIdentity(t *testing.T) {
	rootKey, _ := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	template := &x509.Certificate{SerialNumber: big.NewInt(1), Subject: pkix.Name{CommonName: "isolated root"}, NotBefore: time.Now().Add(-24 * time.Hour), NotAfter: time.Now().Add(24 * time.Hour), IsCA: true, BasicConstraintsValid: true, KeyUsage: x509.KeyUsageCertSign}
	der, _ := x509.CreateCertificate(rand.Reader, template, template, rootKey.Public(), rootKey)
	root, _ := x509.ParseCertificate(der)
	path := filepath.Join(t.TempDir(), "root.crt")
	_ = os.WriteFile(path, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der}), 0o600)
	for _, row := range []struct {
		name, sni, want string
		expired         bool
	}{{"valid", "demo.svc.internal.egon.top", "", false}, {"SAN", "wrong.svc.internal.egon.top", "hostname", false}, {"expired", "demo.svc.internal.egon.top", "validity", true}} {
		t.Run(row.name, func(t *testing.T) {
			server := httptest.NewUnstartedServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				_, _ = fmt.Fprintf(w, "{\"nonce\":%q,\"uid\":\"backend\"}", r.Header.Get("X-Cnpl-Nonce"))
			}))
			server.TLS = &tls.Config{Certificates: []tls.Certificate{certificate(t, root, rootKey, row.expired)}}
			server.StartTLS()
			defer server.Close()
			value, err := request(config{Target: server.Listener.Addr().String(), Name: row.sni, CA: path, Path: "/v1", Nonce: "unique"})
			if row.want == "" {
				if err != nil || !value.Valid || value.Status != 200 || !strings.Contains(string(value.Body), "unique") || value.PeerSHA256 == "" {
					t.Fatalf("wrong verified result: %+v %v", value, err)
				}
			} else if err == nil || value.Valid || value.ErrorClass != row.want {
				t.Fatalf("wrong TLS rejection: %+v %v", value, err)
			}
		})
	}
	t.Run("untrusted", func(t *testing.T) {
		server := httptest.NewTLSServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {}))
		defer server.Close()
		value, err := request(config{Target: server.Listener.Addr().String(), Name: "example.com", CA: path, Path: "/v1", Nonce: "unique"})
		if err == nil || value.Valid || value.ErrorClass != "unknown_authority" {
			t.Fatalf("untrusted server accepted: %+v %v", value, err)
		}
	})
}
