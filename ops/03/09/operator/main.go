// DemoApp 是单 namespace、单副本的教学控制器；只使用 Go 标准库。
package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"reflect"
	"regexp"
	"strconv"
	"strings"
	"syscall"
	"time"
	"unicode/utf8"
)

type object = map[string]any

const finalizer = "lab.egon.top/demoapp-cleanup"

type apiError struct{ status int }

func (e *apiError) Error() string { return fmt.Sprintf("Kubernetes API HTTP %d", e.status) }
func isStatus(err error, status int) bool {
	var e *apiError
	return errors.As(err, &e) && e.status == status
}

type client struct {
	base, namespace, tokenFile string
	http                       *http.Client
}

func (c *client) request(ctx context.Context, method, path string, body any, patch bool) (object, error) {
	var input io.Reader
	if body != nil {
		data, err := json.Marshal(body)
		if err != nil {
			return nil, err
		}
		input = bytes.NewReader(data)
	}
	req, err := http.NewRequestWithContext(ctx, method, c.base+path, input)
	if err != nil {
		return nil, err
	}
	if c.tokenFile != "" {
		// 每次读取投射 token，支持 kubelet 轮换；不记录请求头或响应体。
		token, err := os.ReadFile(c.tokenFile)
		if err != nil {
			return nil, fmt.Errorf("read service account token: %w", err)
		}
		req.Header.Set("Authorization", "Bearer "+strings.TrimSpace(string(token)))
	}
	content := "application/json"
	if patch {
		content = "application/merge-patch+json"
	}
	req.Header.Set("Content-Type", content)
	resp, err := c.http.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, &apiError{resp.StatusCode}
	}
	data, err := io.ReadAll(io.LimitReader(resp.Body, 4*1024*1024+1))
	if err != nil {
		return nil, err
	}
	if len(data) > 4*1024*1024 {
		return nil, errors.New("API response too large")
	}
	if len(bytes.TrimSpace(data)) == 0 {
		return object{}, nil
	}
	var result object
	err = json.Unmarshal(data, &result)
	return result, err
}

func field(o object, key string) object {
	m, _ := o[key].(map[string]any)
	if m == nil {
		m = object{}
		o[key] = m
	}
	return m
}
func text(o object, key string) string { v, _ := o[key].(string); return v }
func number(o object, key string) int  { v, _ := o[key].(float64); return int(v) }
func list(o object, key string) []any  { v, _ := o[key].([]any); return v }
func copyObject(o object) object {
	b, _ := json.Marshal(o)
	var clone object
	_ = json.Unmarshal(b, &clone)
	return clone
}

// 仅合并本控制器声明的字段；保留 API 默认值和 Service 已分配的地址。
// 容器/端口/卷按 name 匹配，避免每轮因默认字段再次写入。
func mergeControlled(current, desired object) {
	for key, value := range desired {
		switch wanted := value.(type) {
		case map[string]any:
			mergeControlled(field(current, key), wanted)
		case []any:
			old, _ := current[key].([]any)
			out := make([]any, 0, len(wanted))
			for _, element := range wanted {
				m, named := element.(map[string]any)
				if !named || text(m, "name") == "" {
					out = append(out, element)
					continue
				}
				merged := object{}
				for _, prev := range old {
					p, ok := prev.(map[string]any)
					if ok && text(p, "name") == text(m, "name") {
						merged = copyObject(p)
						break
					}
				}
				mergeControlled(merged, m)
				out = append(out, merged)
			}
			current[key] = out
		default:
			current[key] = value
		}
	}
}

var imagePattern = regexp.MustCompile(`^harbor\.k8s\.internal\.egon\.top/[a-zA-Z0-9_./-]+@sha256:[0-9a-f]{64}$`)
var namePattern = regexp.MustCompile(`^[a-z0-9]([a-z0-9-]{0,48}[a-z0-9])?$`)

func validate(app object) error {
	meta, spec := field(app, "metadata"), field(app, "spec")
	if !namePattern.MatchString(text(meta, "name")) || text(meta, "uid") == "" {
		return errors.New("name must be a DNS label of at most 50 characters and UID is required")
	}
	if !imagePattern.MatchString(text(spec, "image")) {
		return errors.New("image must use the internal registry and a SHA256 digest")
	}
	if number(spec, "replicas") < 1 || number(spec, "replicas") > 5 {
		return errors.New("replicas must be between 1 and 5")
	}
	if number(spec, "port") < 1024 || number(spec, "port") > 65535 {
		return errors.New("port must be between 1024 and 65535")
	}
	if utf8.RuneCountInString(text(spec, "message")) > 1024 {
		return errors.New("message exceeds 1024 characters")
	}
	return nil
}

func owned(child, app object) bool {
	uid := text(field(app, "metadata"), "uid")
	for _, value := range list(field(child, "metadata"), "ownerReferences") {
		owner, ok := value.(map[string]any)
		if ok && text(owner, "uid") == uid && owner["controller"] == true && text(owner, "kind") == "DemoApp" && text(owner, "apiVersion") == "lab.egon.top/v1alpha1" {
			return true
		}
	}
	return false
}

func (c *client) children(app object) []object {
	meta, spec := field(app, "metadata"), field(app, "spec")
	name, uid := text(meta, "name"), text(meta, "uid")
	labels := object{"lab.egon.top/demoapp-uid": uid}
	owner := []any{object{"apiVersion": "lab.egon.top/v1alpha1", "kind": "DemoApp", "name": name, "uid": uid, "controller": true, "blockOwnerDeletion": false}}
	metadata := func() object {
		return object{"name": name, "namespace": c.namespace, "labels": copyObject(labels), "ownerReferences": owner}
	}
	message := text(spec, "message")
	hash := sha256.Sum256([]byte(message))
	port := spec["port"]
	cm := object{"apiVersion": "v1", "kind": "ConfigMap", "metadata": metadata(), "data": object{"message": message}}
	service := object{"apiVersion": "v1", "kind": "Service", "metadata": metadata(), "spec": object{"selector": labels, "ports": []any{object{"name": "http", "port": port, "targetPort": "http"}}}}
	deployment := object{"apiVersion": "apps/v1", "kind": "Deployment", "metadata": metadata(), "spec": object{
		"replicas": spec["replicas"], "selector": object{"matchLabels": labels}, "template": object{
			"metadata": object{"labels": labels, "annotations": object{"lab.egon.top/config-sha256": hex.EncodeToString(hash[:])}},
			"spec": object{"securityContext": object{"runAsNonRoot": true, "runAsUser": float64(10001)}, "containers": []any{object{
				"name": "app", "image": spec["image"], "ports": []any{object{"name": "http", "containerPort": port}},
				"env":             []any{object{"name": "PORT", "value": strconv.Itoa(number(spec, "port"))}, object{"name": "DEMO_MESSAGE", "valueFrom": object{"configMapKeyRef": object{"name": name, "key": "message"}}}},
				"readinessProbe":  object{"tcpSocket": object{"port": "http"}, "periodSeconds": float64(5)},
				"resources":       object{"requests": object{"cpu": "10m", "memory": "32Mi"}, "limits": object{"memory": "128Mi"}},
				"securityContext": object{"allowPrivilegeEscalation": false, "readOnlyRootFilesystem": true, "capabilities": object{"drop": []any{"ALL"}}},
			}}},
		},
	}}
	return []object{cm, service, deployment}
}

func (c *client) collection(kind string) string {
	base := "/api/v1/namespaces/" + url.PathEscape(c.namespace)
	switch kind {
	case "Deployment":
		return "/apis/apps/v1/namespaces/" + url.PathEscape(c.namespace) + "/deployments"
	case "Service":
		return base + "/services"
	case "ConfigMap":
		return base + "/configmaps"
	default:
		panic("unsupported controlled kind")
	}
}
func (c *client) appPath(app object) string {
	return "/apis/lab.egon.top/v1alpha1/namespaces/" + url.PathEscape(c.namespace) + "/demoapps/" + url.PathEscape(text(field(app, "metadata"), "name"))
}

func (c *client) ensure(ctx context.Context, app, desired object) (object, error) {
	collection := c.collection(text(desired, "kind"))
	path := collection + "/" + url.PathEscape(text(field(desired, "metadata"), "name"))
	existing, err := c.request(ctx, "GET", path, nil, false)
	if isStatus(err, 404) {
		return c.request(ctx, "POST", collection, desired, false)
	}
	if err != nil {
		return nil, err
	}
	if !owned(existing, app) {
		return nil, errors.New("OwnershipConflict: existing child belongs to another owner")
	}
	if text(field(existing, "metadata"), "deletionTimestamp") != "" {
		return nil, errors.New("child deletion still pending")
	}
	updated := copyObject(existing)
	mergeControlled(updated, desired)
	if reflect.DeepEqual(existing, updated) {
		return existing, nil
	}
	return c.request(ctx, "PUT", path, updated, false)
}

func statusFor(app object, ready int, healthy bool, reason, message string, now time.Time) object {
	state := "False"
	if healthy {
		state = "True"
	}
	transition := now.UTC().Format(time.RFC3339)
	for _, value := range list(field(app, "status"), "conditions") {
		cond, ok := value.(map[string]any)
		if ok && text(cond, "type") == "Ready" && text(cond, "status") == state && text(cond, "lastTransitionTime") != "" {
			transition = text(cond, "lastTransitionTime")
		}
	}
	return object{"observedGeneration": field(app, "metadata")["generation"], "readyReplicas": float64(ready), "conditions": []any{object{"type": "Ready", "status": state, "reason": reason, "message": message, "lastTransitionTime": transition}}}
}
func (c *client) status(ctx context.Context, app object, ready int, healthy bool, reason, message string) error {
	wanted := statusFor(app, ready, healthy, reason, message, time.Now())
	if reflect.DeepEqual(field(app, "status"), wanted) {
		return nil
	}
	_, err := c.request(ctx, "PATCH", c.appPath(app)+"/status", object{"metadata": object{"resourceVersion": field(app, "metadata")["resourceVersion"]}, "status": wanted}, true)
	return err
}
func (c *client) finalizers(ctx context.Context, app object, values []any) error {
	_, err := c.request(ctx, "PATCH", c.appPath(app), object{"metadata": object{"resourceVersion": field(app, "metadata")["resourceVersion"], "finalizers": values}}, true)
	return err
}

func (c *client) reconcile(ctx context.Context, app object) error {
	meta := field(app, "metadata")
	// 删除路径不依赖有效 spec，避免升级后旧对象因校验变化永久卡住。
	if text(meta, "deletionTimestamp") != "" {
		pending := false
		for _, kind := range []string{"Deployment", "Service", "ConfigMap"} {
			path := c.collection(kind) + "/" + url.PathEscape(text(meta, "name"))
			child, err := c.request(ctx, "GET", path, nil, false)
			if isStatus(err, 404) {
				continue
			}
			if err != nil {
				return err
			}
			if !owned(child, app) {
				return c.status(ctx, app, 0, false, "OwnershipConflict", "Cleanup blocked by a child with another owner")
			}
			pending = true
			if text(field(child, "metadata"), "deletionTimestamp") == "" {
				_, err = c.request(ctx, "DELETE", path, object{"apiVersion": "v1", "kind": "DeleteOptions", "propagationPolicy": "Foreground", "preconditions": object{"uid": field(child, "metadata")["uid"]}}, false)
				if err != nil && !isStatus(err, 404) {
					return err
				}
			}
		}
		if pending {
			return nil
		}
		kept := []any{}
		found := false
		for _, value := range list(meta, "finalizers") {
			if value == finalizer {
				found = true
			} else {
				kept = append(kept, value)
			}
		}
		if found {
			return c.finalizers(ctx, app, kept)
		}
		return nil
	}
	if err := validate(app); err != nil {
		return c.status(ctx, app, 0, false, "InvalidSpec", err.Error())
	}
	values := list(meta, "finalizers")
	found := false
	for _, value := range values {
		if value == finalizer {
			found = true
		}
	}
	if !found {
		return c.finalizers(ctx, app, append(values, finalizer))
	}
	ready := 0
	for _, desired := range c.children(app) {
		actual, err := c.ensure(ctx, app, desired)
		if err != nil {
			reason := "APIError"
			if isStatus(err, 403) {
				reason = "AccessDenied"
			}
			if strings.HasPrefix(err.Error(), "OwnershipConflict:") {
				reason = "OwnershipConflict"
			}
			if isStatus(err, 409) {
				return err
			}
			return c.status(ctx, app, 0, false, reason, err.Error())
		}
		if text(desired, "kind") == "Deployment" && number(field(actual, "status"), "observedGeneration") >= number(field(actual, "metadata"), "generation") {
			ready = number(field(actual, "status"), "availableReplicas")
		}
	}
	wanted := number(field(app, "spec"), "replicas")
	if ready == wanted {
		return c.status(ctx, app, ready, true, "ResourcesReady", "Owned children are ready")
	}
	return c.status(ctx, app, ready, false, "Reconciling", "Waiting for owned Deployment replicas")
}

func (c *client) once(ctx context.Context) error {
	continuation := ""
	for {
		path := "/apis/lab.egon.top/v1alpha1/namespaces/" + url.PathEscape(c.namespace) + "/demoapps?limit=200"
		if continuation != "" {
			path += "&continue=" + url.QueryEscape(continuation)
		}
		apps, err := c.request(ctx, "GET", path, nil, false)
		if err != nil {
			return err
		}
		for _, value := range list(apps, "items") {
			app, ok := value.(map[string]any)
			if !ok {
				return errors.New("invalid DemoApp list item")
			}
			if err := c.reconcile(ctx, app); err != nil {
				log.Printf("reconcile %s: %v", text(field(app, "metadata"), "name"), err)
			}
		}
		continuation = text(field(apps, "metadata"), "continue")
		if continuation == "" {
			return nil
		}
	}
}

func inCluster() (*client, error) {
	ns := os.Getenv("POD_NAMESPACE")
	if ns == "" {
		return nil, errors.New("POD_NAMESPACE is required")
	}
	ca, err := os.ReadFile("/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")
	if err != nil {
		return nil, err
	}
	pool := x509.NewCertPool()
	if !pool.AppendCertsFromPEM(ca) {
		return nil, errors.New("invalid API CA")
	}
	host, port := os.Getenv("KUBERNETES_SERVICE_HOST"), os.Getenv("KUBERNETES_SERVICE_PORT_HTTPS")
	if host == "" {
		return nil, errors.New("Kubernetes service host is required")
	}
	if port == "" {
		port = "443"
	}
	return &client{base: "https://" + net.JoinHostPort(host, port), namespace: ns, tokenFile: "/var/run/secrets/kubernetes.io/serviceaccount/token", http: &http.Client{Timeout: 15 * time.Second, Transport: &http.Transport{TLSClientConfig: &tls.Config{RootCAs: pool, MinVersion: tls.VersionTLS12}}}}, nil
}

func main() {
	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer cancel()
	c, err := inCluster()
	if err != nil {
		log.Fatal(err)
	}
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()
	for {
		if err := c.once(ctx); err != nil && ctx.Err() == nil {
			log.Printf("list DemoApps: %v", err)
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}
