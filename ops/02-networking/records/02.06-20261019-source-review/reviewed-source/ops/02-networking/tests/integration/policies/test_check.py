"""回归真实失败边界：探测器故障不能当拒绝，反向 L7、UID 变更及删除范围。"""
import importlib.util
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('policy_check_test', Path(__file__).with_name('check.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Policies(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.records = Path(self.temp.name)
        self.context = {'run': 'unique-run', 'capabilities': {'kube-proxy-replacement': 'false', 'enable-bpf-masquerade': 'false', 'enable-egress-gateway': 'false'}}
        self.obj = {'kind': 'NetworkPolicy', 'apiVersion': 'networking.k8s.io/v1',
            'metadata': {'namespace': 'lab-policy', 'name': 'standard-client', 'uid': 'original', 'labels': {m.LABEL: 'unique-run'}}}
        self.pod = {'metadata': {'namespace': 'lab-policy', 'name': 'client', 'uid': 'pod-uid'}}

    def test_negative_requires_timeout_not_arbitrary_error(self):
        self.assertFalse(m.matched({'error': 'executable not found', 'timeout': False}, 'drop'))
        self.assertFalse(m.matched({'error': 'connection refused', 'timeout': False}, 'drop'))
        self.assertFalse(m.matched({'status': 503}, 'drop'))
        self.assertTrue(m.matched({'error': 'deadline exceeded', 'timeout': True}, 'drop'))
        self.assertFalse(m.matched({'rcode': 3}, 'dns-deny'))
        self.assertTrue(m.matched({'rcode': 5}, 'dns-deny'))
        self.assertFalse(m.matched({'rcode': 0, 'addresses': []}, 'dns'))

    def test_nonce_and_backend_identity(self):
        backend = {'metadata': {'uid': 'real'}}
        row = {'status': 200, 'nonce': 'fresh', 'body': json.dumps({'uid': 'real', 'nonce': 'stale'})}
        self.assertFalse(m.matched(row, 200, backend))
        row['body'] = json.dumps({'uid': 'real', 'nonce': 'fresh'})
        self.assertTrue(m.matched(row, 200, backend))
        row['body'] = '{}'
        self.assertFalse(m.matched(row, 200, backend))

    def test_drop_requires_correlated_policy_denied_and_identity(self):
        flow = {'source': {'namespace': 'lab-policy', 'pod_name': 'client', 'identity': 300},
                'destination': {}, 'IP': {'source': '10.244.1.2', 'destination': '10.244.2.3'},
                'l4': {'TCP': {'destination_port': 8080}}, 'verdict': 'DROPPED', 'drop_reason_desc': 'POLICY_DENIED'}
        self.assertTrue(m.flow_matches(flow, self.pod, '10.244.2.3', 8080, 'drop'))
        self.assertTrue(m.flow_matches(flow, self.pod, ['192.168.20.50', '10.244.2.3'], 8080, 'drop'))
        flow['drop_reason_desc'] = 'CT_TRUNCATED_OR_INVALID_HEADER'
        self.assertFalse(m.flow_matches(flow, self.pod, '10.244.2.3', 8080, 'drop'))
        flow['drop_reason_desc'] = 'POLICY_DENIED'
        flow['source']['identity'] = 0
        self.assertFalse(m.flow_matches(flow, self.pod, '10.244.2.3', 8080, 'drop'))

    def test_reverse_http_and_dns_response(self):
        flow = {'source': {}, 'destination': {'namespace': 'lab-policy', 'pod_name': 'client', 'identity': 300},
            'IP': {'source': '10.244.2.3', 'destination': '10.244.1.2'}, 'l4': {'TCP': {'source_port': 8080}}, 'l7': {'http': {'code': 403}}}
        self.assertTrue(m.flow_matches(flow, self.pod, '10.244.2.3', 8080, 403))
        self.assertFalse(m.flow_matches(flow, self.pod, '10.244.2.3', 8080, 'drop'))
        flow['l4'] = {'UDP': {'source_port': 53}}
        flow['l7'] = {'dns': {'rcode': 5}}
        self.assertTrue(m.flow_matches(flow, self.pod, '10.244.2.3', 53, 'dns-deny'))

    def test_uid_precondition_and_replacement_rejection(self):
        path = m.state_path(self.records, self.obj)
        m.save(path, {'uid': 'original', 'run': 'unique-run'})
        with patch.object(m, 'optional', return_value=self.obj):
            row = m.delete_row(self.records, self.context, self.obj, self.records / 'plan.json')
        self.assertEqual(row['url'], '/apis/networking.k8s.io/v1/namespaces/lab-policy/networkpolicies/standard-client')
        self.assertEqual(json.loads(Path(row['body']).read_text())['preconditions']['uid'], 'original')
        self.obj['metadata']['uid'] = 'replacement'
        with patch.object(m, 'optional', return_value=self.obj), self.assertRaisesRegex(ValueError, 'UID'):
            m.delete_row(self.records, self.context, self.obj, self.records / 'plan.json')

    def test_foreign_resource_and_forbidden_kind(self):
        self.obj['metadata']['labels'][m.LABEL] = 'another-run'
        with patch.object(m, 'optional', return_value=None), self.assertRaises(ValueError):
            m.object_plan(self.records, self.context, self.obj)
        self.obj['metadata']['labels'][m.LABEL] = 'unique-run'
        self.obj['kind'] = 'CiliumEgressGatewayPolicy'
        with self.assertRaises(ValueError):
            m.object_plan(self.records, self.context, self.obj)

    def test_create_crash_can_cleanup_only_original_run(self):
        m.save(m.state_path(self.records, self.obj), {'uid': None, 'run': 'unique-run', 'creation_planned': True})
        with patch.object(m, 'optional', return_value=self.obj):
            row = m.delete_row(self.records, self.context, self.obj, self.records / 'plan.json')
        self.assertEqual(json.loads(Path(row['body']).read_text())['preconditions']['uid'], 'original')
        self.obj['metadata']['labels'][m.LABEL] = 'foreign'
        with patch.object(m, 'optional', return_value=self.obj), self.assertRaises(ValueError):
            m.delete_row(self.records, self.context, self.obj, self.records / 'plan.json')

    def test_blocked_is_never_pass(self):
        value = m.blocked(self.context)
        self.assertEqual(value['status'], 'BLOCKED')
        self.assertFalse(value['passed'])
        self.assertFalse(value['phase_complete'])
        self.assertIn('kube-proxy-replacement', value['missing'])

    def test_probe_command_failure_is_fatal(self):
        with patch.object(m, 'call', side_effect=ValueError('kubectl exec failed')), self.assertRaises(ValueError):
            m.request(self.pod, 'http', 'http://10.244.2.3:8080/allowed')

    def test_real_kubectl_raw_delete_preserves_uid_body(self):
        captured = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_DELETE(self):
                data = b''
                if self.headers.get('Transfer-Encoding') == 'chunked':
                    while True:
                        size = int(self.rfile.readline().split(b';')[0], 16)
                        if size == 0:
                            self.rfile.readline()
                            break
                        data += self.rfile.read(size)
                        self.rfile.read(2)
                else:
                    data = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                captured.append((self.path, json.loads(data)))
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"apiVersion":"v1","kind":"Status","status":"Success"}')
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
        thread.start()
        try:
            config = self.records / 'client.json'
            m.save(config, {'apiVersion': 'v1', 'kind': 'Config', 'clusters': [{'name': 'unit', 'cluster': {'server': 'http://127.0.0.1:' + str(server.server_port)}}],
                'contexts': [{'name': 'unit', 'context': {'cluster': 'unit', 'user': 'unit'}}], 'current-context': 'unit', 'users': [{'name': 'unit', 'user': {}}]})
            body = self.records / 'delete.json'
            m.save(body, {'apiVersion': 'v1', 'kind': 'DeleteOptions', 'preconditions': {'uid': 'original-uid'}, 'propagationPolicy': 'Foreground'})
            target = '/api/v1/namespaces/lab-policy'
            reply = subprocess.run([str(Path.home() / '.cnpl/bin/kubectl'), '--kubeconfig', str(config),
                '--request-timeout=3s', 'delete', '--raw', target, '-f', str(body)], capture_output=True, text=True, timeout=6)
            self.assertEqual(reply.returncode, 0, reply.stderr)
            self.assertEqual(len(captured), 1)
            self.assertEqual(captured[0][0].split('?')[0], target)
            self.assertEqual(captured[0][1], json.loads(body.read_text()))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=1)

    def test_hubble_lost_events_never_pass(self):
        pod = {**self.pod, 'spec': {'nodeName': 'worker01'}}
        with patch.object(m, 'agents', return_value={'worker01': 'agent'}), patch.object(m, 'get',
            return_value={'spec': {'clusterIP': '192.168.20.2'}}), patch.object(m, 'call',
            side_effect=['Connected Nodes: 10/10', '{"lost_events":{"num_events_lost":1}}\n']):
            with self.assertRaisesRegex(ValueError, '丢失事件'):
                m.flows(pod, '10.244.2.3', 8080, '2026-10-19T00:00:00Z', 'drop', self.records / 'hubble.jsonl')


if __name__ == '__main__':
    unittest.main()
