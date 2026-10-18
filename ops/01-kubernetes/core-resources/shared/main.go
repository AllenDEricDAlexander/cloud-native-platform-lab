// 01.07–01.10 的身份、幂等任务、受控负载与配置消费者；仅依赖标准库。
package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"crypto/subtle"
	"crypto/tls"
	"crypto/x509"
	"encoding/base64"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"path/filepath"
	"runtime"
	"runtime/debug"
	"sort"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
)

func workFile(name string) string {
	base := os.Getenv("APP_WORK")
	if base == "" {
		base = "/work"
	}
	return filepath.Join(base, name)
}

func text(path string) string {
	b, err := os.ReadFile(path)
	if err != nil {
		return "absent"
	}
	return strings.TrimSpace(string(b))
}

func reply(w http.ResponseWriter, value any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(value)
}

type application struct {
	mu      sync.Mutex
	mode    string
	memory  []byte
	cpuStop chan struct{}
}

func (a *application) load(mode string) {
	a.mu.Lock()
	defer a.mu.Unlock()
	if mode == a.mode {
		return
	}
	if a.cpuStop != nil {
		close(a.cpuStop)
		a.cpuStop = nil
	}
	if mode != "memory" && mode != "hold" {
		a.memory = nil
	}
	if mode == "cpu" {
		stop := make(chan struct{})
		a.cpuStop = stop
		go func() {
			value := [32]byte{1}
			for {
				select {
				case <-stop:
					return
				default:
					value = sha256.Sum256(value[:])
				}
			}
		}()
	}
	if (mode == "memory" || mode == "hold") && a.memory == nil {
		a.memory = make([]byte, 96*1024*1024)
		for i := 0; i < len(a.memory); i += 4096 {
			a.memory[i] = 1
		}
	}
	a.mode = mode
	if mode != "memory" && mode != "hold" {
		runtime.GC()
		debug.FreeOSMemory()
	}
}

func (a *application) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	switch r.URL.Path {
	case "/ready":
		if _, err := os.Stat(workFile("not-ready")); err == nil {
			w.WriteHeader(503)
		}
		reply(w, map[string]bool{"ready": text(workFile("not-ready")) == "absent"})
	case "/live":
		reply(w, map[string]bool{"live": true})
	case "/auth":
		secret, err := os.ReadFile("/secret/value")
		if err != nil {
			http.Error(w, "credential unavailable", 503)
			return
		}
		if subtle.ConstantTimeCompare(secret, []byte(r.Header.Get("X-Lab-Secret"))) != 1 {
			http.Error(w, "unauthorized", 401)
			return
		}
		reply(w, map[string]bool{"authorized": true})
	case "/identity":
		a.mu.Lock()
		mode := a.mode
		a.mu.Unlock()
		reply(w, map[string]any{"pod": os.Getenv("POD_NAME"), "uid": os.Getenv("POD_UID"), "version": os.Getenv("APP_VERSION"),
			"local": text(workFile("local")), "env": os.Getenv("APP_CONFIG"), "volume": text("/config/value"), "subpath": text("/subpath/value"), "load": mode})
	default:
		http.NotFound(w, r)
	}
}

func serve() error {
	runtime.GOMAXPROCS(1)
	if _, err := os.Stat(workFile("local")); os.IsNotExist(err) {
		if err = os.WriteFile(workFile("local"), []byte(os.Getenv("POD_UID")), 0600); err != nil {
			return err
		}
	}
	if ordinal := os.Getenv("BLOCK_ORDINAL"); ordinal != "" && strings.HasSuffix(os.Getenv("POD_NAME"), "-"+ordinal) {
		if err := os.WriteFile(workFile("not-ready"), []byte("initial block"), 0600); err != nil {
			return err
		}
	}
	a := &application{}
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer stop()
	go func() {
		for {
			a.load(text("/load/mode"))
			select {
			case <-ctx.Done():
				a.load("off")
				return
			case <-time.After(time.Second):
			}
		}
	}()
	server := &http.Server{Addr: ":8080", Handler: a, ReadHeaderTimeout: 3 * time.Second}
	go func() {
		<-ctx.Done()
		shutdown, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = server.Shutdown(shutdown)
	}()
	log.Printf("START pod=%s uid=%s version=%s", os.Getenv("POD_NAME"), os.Getenv("POD_UID"), os.Getenv("APP_VERSION"))
	err := server.ListenAndServe()
	if err == http.ErrServerClosed {
		return nil
	}
	return err
}

type apiClient struct {
	client                 *http.Client
	base, namespace, token string
}

func clusterClient() (*apiClient, error) {
	ca, err := os.ReadFile("/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")
	if err != nil {
		return nil, err
	}
	pool := x509.NewCertPool()
	if !pool.AppendCertsFromPEM(ca) {
		return nil, fmt.Errorf("invalid API CA")
	}
	token, _ := os.ReadFile("/var/run/secrets/kubernetes.io/serviceaccount/token")
	ns := os.Getenv("POD_NAMESPACE")
	if ns == "" {
		return nil, fmt.Errorf("missing namespace")
	}
	return &apiClient{client: &http.Client{Timeout: 5 * time.Second, Transport: &http.Transport{Proxy: nil, TLSClientConfig: &tls.Config{RootCAs: pool, MinVersion: tls.VersionTLS12}}},
		base: "https://" + net.JoinHostPort(os.Getenv("KUBERNETES_SERVICE_HOST"), "443"), namespace: ns, token: strings.TrimSpace(string(token))}, nil
}

func (c *apiClient) request(method, path string, value any) (int, []byte, error) {
	var body []byte
	var err error
	if value != nil {
		body, err = json.Marshal(value)
		if err != nil {
			return 0, nil, err
		}
	}
	r, err := http.NewRequest(method, c.base+path, bytes.NewReader(body))
	if err != nil {
		return 0, nil, err
	}
	if c.token != "" {
		r.Header.Set("Authorization", "Bearer "+c.token)
	}
	r.Header.Set("Content-Type", "application/json")
	response, err := c.client.Do(r)
	if err != nil {
		return 0, nil, err
	}
	defer response.Body.Close()
	data, err := io.ReadAll(io.LimitReader(response.Body, 1024*1024))
	return response.StatusCode, data, err
}

// ConfigMap resourceVersion 提供测试账本的原子提交；冲突重读，不把重试当作再次产生效果。
func (c *apiClient) commit(ledger, key string) (bool, error) {
	path := "/api/v1/namespaces/" + url.PathEscape(c.namespace) + "/configmaps/" + url.PathEscape(ledger)
	for i := 0; i < 20; i++ {
		status, raw, err := c.request(http.MethodGet, path, nil)
		if err != nil {
			return false, err
		}
		if status != 200 {
			return false, fmt.Errorf("ledger GET HTTP %d", status)
		}
		var object map[string]any
		if err = json.Unmarshal(raw, &object); err != nil {
			return false, err
		}
		metadata, _ := object["metadata"].(map[string]any)
		labels, _ := metadata["labels"].(map[string]any)
		if labels["cnpl.io/core-run"] != os.Getenv("CORE_RUN") {
			return false, fmt.Errorf("ledger ownership mismatch")
		}
		data, _ := object["data"].(map[string]any)
		if data == nil {
			data = map[string]any{}
		}
		if value, found := data[key]; found {
			if value != "1" {
				return false, fmt.Errorf("duplicate or invalid effect")
			}
			return false, nil
		}
		data[key] = "1"
		object["data"] = data
		status, _, err = c.request(http.MethodPut, path, object)
		if err != nil {
			return false, err
		}
		if status == 409 {
			continue
		}
		if status != 200 {
			return false, fmt.Errorf("ledger PUT HTTP %d", status)
		}
		return true, nil
	}
	return false, fmt.Errorf("ledger conflicts exceeded bounded retries")
}

func api(args []string) error {
	if len(args) != 3 || (args[0] != "GET" && args[0] != "DELETE") {
		return fmt.Errorf("api METHOD PATH EXPECTED_CODES required")
	}
	c, err := clusterClient()
	if err != nil {
		return err
	}
	prefix := "/api/v1/namespaces/" + url.PathEscape(c.namespace) + "/"
	allowedRead := args[1] == "/api/v1/nodes" || args[1] == "/api/v1/namespaces/lab-core/pods" || args[1] == "/api/v1/namespaces/lab-core/configmaps/p10-config"
	if !strings.HasPrefix(args[1], prefix) && !(args[0] == "GET" && allowedRead) {
		return fmt.Errorf("API request outside experiment scope")
	}
	status, _, err := c.request(args[0], args[1], nil)
	if err != nil {
		return err
	}
	matched := false
	for _, value := range strings.Split(args[2], ",") {
		if value == strconv.Itoa(status) {
			matched = true
		}
	}
	if !matched {
		return fmt.Errorf("unexpected API status %d", status)
	}
	result := map[string]any{"status": status, "method": args[0], "token_mounted": c.token != ""}
	if fields := strings.Split(c.token, "."); len(fields) == 3 {
		if payload, e := base64.RawURLEncoding.DecodeString(fields[1]); e == nil {
			var claims map[string]any
			if json.Unmarshal(payload, &claims) == nil {
				result["audience"] = claims["aud"]
				result["expires_at"] = claims["exp"]
			}
		}
	}
	return json.NewEncoder(os.Stdout).Encode(result)
}

func run(args []string) (int, error) {
	if len(args) == 0 {
		return 1, fmt.Errorf("command required")
	}
	switch args[0] {
	case "serve":
		return 0, serve()
	case "identity":
		client := &http.Client{Timeout: 3 * time.Second, Transport: &http.Transport{Proxy: nil}}
		r, err := client.Get("http://127.0.0.1:8080/identity")
		if err != nil {
			return 1, err
		}
		defer r.Body.Close()
		if r.StatusCode != 200 {
			return 1, fmt.Errorf("identity HTTP %d", r.StatusCode)
		}
		_, err = io.Copy(os.Stdout, r.Body)
		return 0, err
	case "ready":
		if len(args) != 2 || (args[1] != "true" && args[1] != "false") {
			return 1, fmt.Errorf("ready true|false required")
		}
		if args[1] == "false" {
			return 0, os.WriteFile(workFile("not-ready"), []byte("blocked"), 0600)
		}
		err := os.Remove(workFile("not-ready"))
		if os.IsNotExist(err) {
			err = nil
		}
		return 0, err
	case "local":
		if len(args) != 2 || len(args[1]) > 200 {
			return 1, fmt.Errorf("bounded local value required")
		}
		return 0, os.WriteFile(workFile("local"), []byte(args[1]), 0600)
	case "dns":
		if len(args) != 2 || !strings.HasSuffix(args[1], ".svc.cluster.local") {
			return 1, fmt.Errorf("cluster.local name required")
		}
		ips, err := net.LookupHost(args[1])
		if err != nil {
			return 1, err
		}
		sort.Strings(ips)
		return 0, json.NewEncoder(os.Stdout).Encode(map[string]any{"name": args[1], "ips": ips})
	case "api":
		return 0, api(args[1:])
	case "job":
		if len(args) > 1 && args[1] == "permanent" {
			return 42, nil
		}
		c, err := clusterClient()
		if err != nil {
			return 1, err
		}
		key := "business-" + os.Getenv("JOB_COMPLETION_INDEX")
		first, err := c.commit("p09-ledger", key)
		if err != nil {
			return 1, err
		}
		log.Printf("COMMIT key=%s effects=1 first=%t", key, first)
		if first {
			return 7, nil
		}
		return 0, nil
	case "sleep":
		if len(args) != 2 {
			return 1, fmt.Errorf("sleep seconds required")
		}
		n, err := strconv.Atoi(args[1])
		if err != nil || n < 1 || n > 180 {
			return 1, fmt.Errorf("sleep outside 1..180")
		}
		time.Sleep(time.Duration(n) * time.Second)
		return 0, nil
	case "secret-match":
		if len(args) != 2 {
			return 1, fmt.Errorf("expected boolean required")
		}
		value, err := os.ReadFile("/secret/value")
		if err != nil {
			return 1, err
		}
		expected, err := strconv.ParseBool(args[1])
		if err != nil {
			return 1, err
		}
		matches := subtle.ConstantTimeCompare(value, []byte(os.Getenv("SECRET_VALUE"))) == 1
		if matches != expected {
			return 1, fmt.Errorf("secret refresh condition not met")
		}
		fmt.Printf("SECRET CHECK PASS match=%t\n", matches)
		return 0, nil
	case "auth-check":
		secret, err := os.ReadFile("/secret/value")
		if err != nil {
			return 1, err
		}
		client := &http.Client{Timeout: 3 * time.Second, Transport: &http.Transport{Proxy: nil}}
		for i, value := range []string{string(secret), "intentionally-invalid"} {
			r, err := http.NewRequest("GET", "http://127.0.0.1:8080/auth", nil)
			if err != nil {
				return 1, err
			}
			r.Header.Set("X-Lab-Secret", value)
			response, err := client.Do(r)
			if err != nil {
				return 1, err
			}
			_, _ = io.Copy(io.Discard, response.Body)
			response.Body.Close()
			expected := 200
			if i == 1 {
				expected = 401
			}
			if response.StatusCode != expected {
				return 1, fmt.Errorf("authentication contrast failed")
			}
		}
		fmt.Println("AUTHENTICATION CHECK PASS")
		return 0, nil
	case "tls-check":
		pair, err := tls.LoadX509KeyPair("/tls/tls.crt", "/tls/tls.key")
		if err != nil {
			return 1, fmt.Errorf("TLS pair invalid")
		}
		cert, err := x509.ParseCertificate(pair.Certificate[0])
		if err != nil {
			return 1, err
		}
		ca, err := os.ReadFile("/tls/ca.crt")
		if err != nil {
			return 1, err
		}
		pool := x509.NewCertPool()
		if block, _ := pem.Decode(ca); block == nil || !pool.AppendCertsFromPEM(ca) {
			return 1, fmt.Errorf("TLS CA invalid")
		}
		_, err = cert.Verify(x509.VerifyOptions{Roots: pool, DNSName: os.Getenv("TLS_NAME")})
		if err != nil {
			return 1, err
		}
		fmt.Println("TLS CHECK PASS")
		return 0, nil
	default:
		return 1, fmt.Errorf("unsupported command")
	}
}

func main() {
	code, err := run(os.Args[1:])
	if err != nil {
		log.Print(err)
		if code == 0 {
			code = 1
		}
	}
	os.Exit(code)
}
