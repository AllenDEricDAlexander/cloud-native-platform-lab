// imagepack 仅打包已有静态二进制，不执行部署、不启动应用。由 Ansible 调用。
package main

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"time"
)

func hash(b []byte) string { s := sha256.Sum256(b); return hex.EncodeToString(s[:]) }
func data(v any) []byte {
	b, e := json.Marshal(v)
	if e != nil {
		panic(e)
	}
	return b
}
func descriptor(kind string, b []byte) map[string]any {
	return map[string]any{"mediaType": kind, "size": len(b), "digest": "sha256:" + hash(b)}
}
func put(t *tar.Writer, name string, b []byte, mode int64) {
	if e := t.WriteHeader(&tar.Header{Name: name, Mode: mode, Size: int64(len(b)), ModTime: time.Unix(0, 0), Format: tar.FormatUSTAR}); e != nil {
		panic(e)
	}
	if _, e := t.Write(b); e != nil {
		panic(e)
	}
}
func read(path string) []byte {
	b, e := os.ReadFile(path)
	if e != nil {
		panic(e)
	}
	return b
}

func pack(binary []byte, source, repo, entry, version string) ([]byte, map[string]any) {
	var raw bytes.Buffer
	t := tar.NewWriter(&raw)
	put(t, entry, binary, 0555)
	if e := t.Close(); e != nil {
		panic(e)
	}
	var layer bytes.Buffer
	g := gzip.NewWriter(&layer)
	if _, e := g.Write(raw.Bytes()); e != nil {
		panic(e)
	}
	if e := g.Close(); e != nil {
		panic(e)
	}
	settings := map[string]any{"User": "1000:1000", "WorkingDir": "/work", "Entrypoint": []string{"/" + entry}, "Labels": map[string]string{"cnpl.io/source-sha256": source}}
	if version != "" {
		settings["Env"] = []string{"APP_VERSION=" + version}
		settings["Labels"].(map[string]string)["cnpl.io/controller-version"] = version
	}
	config := data(map[string]any{"architecture": "amd64", "os": "linux", "config": settings, "rootfs": map[string]any{"type": "layers", "diff_ids": []string{"sha256:" + hash(raw.Bytes())}}})
	manifest := data(map[string]any{"schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json", "config": descriptor("application/vnd.oci.image.config.v1+json", config), "layers": []any{descriptor("application/vnd.oci.image.layer.v1.tar+gzip", layer.Bytes())}})
	sha := "sha256:" + hash(manifest)
	tag := repo + ":sha256-" + hash(binary)
	if version != "" {
		tag = repo + ":" + version + "-sha256-" + hash(manifest)
	}
	d := descriptor("application/vnd.oci.image.manifest.v1+json", manifest)
	d["platform"] = map[string]string{"os": "linux", "architecture": "amd64"}
	d["annotations"] = map[string]string{"io.containerd.image.name": tag, "org.opencontainers.image.ref.name": tag}
	var output bytes.Buffer
	outer := tar.NewWriter(&output)
	put(outer, "oci-layout", []byte(`{"imageLayoutVersion":"1.0.0"}`), 0644)
	put(outer, "index.json", data(map[string]any{"schemaVersion": 2, "manifests": []any{d}}), 0644)
	for _, b := range [][]byte{config, layer.Bytes(), manifest} {
		put(outer, "blobs/sha256/"+hash(b), b, 0644)
	}
	if e := outer.Close(); e != nil {
		panic(e)
	}
	return output.Bytes(), map[string]any{"version": version, "image": repo + "@" + sha, "import_tag": tag, "manifest_digest": sha, "binary_sha256": hash(binary)}
}

func main() {
	family := flag.String("family", "", "probes|controllers")
	sourceDir := flag.String("source", "", "source directory")
	binaryPath := flag.String("binary", "", "linux/amd64 binary")
	output := flag.String("output", "", "metadata JSON")
	flag.Parse()
	if *family != "probes" && *family != "controllers" {
		panic("invalid image family")
	}
	var inputs []byte
	for _, n := range []string{"go.mod", "main.go"} {
		inputs = append(inputs, []byte(n)...)
		inputs = append(inputs, 0)
		inputs = append(inputs, read(filepath.Join(*sourceDir, n))...)
	}
	source := hash(inputs)
	binary := read(*binaryPath)
	repo := "cnpl.local/phase01/probe-lab"
	entry := "probe-lab"
	versions := []string{""}
	if *family == "controllers" {
		repo = "cnpl.local/phase01/controller-lab"
		entry = "controller-app"
		versions = []string{"v1", "v2", "bad"}
	}
	images := map[string]any{}
	result := map[string]any{"schema_version": 1, "source_sha256": source, "go_version": "go1.27.2", "go_archive_sha256": "76812b213b1b2302c978d28fa52fa92d541704b9e7d9d5db8002c50e4018c4c5", "binary_sha256": hash(binary)}
	if e := os.MkdirAll(filepath.Dir(*output), 0700); e != nil {
		panic(e)
	}
	for _, v := range versions {
		archive, meta := pack(binary, source, repo, entry, v)
		name := v
		if name == "" {
			name = "probe"
		}
		path := filepath.Join(filepath.Dir(*output), name+".oci.tar")
		if e := os.WriteFile(path, archive, 0600); e != nil {
			panic(e)
		}
		meta["archive"] = path
		meta["archive_sha256"] = hash(archive)
		if v == "" {
			for k, val := range meta {
				if k != "version" {
					result[k] = val
				}
			}
		} else {
			images[v] = meta
		}
	}
	if *family == "controllers" {
		result["images"] = images
	}
	b, e := json.MarshalIndent(result, "", "  ")
	if e != nil {
		panic(e)
	}
	if e = os.WriteFile(*output, append(b, '\n'), 0600); e != nil {
		panic(e)
	}
	fmt.Println("OCI PACK PASS", *family)
}
