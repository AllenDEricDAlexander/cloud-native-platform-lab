"""只使用临时文件、伪客户端和合成 Pod；不创建集群资源。"""
import copy
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'bootstrap/acceptance/check-network.py'
spec = importlib.util.spec_from_file_location('network_acceptance', SCRIPT)
network = importlib.util.module_from_spec(spec)
spec.loader.exec_module(network)


class NetworkAcceptanceTest(unittest.TestCase):
    def pods(self):
        return [{'metadata': {'name': 'network-' + str(index)}, 'spec': {'nodeName': node},
                 'status': {'podIP': f'10.244.{index}.2', 'conditions': [{'type': 'Ready', 'status': 'True'}]}}
                for index, node in enumerate(sorted(network.EXPECTED))]

    def test_exact_ten_nodes_and_addresses(self):
        network.inspect_pods(self.pods())
        for mutation in ['missing', 'duplicate-ip', 'wrong-cidr', 'host-network', 'not-ready']:
            pods = copy.deepcopy(self.pods())
            if mutation == 'missing': pods.pop()
            if mutation == 'duplicate-ip': pods[1]['status']['podIP'] = pods[0]['status']['podIP']
            if mutation == 'wrong-cidr': pods[0]['status']['podIP'] = '192.168.9.101'
            if mutation == 'host-network': pods[0]['spec']['hostNetwork'] = True
            if mutation == 'not-ready': pods[0]['status']['conditions'][0]['status'] = 'False'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                network.inspect_pods(pods)

    def run_probe(self, mode):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for binary, source in {
                'wget': "print('wrong-node' if os.environ['MOCK_MODE']=='wrong-http' else 'cp01.k8s.internal.egon.top')",
                'nslookup': "sys.exit(1) if os.environ['MOCK_MODE']=='dns-failure' else None\nprint('Address: ' + ('192.168.20.10' if os.environ['MOCK_MODE']=='wrong-answer' else {'network-smoke.cnpl-phase01-acceptance.svc.cluster.local':'192.168.20.2','kubernetes.default.svc.cluster.local':'192.168.20.1','harbor.k8s.internal.egon.top':'192.168.9.12','kubernetes.io':'203.0.113.1'}[sys.argv[2]]))"
            }.items():
                path = root / binary
                path.write_text(f'#!{sys.executable}\nimport os,sys\n' + source + '\n')
                path.chmod(0o700)
            env = dict(os.environ, MOCK_MODE=mode, PATH=str(root) + os.pathsep + os.environ['PATH'])
            return subprocess.run(['/bin/sh', '-ec', network.PROBE, 'probe', '192.168.20.2',
                                   '10.244.0.2=cp01.k8s.internal.egon.top'], env=env, capture_output=True, text=True, timeout=10)

    def test_success_checks_http_dns_and_both_service_paths(self):
        result = self.run_probe('success')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.count('DNS '), 4)
        self.assertEqual(result.stdout.count('SERVICE '), 2)

    def test_http_wrong_backend_is_failure(self):
        result = self.run_probe('wrong-http')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('DNS ', result.stdout)

    def test_dns_command_failure_is_not_ignored(self):
        result = self.run_probe('dns-failure')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('SERVICE ', result.stdout)

    def test_wrong_dns_answer_cannot_pass_by_matching_resolver_address(self):
        result = self.run_probe('wrong-answer')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('SERVICE ', result.stdout)


if __name__ == '__main__':
    unittest.main()
