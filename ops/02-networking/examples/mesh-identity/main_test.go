package main

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"math/big"
	"net"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/hashicorp/hcl"
	"github.com/spiffe/go-spiffe/v2/bundle/x509bundle"
	"github.com/spiffe/go-spiffe/v2/proto/spiffe/workload"
	"github.com/spiffe/go-spiffe/v2/spiffeid"
	"github.com/spiffe/go-spiffe/v2/spiffetls/tlsconfig"
	"github.com/spiffe/go-spiffe/v2/svid/x509svid"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

type rejectingWorkloadAPI struct {
	workload.UnimplementedSpiffeWorkloadAPIServer
	code codes.Code
}

func (s rejectingWorkloadAPI) FetchX509SVID(*workload.X509SVIDRequest, grpc.ServerStreamingServer[workload.X509SVIDResponse]) error {
	return status.Error(s.code, "test workload response")
}

func TestSingleFetchPreservesDenialAndRejectsOtherFailures(t *testing.T) {
	for _, test := range []struct {
		code  codes.Code
		class string
	}{{codes.PermissionDenied, "identity_denied"}, {codes.Unavailable, "workload_api_error"}} {
		t.Run(test.code.String(), func(t *testing.T) {
			folder, err := os.MkdirTemp("/tmp", "cnpl-svid-")
			if err != nil {
				t.Fatal(err)
			}
			defer os.RemoveAll(folder)
			path := filepath.Join(folder, "agent.sock")
			listener, err := net.Listen("unix", path)
			if err != nil {
				t.Fatal(err)
			}
			server := grpc.NewServer()
			workload.RegisterSpiffeWorkloadAPIServer(server, rejectingWorkloadAPI{code: test.code})
			go server.Serve(listener)
			defer server.Stop()
			ctx, cancel := context.WithTimeout(context.Background(), time.Second)
			defer cancel()
			value := fetchIdentity(ctx, "unix://"+path)
			if value["class"] != test.class {
				t.Fatalf("unexpected result: %v", value)
			}
		})
	}
	if identityError(context.DeadlineExceeded)["class"] != "workload_api_error" {
		t.Fatal("a timeout must not be accepted as authorization denial")
	}
}

func testIdentity(t *testing.T, uri string, ca *x509.Certificate, caKey *ecdsa.PrivateKey) (fixedSVID, *x509.Certificate, *ecdsa.PrivateKey) {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	serial, err := rand.Int(rand.Reader, new(big.Int).Lsh(big.NewInt(1), 128))
	if err != nil {
		t.Fatal(err)
	}
	id, err := spiffeid.FromString(uri)
	if err != nil {
		t.Fatal(err)
	}
	parsed, _ := url.Parse(uri)
	template := &x509.Certificate{SerialNumber: serial, NotBefore: time.Now().Add(-time.Minute), NotAfter: time.Now().Add(time.Hour),
		URIs: []*url.URL{parsed}, KeyUsage: x509.KeyUsageDigitalSignature, ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth, x509.ExtKeyUsageClientAuth}}
	parent, signer := ca, caKey
	if ca == nil {
		template.IsCA = true
		template.BasicConstraintsValid = true
		template.KeyUsage |= x509.KeyUsageCertSign
		parent, signer = template, key
	}
	der, err := x509.CreateCertificate(rand.Reader, template, parent, &key.PublicKey, signer)
	if err != nil {
		t.Fatal(err)
	}
	cert, err := x509.ParseCertificate(der)
	if err != nil {
		t.Fatal(err)
	}
	return fixedSVID{&x509svid.SVID{ID: id, Certificates: []*x509.Certificate{cert}, PrivateKey: key}}, cert, key
}

func TestActualSPIFFEMTLSAndWrongIdentity(t *testing.T) {
	_, ca, key := testIdentity(t, "spiffe://internal.egon.top/root", nil, nil)
	server, _, _ := testIdentity(t, "spiffe://internal.egon.top/server", ca, key)
	allowed, _, _ := testIdentity(t, "spiffe://internal.egon.top/allowed", ca, key)
	bad, _, _ := testIdentity(t, "spiffe://internal.egon.top/denied", ca, key)
	bundle := x509bundle.FromX509Authorities(server.svid.ID.TrustDomain(), []*x509.Certificate{ca})
	bundles := x509bundle.NewSet(bundle)
	httpServer := httptest.NewUnstartedServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(200); _, _ = w.Write([]byte("{}")) }))
	httpServer.TLS = tlsconfig.MTLSServerConfig(server, bundles, tlsconfig.AuthorizeID(allowed.svid.ID))
	httpServer.TLS.Certificates = []tls.Certificate{{Certificate: [][]byte{server.svid.Certificates[0].Raw}, PrivateKey: server.svid.PrivateKey}}
	httpServer.StartTLS()
	defer httpServer.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	good := call(ctx, allowed, bundles, httpServer.URL, server.svid.ID.String())
	if good["status"] != 200 || good["peer_id"] != server.svid.ID.String() {
		t.Fatal(good)
	}
	denied := call(ctx, bad, bundles, httpServer.URL, server.svid.ID.String())
	if denied["error"] == nil {
		t.Fatal("unauthorized peer accepted")
	}
	wrongServer := call(ctx, allowed, bundles, httpServer.URL, "spiffe://internal.egon.top/wrong")
	if wrongServer["error"] == nil {
		t.Fatal("wrong server URI accepted")
	}
	encoded, err := json.Marshal(metadata(allowed.svid))
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(encoded), "PRIVATE") || strings.Contains(string(encoded), "private_key") {
		t.Fatal("private material in metadata")
	}
}

func TestPinnedSPIREHCLSyntax(t *testing.T) {
	for _, name := range []string{"spire-server.conf", "spire-agent.conf"} {
		data, err := os.ReadFile(filepath.Join("..", "..", "networking", "mesh", name))
		if err != nil {
			t.Fatal(err)
		}
		if _, err = hcl.Parse(string(data)); err != nil {
			t.Fatalf("%s: %v", name, err)
		}
		if strings.Contains(string(data), "audiences =") {
			t.Fatal("unsupported SPIRE PSAT field")
		}
	}
}
