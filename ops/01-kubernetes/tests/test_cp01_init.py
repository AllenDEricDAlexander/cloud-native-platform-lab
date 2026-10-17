"""离线回归：仅临时文件和伪命令，不连接节点、不启动服务。"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml


PHASE = Path(__file__).resolve().parents[1]
SCRIPT = PHASE / "bootstrap/scripts/init-cp01.sh"


class InitRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.kube = self.root / "kubernetes"
        self.etcd = self.root / "etcd"
        self.stage = self.root / "stage"
        for directory in [self.kube / "pki", self.kube / "manifests", self.etcd / "member", self.stage / "kube-vip", self.root / "bin"]:
            directory.mkdir(parents=True)
        self.originals = {
            self.kube / "admin.conf": "KEEP_ADMIN",
            self.kube / "pki/ca.crt": "KEEP_CA",
            self.kube / "manifests/kube-apiserver.yaml": "KEEP_API",
            self.etcd / "member/state": "KEEP_ETCD",
        }
        for path, value in self.originals.items():
            path.write_text(value)
        shutil.copyfile(PHASE / "bootstrap/kube-vip/kube-vip-control-plane.yaml", self.stage / "kube-vip/kube-vip-control-plane.yaml")
        self.env = dict(os.environ, MOCK_ROOT=str(self.root), MOCK_KUBE=str(self.kube), SCRIPT=str(SCRIPT))
        self.env["PATH"] = str(self.root / "bin") + os.pathsep + self.env["PATH"]
        self.stub("id", "print('0')")
        self.stub("hostname", "print('cp01.k8s.internal.egon.top' if '-f' in sys.argv else 'cp01')")
        self.stub("getenforce", "print('Enforcing')")
        self.stub("sleep", "pass")
        self.stub("ip", "print('2: ens33 inet 192.168.9.100/32 scope global')")
        self.stub("crictl", "pass")
        self.stub("systemctl", "print('active')")
        self.stub("kubeadm", "Path(os.environ['MOCK_ROOT'], 'kubeadm-called').write_text(' '.join(sys.argv)); sys.exit(99)")
        self.stub("kubectl", """
if '--server' in sys.argv and os.environ.get('MOCK_LOCAL_DOWN'):
    print('local API connection refused', file=sys.stderr)
    sys.exit(1)
if 'pod' in sys.argv:
    import yaml
    pod = yaml.safe_load(Path(os.environ['MOCK_KUBE'], 'manifests/kube-vip.yaml').read_text())
    alias = pod['spec'].get('hostAliases', [{}])[0]
    host_path = pod['spec']['volumes'][0]['hostPath']['path']
    print(alias.get('ip', '') + ' ' + ','.join(alias.get('hostnames', [])) + ' ' + host_path + ' true')
else:
    print('ok')
""")

    def stub(self, name, body):
        path = self.root / "bin" / name
        path.write_text(f"#!{sys.executable}\nimport os,sys\nfrom pathlib import Path\n" + body + "\n")
        path.chmod(0o700)

    def run_script(self, action="main --resume"):
        command = 'source "$SCRIPT"; KUBE_DIR="$MOCK_KUBE"; ETCD_DIR="$MOCK_ROOT/etcd"; ADMIN="$KUBE_DIR/admin.conf"; STAGE="$MOCK_ROOT/stage"; ' + action
        return subprocess.run(["/bin/bash", "-c", command], env=self.env, capture_output=True, text=True, timeout=15)

    def assert_cluster_preserved(self):
        self.assertFalse((self.root / "kubeadm-called").exists())
        for path, value in self.originals.items():
            self.assertEqual(path.read_text(), value)

    def test_bootstrap_and_steady_manifests_have_local_api_alias(self):
        for filename in ["kube-vip-cp01-init.yaml", "kube-vip-control-plane.yaml"]:
            pod = yaml.safe_load((PHASE / "bootstrap/kube-vip" / filename).read_text())
            self.assertTrue(pod["spec"]["hostNetwork"])
            self.assertEqual(pod["spec"]["hostAliases"], [{"ip": "127.0.0.1", "hostnames": ["kubernetes"]}])
            env = {item["name"]: item["value"] for item in pod["spec"]["containers"][0]["env"]}
            self.assertEqual(env["vip_subnet"], "32")
            self.assertNotIn("vip_cidr", env)

    def test_resume_repairs_vip_without_reinitializing_cluster(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("cp01 init PASS", result.stdout)
        self.assert_cluster_preserved()

    def test_resume_refuses_unhealthy_local_api_before_changing_manifest(self):
        self.env["MOCK_LOCAL_DOWN"] = "yes"
        result = self.run_script()
        self.assertEqual(result.returncode, 1)
        self.assertIn("本机控制平面尚不健康", result.stderr)
        self.assertFalse((self.kube / "manifests/kube-vip.yaml").exists())
        self.assert_cluster_preserved()

    def test_apply_refuses_running_cluster_with_recovery_hint(self):
        result = self.run_script("main --apply")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--resume", result.stderr)
        self.assert_cluster_preserved()

    def test_old_pod_does_not_pass_merely_because_vip_api_responds(self):
        pod = yaml.safe_load((self.stage / "kube-vip/kube-vip-control-plane.yaml").read_text())
        del pod["spec"]["hostAliases"]
        (self.kube / "manifests/kube-vip.yaml").write_text(yaml.safe_dump(pod))
        result = self.run_script("wait_for_vip 1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("等待修正后的稳态", result.stderr)
        self.assert_cluster_preserved()

    def test_diagnostics_redact_bootstrap_credentials(self):
        result = self.run_script("printf 'token: abcdef.0123456789abcdef\\n' | redact")
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("abcdef.0123456789abcdef", result.stdout)
        self.assertIn("REDACTED", result.stdout)


if __name__ == "__main__":
    unittest.main()
