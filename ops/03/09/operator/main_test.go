package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"reflect"
	"strings"
	"testing"
	"time"
)

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

type memoryAPI struct {
	objects       map[string]object
	writes        int
	blockedPath   string
	blockedStatus int
	lastDelete    object
}

func response(code int, value object) *http.Response {
	data, _ := json.Marshal(value)
	return &http.Response{StatusCode: code, Body: io.NopCloser(bytes.NewReader(data)), Header: http.Header{}}
}
func (f *memoryAPI) RoundTrip(req *http.Request) (*http.Response, error) {
	path := req.URL.Path
	if path == f.blockedPath {
		return response(f.blockedStatus, object{}), nil
	}
	old, found := f.objects[path]
	if req.Method == "GET" {
		if !found {
			return response(404, object{}), nil
		}
		return response(200, copyObject(old)), nil
	}
	var value object
	if req.Body != nil {
		_ = json.NewDecoder(req.Body).Decode(&value)
	}
	if req.Method == "DELETE" {
		f.lastDelete = value
		if !found {
			return response(404, object{}), nil
		}
		if field(value, "preconditions")["uid"] != field(old, "metadata")["uid"] {
			return response(409, object{}), nil
		}
		delete(f.objects, path)
		f.writes++
		return response(200, object{}), nil
	}
	if req.Method == "POST" {
		path += "/" + text(field(value, "metadata"), "name")
		if _, exists := f.objects[path]; exists {
			return response(409, object{}), nil
		}
		f.writes++
		field(value, "metadata")["uid"] = fmt.Sprintf("child-%d", f.writes)
		field(value, "metadata")["resourceVersion"] = fmt.Sprint(f.writes)
		field(value, "metadata")["generation"] = float64(1)
		if text(value, "kind") == "Service" {
			field(value, "spec")["clusterIP"] = "192.168.20.77"
		}
		if text(value, "kind") == "Deployment" {
			pod := field(field(field(value, "spec"), "template"), "spec")
			pod["dnsPolicy"] = "ClusterFirst"
			container := list(pod, "containers")[0].(map[string]any)
			container["terminationMessagePolicy"] = "File"
		}
		f.objects[path] = copyObject(value)
		return response(201, value), nil
	}
	basePath := strings.TrimSuffix(path, "/status")
	if req.Method == "PATCH" {
		old, found = f.objects[basePath]
	}
	if !found {
		return response(404, object{}), nil
	}
	if text(field(value, "metadata"), "resourceVersion") != text(field(old, "metadata"), "resourceVersion") {
		return response(409, object{}), nil
	}
	if req.Method == "PUT" {
		old = value
	} else {
		mergeControlled(old, value)
	}
	f.writes++
	field(old, "metadata")["resourceVersion"] = fmt.Sprint(f.writes)
	f.objects[basePath] = copyObject(old)
	return response(200, old), nil
}
func setup() (*client, *memoryAPI, string) {
	f := &memoryAPI{objects: map[string]object{}}
	c := &client{base: "https://api.invalid", namespace: "cnpl03-09", http: &http.Client{Transport: f}}
	app := object{"apiVersion": "lab.egon.top/v1alpha1", "kind": "DemoApp", "metadata": object{"name": "demo", "uid": "owner-uid", "generation": float64(1), "resourceVersion": "initial", "finalizers": []any{finalizer}}, "spec": object{"image": "harbor.k8s.internal.egon.top/lab/app@sha256:" + strings.Repeat("a", 64), "replicas": float64(2), "port": float64(8080), "message": "hello"}}
	path := c.appPath(app)
	f.objects[path] = copyObject(app)
	return c, f, path
}
func reconcile(t *testing.T, c *client, f *memoryAPI, path string) {
	t.Helper()
	if err := c.reconcile(context.Background(), copyObject(f.objects[path])); err != nil {
		t.Fatal(err)
	}
}

func TestRepeatedReconcilePreservesAPIDefaults(t *testing.T) {
	c, f, path := setup()
	reconcile(t, c, f, path)
	dep := f.objects[c.collection("Deployment")+"/demo"]
	dep["status"] = object{"availableReplicas": float64(2), "observedGeneration": float64(1)}
	reconcile(t, c, f, path)
	writes := f.writes
	for range 5 {
		reconcile(t, c, f, path)
	}
	if f.writes != writes {
		t.Fatalf("unchanged state caused writes: %d -> %d", writes, f.writes)
	}
	service := f.objects[c.collection("Service")+"/demo"]
	if text(field(service, "spec"), "clusterIP") != "192.168.20.77" {
		t.Fatal("lost Service address")
	}
}
func TestInvalidSpecProducesConditionWithoutChildren(t *testing.T) {
	c, f, path := setup()
	field(f.objects[path], "spec")["replicas"] = float64(0)
	reconcile(t, c, f, path)
	cond := list(field(f.objects[path], "status"), "conditions")[0].(map[string]any)
	if text(cond, "reason") != "InvalidSpec" || len(f.objects) != 1 {
		t.Fatal("invalid resource was deployed")
	}
}
func TestRejectsForeignOwner(t *testing.T) {
	c, f, path := setup()
	child := c.children(f.objects[path])[0]
	list(field(child, "metadata"), "ownerReferences")[0].(map[string]any)["uid"] = "someone-else"
	f.objects[c.collection("ConfigMap")+"/demo"] = copyObject(child)
	reconcile(t, c, f, path)
	if !reflect.DeepEqual(f.objects[c.collection("ConfigMap")+"/demo"], child) {
		t.Fatal("adopted foreign child")
	}
	cond := list(field(f.objects[path], "status"), "conditions")[0].(map[string]any)
	if text(cond, "reason") != "OwnershipConflict" {
		t.Fatal("missing ownership condition")
	}
}
func TestPermissionDeniedIsVisibleAndDoesNotOverwriteChildren(t *testing.T) {
	c, f, path := setup()
	f.blockedPath = c.collection("ConfigMap") + "/demo"
	f.blockedStatus = 403
	reconcile(t, c, f, path)
	cond := list(field(f.objects[path], "status"), "conditions")[0].(map[string]any)
	if text(cond, "reason") != "AccessDenied" || len(f.objects) != 1 {
		t.Fatal("permission failure lost")
	}
}
func TestTransientPartialFailureConverges(t *testing.T) {
	c, f, path := setup()
	f.blockedPath = c.collection("Deployment") + "/demo"
	f.blockedStatus = 503
	reconcile(t, c, f, path)
	if len(f.objects) != 3 {
		t.Fatal("expected two successfully created children")
	}
	f.blockedPath = ""
	reconcile(t, c, f, path)
	if len(f.objects) != 4 {
		t.Fatal("failed to resume partial work")
	}
}
func TestConfigChangeUpdatesRolloutAndImage(t *testing.T) {
	c, f, path := setup()
	reconcile(t, c, f, path)
	depPath := c.collection("Deployment") + "/demo"
	oldTemplate := copyObject(field(field(f.objects[depPath], "spec"), "template"))
	field(f.objects[path], "spec")["message"] = "changed"
	field(f.objects[path], "spec")["image"] = "harbor.k8s.internal.egon.top/lab/app@sha256:" + strings.Repeat("b", 64)
	field(f.objects[path], "metadata")["generation"] = float64(2)
	reconcile(t, c, f, path)
	newTemplate := field(field(f.objects[depPath], "spec"), "template")
	if reflect.DeepEqual(oldTemplate, newTemplate) {
		t.Fatal("config did not trigger rollout")
	}
	if text(field(f.objects[c.collection("ConfigMap")+"/demo"], "data"), "message") != "changed" {
		t.Fatal("config not updated")
	}
}
func TestDeleteWaitsForChildrenAndUsesUIDPrecondition(t *testing.T) {
	c, f, path := setup()
	reconcile(t, c, f, path)
	field(f.objects[path], "metadata")["deletionTimestamp"] = "2026-10-21T00:00:00Z"
	field(f.objects[path], "spec")["replicas"] = float64(0) // 无效旧 spec 不能阻止删除。
	reconcile(t, c, f, path)
	if len(list(field(f.objects[path], "metadata"), "finalizers")) != 1 {
		t.Fatal("released finalizer before confirming children gone")
	}
	if text(field(f.lastDelete, "preconditions"), "uid") == "" {
		t.Fatal("delete had no UID precondition")
	}
	reconcile(t, c, f, path)
	if len(list(field(f.objects[path], "metadata"), "finalizers")) != 0 {
		t.Fatal("finalizer not removed")
	}
}
func TestAddsOnlyOwnFinalizer(t *testing.T) {
	c, f, path := setup()
	field(f.objects[path], "metadata")["finalizers"] = []any{"other.example/keep"}
	reconcile(t, c, f, path)
	values := list(field(f.objects[path], "metadata"), "finalizers")
	if len(values) != 2 || values[0] != "other.example/keep" || values[1] != finalizer {
		t.Fatal("other finalizer lost")
	}
	if len(f.objects) != 1 {
		t.Fatal("children created before finalizer was persisted")
	}
}
func TestConflictIsRetriedWithoutAdoption(t *testing.T) {
	c, f, path := setup()
	f.blockedPath = c.collection("ConfigMap") + "/demo"
	f.blockedStatus = 409
	err := c.reconcile(context.Background(), copyObject(f.objects[path]))
	if !isStatus(err, 409) || f.writes != 0 {
		t.Fatal("conflict was not propagated safely")
	}
}
func TestTransitionTimeChangesOnlyOnReadyStatusChange(t *testing.T) {
	_, f, path := setup()
	app := copyObject(f.objects[path])
	first := statusFor(app, 0, false, "Reconciling", "waiting", time.Unix(10, 0))
	app["status"] = first
	second := statusFor(app, 0, false, "APIError", "retry", time.Unix(20, 0))
	if text(list(second, "conditions")[0].(map[string]any), "lastTransitionTime") != text(list(first, "conditions")[0].(map[string]any), "lastTransitionTime") {
		t.Fatal("reason-only update changed transition time")
	}
	third := statusFor(app, 2, true, "ResourcesReady", "ready", time.Unix(20, 0))
	if text(list(third, "conditions")[0].(map[string]any), "lastTransitionTime") == text(list(first, "conditions")[0].(map[string]any), "lastTransitionTime") {
		t.Fatal("ready transition did not change time")
	}
}
func TestListPaginationUsesOpaqueContinuation(t *testing.T) {
	calls := 0
	c := &client{base: "https://api.invalid", namespace: "cnpl03-09", http: &http.Client{Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
		calls++
		if calls == 1 {
			return response(200, object{"items": []any{}, "metadata": object{"continue": "a+b/c=="}}), nil
		}
		if req.URL.Query().Get("continue") != "a+b/c==" {
			t.Fatal("continuation was not preserved")
		}
		return response(200, object{"items": []any{}, "metadata": object{}}), nil
	})}}
	if err := c.once(context.Background()); err != nil || calls != 2 {
		t.Fatalf("pagination failed: %v", err)
	}
}
func TestValidationBoundaries(t *testing.T) {
	_, f, path := setup()
	for _, test := range []struct {
		name, key string
		value     any
	}{
		{"tag image", "image", "harbor.k8s.internal.egon.top/lab/app:latest"},
		{"external registry", "image", "docker.io/library/nginx@sha256:" + strings.Repeat("a", 64)},
		{"too many replicas", "replicas", float64(6)},
		{"privileged port", "port", float64(80)},
		{"long message", "message", strings.Repeat("x", 1025)},
	} {
		t.Run(test.name, func(t *testing.T) {
			app := copyObject(f.objects[path])
			field(app, "spec")[test.key] = test.value
			if validate(app) == nil {
				t.Fatal("invalid input accepted")
			}
		})
	}
}
