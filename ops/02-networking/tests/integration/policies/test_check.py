"""回归真实失败边界：探测器故障不能当拒绝，反向 L7、UID 变更及删除范围。"""
import importlib.util
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
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
        flow['drop_reason_desc'] = 'POLICY_DENY'
        self.assertTrue(m.flow_matches(flow, self.pod, '10.244.2.3', 8080, 'drop'))
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

    def test_dns_proxy_rejection_uses_dropped_query_and_exact_probe_socket(self):
        pod = {'metadata': {'namespace': 'lab-policy', 'name': 'fqdn'}}
        flow = {'source': {'namespace': 'lab-policy', 'pod_name': 'fqdn', 'identity': 21561},
            'IP': {'source': '10.244.8.26', 'destination': '10.244.9.95'},
            'l4': {'UDP': {'source_port': 47364, 'destination_port': 53}}, 'verdict': 'DROPPED',
            'l7': {'type': 'REQUEST', 'dns': {'query': 'nexus.svc.internal.egon.top.', 'observation_source': 'proxy', 'qtypes': ['A']}}}
        target = 'nexus.svc.internal.egon.top'
        self.assertTrue(m.flow_matches(flow, pod, '10.244.9.95', 53, 'dns-deny', target, [47364]))
        self.assertFalse(m.flow_matches(flow, pod, '10.244.9.95', 53, 'dns-deny', 'harbor.k8s.internal.egon.top', [47364]))
        self.assertFalse(m.flow_matches(flow, pod, '10.244.9.95', 53, 'dns-deny', target, [59346]))
        flow['verdict'] = 'FORWARDED'
        self.assertFalse(m.flow_matches(flow, pod, '10.244.9.95', 53, 'dns-deny', target, [47364]))
        flow['verdict'] = 'DROPPED'
        flow['l7'] = {}
        self.assertFalse(m.flow_matches(flow, pod, '10.244.9.95', 53, 'dns-deny', target, [47364]))

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

    def test_hubble_query_binds_peer_port_in_both_directions(self):
        targets = ['10.244.2.3', '192.168.20.50']
        query = m.hubble_query(self.pod, targets, 8080, '2026-10-19T00:00:00.123456Z')
        self.assertNotIn('--pod', query)
        self.assertNotIn('--ip', query)
        self.assertNotIn('--port', query)
        filters = [json.loads(query[i + 1]) for i, value in enumerate(query) if value == '--allowlist']
        self.assertEqual(filters, [
            {'source_pod': ['lab-policy/client'], 'destination_ip': targets, 'destination_port': ['8080']},
            {'destination_pod': ['lab-policy/client'], 'source_ip': targets, 'source_port': ['8080']}])
        # 客户端使用临时端口；正向约束目标端口，反向约束源端口。
        for row, client, peer in [(filters[0], 'source', 'destination'), (filters[1], 'destination', 'source')]:
            self.assertNotIn(client + '_port', row)
            self.assertEqual(row[peer + '_port'], ['8080'])

    def test_hubble_dns_correlates_service_and_ready_backend(self):
        pod = {**self.pod, 'spec': {'nodeName': 'worker01'}}
        dns = {'metadata': {'labels': {'k8s-app': 'kube-dns'}},
            'status': {'podIP': '10.244.3.4', 'conditions': [{'type': 'Ready', 'status': 'True'}]}}
        unready = {'metadata': {'labels': {'k8s-app': 'kube-dns'}}, 'status': {'podIP': '10.244.3.5'}}
        flow = {'source': {'namespace': 'lab-policy', 'pod_name': 'client', 'identity': 300},
            'IP': {'destination': '10.244.3.4'}, 'l4': {'UDP': {'destination_port': 53}}, 'verdict': 'FORWARDED'}
        unrelated = {**flow, 'IP': {'destination': '192.168.9.14'}}
        raw = '\n'.join(json.dumps({'flow': value}) for value in [unrelated, flow]) + '\n'
        output = self.records / 'hubble.jsonl'
        with patch.object(m, 'hubble_access', return_value=(['hubble'], 'Connected Nodes: 10/10')), \
            patch.object(m, 'get', return_value={'items': [dns, unready]}), patch.object(m, 'call', return_value=raw) as call:
            result = m.flows(pod, '192.168.20.10', 53, '2026-10-19T00:00:00Z', 'dns', output)
        self.assertEqual(result['matching_flows'], 1)
        self.assertEqual(result['target_ips'], ['10.244.3.4', '192.168.20.10'])
        self.assertEqual(result['workload_identities'], [300])
        args = call.call_args.args[0]
        filters = [json.loads(args[i + 1]) for i, value in enumerate(args) if value == '--allowlist']
        self.assertEqual(filters[0]['destination_ip'], result['target_ips'])
        self.assertEqual(filters[1]['source_ip'], result['target_ips'])
        self.assertEqual(output.read_text(), raw)

    def firewall_inventory(self):
        return {name: {'metadata': {'uid': name + '-uid'}, 'status': {'podIP': ip},
            'spec': {'nodeName': 'worker01.k8s.internal.egon.top' if name != 'api' else 'worker02.k8s.internal.egon.top'}}
            for name, ip in [('client', '10.244.8.2'), ('api', '10.244.9.3'),
                             ('fqdn', '10.244.8.4'), ('egress', '10.244.8.5')]}

    def test_firewall_limits_exact_pod_peers_and_original_ports(self):
        rules = m.firewall_rules(self.firewall_inventory(), ['192.168.20.10', '10.244.9.10'])
        self.assertEqual(len(rules), 18)
        self.assertTrue(all('/32"' in rule and ' accept' in rule for rule in rules))
        self.assertFalse(any('10000-' in rule or '20000' in rule or '10503' in rule or '41035' in rule for rule in rules))
        http = [rule for rule in rules if 'port="8080"' in rule]
        self.assertEqual(len(http), 2)
        self.assertTrue(any('source address="10.244.8.2/32" destination address="10.244.9.3/32" port port="8080"' in rule for rule in http))
        self.assertTrue(any('source address="10.244.9.3/32" destination address="10.244.8.2/32" source-port port="8080"' in rule for rule in http))
        for rule in rules:
            if 'port="53"' in rule:
                self.assertTrue('10.244.8.4/32' in rule or '10.244.8.5/32' in rule)
        inventory = self.firewall_inventory()
        inventory['api']['status']['podIP'] = '192.168.9.101'
        with self.assertRaisesRegex(ValueError, '越界'):
            m.firewall_rules(inventory, ['192.168.20.10'])

    def prepare_firewall(self, existing=False):
        self.context['cluster_uid'] = 'cluster-uid'
        inventory = self.firewall_inventory()
        rules = m.firewall_rules(inventory, ['192.168.20.10', '10.244.9.10'])
        before = {'runtime': [rules[0]] if existing else ['original-rule'], 'permanent': ['original-permanent'], 'parsed': rules}
        def get(kind, *args, **kwargs):
            if kind == 'node':
                return {'metadata': {'uid': 'node-uid'}}
            return {'items': [{'metadata': {'labels': {'k8s-app': 'kube-dns'}},
                'status': {'podIP': '10.244.9.10', 'conditions': [{'type': 'Ready', 'status': 'True'}]}}]}
        with patch.object(m, 'pods', return_value=inventory), patch.object(m, 'get', side_effect=get), \
            patch.object(m, 'firewall_snapshot', return_value=before):
            plan = m.firewall_plan(self.records, self.context)
        return plan, rules

    def test_firewall_intent_precedes_commands_and_recovery_removes_partial_subset(self):
        plan, rules = self.prepare_firewall()
        state = self.records / 'state/l7-firewall.json'
        original = state.read_bytes()
        self.assertEqual(len(plan['objects']), len(rules))
        self.assertTrue(all('--timeout=3600' in obj['argv'][-1] and '--permanent' not in obj['argv'][-1] for obj in plan['objects']))
        current = {'runtime': ['original-rule', *rules[:2]], 'permanent': ['original-permanent']}
        with patch.object(m, 'get', return_value={'metadata': {'uid': 'node-uid'}}), \
            patch.object(m, 'firewall_snapshot', return_value=current):
            cleanup = m.firewall_plan(self.records, self.context, cleanup=True)
        self.assertEqual([obj['rule'] for obj in cleanup['objects']], rules[:2])
        self.assertTrue(all('--remove-rich-rule=' in obj['argv'][-1] for obj in cleanup['objects']))
        self.assertEqual(state.read_bytes(), original)

    def test_firewall_refuses_preexisting_rule_and_changed_node_uid(self):
        with self.assertRaisesRegex(ValueError, '不能接管'):
            self.prepare_firewall(existing=True)
        self.assertFalse((self.records / 'state/l7-firewall.json').exists())
        self.prepare_firewall()
        with patch.object(m, 'get', return_value={'metadata': {'uid': 'replacement'}}), \
            patch.object(m, 'firewall_snapshot') as snapshot, self.assertRaisesRegex(ValueError, 'UID'):
            m.firewall_plan(self.records, self.context, cleanup=True)
        snapshot.assert_not_called()

    def test_firewall_restoration_preserves_original_and_permanent_rules(self):
        self.assertTrue(m.firewall_verify(self.records, self.context, restored=True)['passed'])
        _, rules = self.prepare_firewall()
        with patch.object(m, 'get', return_value={'metadata': {'uid': 'node-uid'}}), \
            patch.object(m, 'firewall_snapshot', return_value={'runtime': ['original-rule'], 'permanent': ['original-permanent']}) as snapshot:
            self.assertTrue(m.firewall_verify(self.records, self.context, restored=True)['passed'])
            snapshot.return_value['permanent'] = ['changed']
            with self.assertRaisesRegex(ValueError, '永久规则'):
                m.firewall_verify(self.records, self.context, restored=True)
            snapshot.return_value = {'runtime': ['original-rule', *rules[:-1]], 'permanent': ['original-permanent']}
            with self.assertRaisesRegex(ValueError, '未收敛'):
                m.firewall_verify(self.records, self.context)

    def test_probe_timeout_still_collects_hubble_before_failing(self):
        pod = self.firewall_inventory()['client']
        row = {'error': 'context deadline exceeded', 'timeout': True}
        with patch.object(m, 'request', return_value=row), patch.object(m.time, 'sleep'), \
            patch.object(m, 'flows', return_value={'passed': True, 'matching_flows': 24}) as flows:
            with self.assertRaisesRegex(ValueError, '超时 12/12'):
                m.case(self.context, self.records, 'cilium-api-allowed', pod, 'http', 'http://10.244.9.3:8080/allowed', 200)
        flows.assert_called_once()
        path = self.records / 'observations/cilium-api-allowed'
        self.assertEqual(len(json.loads((path / 'requests.json').read_text())), 12)
        self.assertFalse(json.loads((path / 'result.json').read_text())['passed'])

    def test_proxy_readiness_allows_unchanged_ack_but_requires_initial_ack_and_port(self):
        vm = 'worker01.k8s.internal.egon.top'
        pod = {'metadata': {'namespace': 'lab-policy'}, 'spec': {'nodeName': vm}}
        policy = {'spec': {'policy-revision': 10}, 'realized': {'policy-revision': 10, 'policy-enabled': 'both'},
            'proxy-policy-revision': 0, 'proxy-statistics': [{'allocated-proxy-port': 10503}]}
        status = {'state': 'ready', 'policy': policy}
        cep = {'status': {'id': 123, 'identity': {'id': 300}}}
        with patch.object(m, 'pods', return_value={'client': pod}), patch.object(m, 'agents', return_value={vm: 'agent'}), \
            patch.object(m, 'get', return_value=cep), patch.object(m, 'call', side_effect=lambda *args, **kwargs: json.dumps([{'id': 123, 'status': status}])):
            with self.assertRaisesRegex(ValueError, 'ACK'):
                m.endpoint_state(self.context)
            policy['proxy-policy-revision'] = 9
            policy['proxy-statistics'][0]['allocated-proxy-port'] = 0
            with self.assertRaisesRegex(ValueError, '端口分配'):
                m.endpoint_state(self.context)
            policy['proxy-statistics'][0]['allocated-proxy-port'] = 10503
            self.assertTrue(m.endpoint_state(self.context)['passed'])

    def test_tcpdump_combined_startup_lines_are_not_hidden_by_text_buffer(self):
        original_popen = subprocess.Popen
        code = ('import os,time; os.write(2,b"tcpdump: verbose output suppressed\\nlistening on ens33, link-type EN10MB\\n"); '
            'os.write(1,b"IP 192.168.9.109.41000 > 192.168.9.12.443: Flags [S]\\n"); time.sleep(0.2)')
        def start(*args, **kwargs):
            process = original_popen([sys.executable, '-c', code], **kwargs)
            self.assertTrue(m.select.select([process.stderr], [], [], 2)[0])
            return process
        pod = self.firewall_inventory()['egress']
        row = {'local': pod['status']['podIP'] + ':41000', 'status': 401}
        with patch.object(m.subprocess, 'Popen', side_effect=start), patch.object(m, 'request', return_value=row) as request, \
            patch.object(m.time, 'monotonic', side_effect=[0, 0, 7]), patch.object(m, 'call', return_value='[{"dev":"ens33"}]'):
            value = m.wire(self.context, self.records, pod, '192.168.9.12', 443, 'https://harbor.k8s.internal.egon.top/v2/')
        request.assert_called_once()
        self.assertTrue(value['passed'])
        self.assertTrue(value['snat'])
        self.assertIn('listening on ens33', (self.records / 'observations/wire-192.168.9.12-443/observer.txt').read_text())


if __name__ == '__main__':
    unittest.main()
