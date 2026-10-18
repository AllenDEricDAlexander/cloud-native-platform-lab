package main

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"encoding/json"
	"io"
	"testing"
)

func TestPackBindsDescriptorsPlatformVersionAndBinary(t *testing.T) {
	binary := []byte("finite Linux fixture")
	source := "source-sha"
	seen := map[string]bool{}
	for _, version := range []string{"v1", "v2", "bad"} {
		archive, meta := pack(binary, source, "cnpl.local/phase01/controller-lab", "controller-app", version)
		second, _ := pack(binary, source, "cnpl.local/phase01/controller-lab", "controller-app", version)
		if !bytes.Equal(archive, second) {
			t.Fatal("nondeterministic OCI")
		}
		digest := meta["manifest_digest"].(string)
		if seen[digest] {
			t.Fatal("versions share a manifest")
		}
		seen[digest] = true
		files := map[string][]byte{}
		r := tar.NewReader(bytes.NewReader(archive))
		for {
			h, e := r.Next()
			if e == io.EOF {
				break
			}
			if e != nil {
				t.Fatal(e)
			}
			b, e := io.ReadAll(r)
			if e != nil {
				t.Fatal(e)
			}
			files[h.Name] = b
		}
		var index struct {
			Manifests []struct {
				Digest      string
				Size        int
				Platform    struct{ OS, Architecture string }
				Annotations map[string]string
			}
		}
		if e := json.Unmarshal(files["index.json"], &index); e != nil {
			t.Fatal(e)
		}
		d := index.Manifests[0]
		if d.Digest != digest || d.Platform.OS != "linux" || d.Platform.Architecture != "amd64" || d.Annotations["io.containerd.image.name"] != meta["import_tag"] {
			t.Fatal(d)
		}
		manifest := files["blobs/sha256/"+digest[7:]]
		if "sha256:"+hash(manifest) != digest || len(manifest) != d.Size {
			t.Fatal("manifest descriptor mismatch")
		}
		var m struct {
			Config struct {
				Digest string
				Size   int
			}
			Layers []struct {
				Digest string
				Size   int
			}
		}
		if e := json.Unmarshal(manifest, &m); e != nil {
			t.Fatal(e)
		}
		config := files["blobs/sha256/"+m.Config.Digest[7:]]
		layer := files["blobs/sha256/"+m.Layers[0].Digest[7:]]
		if "sha256:"+hash(config) != m.Config.Digest || len(config) != m.Config.Size || "sha256:"+hash(layer) != m.Layers[0].Digest || len(layer) != m.Layers[0].Size {
			t.Fatal("blob descriptor mismatch")
		}
		var c struct {
			Config struct {
				User            string
				Entrypoint, Env []string
				Labels          map[string]string
			}
			Rootfs struct {
				DiffIDs []string `json:"diff_ids"`
			}
		}
		if e := json.Unmarshal(config, &c); e != nil {
			t.Fatal(e)
		}
		if c.Config.User != "1000:1000" || c.Config.Entrypoint[0] != "/controller-app" || c.Config.Env[0] != "APP_VERSION="+version || c.Config.Labels["cnpl.io/source-sha256"] != source {
			t.Fatal(c.Config)
		}
		gz, e := gzip.NewReader(bytes.NewReader(layer))
		if e != nil {
			t.Fatal(e)
		}
		raw, e := io.ReadAll(gz)
		gz.Close()
		if e != nil {
			t.Fatal(e)
		}
		if "sha256:"+hash(raw) != c.Rootfs.DiffIDs[0] {
			t.Fatal("diff id mismatch")
		}
		inner := tar.NewReader(bytes.NewReader(raw))
		h, e := inner.Next()
		if e != nil {
			t.Fatal(e)
		}
		actual, e := io.ReadAll(inner)
		if e != nil || h.Name != "controller-app" || h.Mode != 0555 || !bytes.Equal(actual, binary) {
			t.Fatal("binary layer mismatch")
		}
	}
}
