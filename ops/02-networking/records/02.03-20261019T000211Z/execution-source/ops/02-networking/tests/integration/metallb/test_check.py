import copy
import errno
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import subprocess
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('metallb_checks', Path(__file__).with_name('check.py'))
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)
monitor = check.monitor


def original():
    return {'uid': 'speaker-uid', 'spec': {'updateStrategy': {'type': 'RollingUpdate', 'rollingUpdate': {'maxSurge': 0, 'maxUnavailable': 1}}, 'template': {'spec': {'nodeSelector': {'kubernetes.io/os': 'linux', 'node-role.kubernetes.io/worker': ''}, 'containers': [{'image': 'pinned'}]}}}}


def apply_patch(document, operations):
    value = copy.deepcopy(document)
    for operation in operations:
        parts = operation['path'].strip('/').split('/')
        parent = value
        for part in parts[:-1]:
            parent = parent[part]
        if operation['op'] == 'test':
            if parent[parts[-1]] != operation['value']:
                raise ValueError('JSON Patch precondition failed')
        else:
            parent[parts[-1]] = operation['value']
    return value


def endpoints():
    service = {'metadata': {'name': 'vip-primary', 'uid': 'svc'}}
    pods = [{'metadata': {'uid': 'p'}, 'status': {'podIP': '10.244.9.4'}}]
    slices = [{'metadata': {'labels': {'kubernetes.io/service-name': 'vip-primary'}, 'ownerReferences': [{'uid': 'svc'}]}, 'addressType': 'IPv4', 'ports': [{'name': 'http', 'protocol': 'TCP', 'port': 8080}], 'endpoints': [{'targetRef': {'uid': 'p'}, 'conditions': {'ready': True}, 'addresses': ['10.244.9.4']}]}]
    return service, pods, slices


class L2Checks(unittest.TestCase):
    def test_observer_identity_resolves_symlink_paths_and_rejects_other_attempt(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            script = root / 'real/check.py'
            script.parent.mkdir()
            script.touch()
            alias = root / 'alias'
            alias.symlink_to(script.parent, target_is_directory=True)
            attempt = root / 'records/attempts/current'
            check.save(attempt / 'monitor-pid.json', {'pid': 123})
            virtual = root / 'virtual-records'
            virtual.symlink_to(root / 'records', target_is_directory=True)
            command = '/python ' + str(alias / 'check.py') + ' observe --attempt ' + str(virtual / 'attempts/current')
            with patch.object(check, '__file__', str(script)), patch.object(check.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, command, '')):
                self.assertTrue(check.process_alive(attempt))
            with patch.object(check, '__file__', str(script)), patch.object(check.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, command.replace('/attempts/current', '/attempts/other'), '')):
                self.assertFalse(check.process_alive(attempt))

    def test_both_maintenance_directions_and_exact_restore_round_trip(self):
        for remaining in check.WORKERS:
            with self.subTest(remaining=remaining), tempfile.TemporaryDirectory() as folder:
                records = Path(folder)
                saved = original()
                check.save(records / 'state/speaker-original.json', saved)
                daemon = {'metadata': {'uid': saved['uid']}, 'spec': saved['spec']}
                active = apply_patch(daemon, check.maintenance_patch(saved, remaining))
                self.assertEqual(active['spec']['updateStrategy'], {'type': 'OnDelete'})
                self.assertEqual(active['spec']['template']['spec']['nodeSelector']['kubernetes.io/hostname'], remaining)
                check.save(records / 'state/fault-plan.json', {'selector': active['spec']['template']['spec']['nodeSelector']})
                with patch.object(check, 'get', return_value=active):
                    plan = check.restore_plan(records, {'component': {'speaker_uid': saved['uid']}})
                self.assertEqual(apply_patch(active, plan['patch']), daemon)

    def test_patch_uid_guard_and_foreign_maintenance_fields_are_rejected(self):
        saved = original()
        with self.assertRaisesRegex(ValueError, 'precondition'):
            apply_patch({'metadata': {'uid': 'recreated'}, 'spec': saved['spec']}, check.maintenance_patch(saved, next(iter(check.WORKERS))))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            check.save(root / 'state/speaker-original.json', saved)
            check.save(root / 'state/fault-plan.json', {'selector': {'kubernetes.io/hostname': 'known'}})
            daemon = {'metadata': {'uid': 'speaker-uid'}, 'spec': copy.deepcopy(saved['spec'])}
            daemon['spec']['template']['spec']['nodeSelector'] = {'kubernetes.io/hostname': 'foreign'}
            with patch.object(check, 'get', return_value=daemon), self.assertRaisesRegex(ValueError, '其他操作'):
                check.restore_plan(root, {'component': {'speaker_uid': saved['uid']}})

    def test_restore_before_fault_is_idempotent(self):
        saved = original()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.assertEqual(check.restore_plan(root, {})['patch'], [])
            check.save(root / 'state/speaker-original.json', saved)
            with patch.object(check, 'get', return_value={'metadata': {'uid': saved['uid']}, 'spec': saved['spec']}):
                self.assertEqual(check.restore_plan(root, {'component': {'speaker_uid': saved['uid']}})['patch'], [])

    def test_null_slices_wait_and_old_pod_uid_cannot_pass(self):
        for field in ['ports', 'endpoints', 'uid']:
            service, pods, slices = endpoints()
            if field == 'uid':
                slices[0]['endpoints'][0]['targetRef']['uid'] = 'old'
            else:
                slices[0][field] = None
            with self.subTest(field=field), patch.object(check, 'get', return_value={'items': slices}):
                self.assertFalse(check.endpoint_match(service, pods))

    def test_empty_placeholder_does_not_hide_live_endpoints(self):
        service, pods, slices = endpoints()
        empty = copy.deepcopy(slices[0])
        empty.update(ports=None, endpoints=None)
        with patch.object(check, 'get', return_value={'items': slices + [empty]}):
            self.assertTrue(check.endpoint_match(service, pods))

    def test_wrong_service_slice_owner_is_rejected(self):
        service, pods, slices = endpoints()
        slices[0]['metadata']['ownerReferences'][0]['uid'] = 'other-service'
        with patch.object(check, 'get', return_value={'items': slices}), self.assertRaisesRegex(ValueError, 'Service UID'):
            check.endpoint_match(service, pods)

    def test_pool_cannot_expand_enable_autoassign_or_change_candidates(self):
        context = {'cluster_uid': 'cluster'}
        for kind in ['IPAddressPool', 'L2Advertisement']:
            document = {'kind': kind, 'metadata': {'labels': {'cnpl.io/component': check.COMPONENT, 'cnpl.io/cluster-uid': 'cluster'}}, 'spec': check.pool_spec(kind)}
            check.pool_owned(document, context)
            for field, value in ([('addresses', ['192.168.9.100/32']), ('autoAssign', True)] if kind == 'IPAddressPool' else [('nodeSelectors', []), ('interfaces', ['all'])]):
                altered = copy.deepcopy(document)
                altered['spec'][field] = value
                with self.subTest(kind=kind, field=field), self.assertRaisesRegex(ValueError, '策略不同'):
                    check.pool_owned(altered, context)

    def test_object_scope_and_uid_receipts_prevent_takeover(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            context = {'run': 'r'}
            outside = {'kind': 'Namespace', 'metadata': {'name': 'kube-system', 'namespace': check.NS, 'labels': {check.LABEL: 'r'}}}
            with self.assertRaisesRegex(ValueError, '越界'):
                check.object_plan(root, context, outside)
            service = {'kind': 'Service', 'metadata': {'name': 'vip-primary', 'namespace': check.NS, 'labels': {check.LABEL: 'r'}, 'uid': 'new'}}
            check.save(root / 'state/object-service-lab-metallb-vip-primary.json', {'uid': 'original'})
            with patch.object(check, 'optional', return_value=service), self.assertRaisesRegex(ValueError, 'UID'):
                check.object_plan(root, context, service)

    def test_delete_requires_original_uid(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            obj = {'metadata': {'uid': 'new', 'labels': {check.LABEL: 'r'}}}
            check.save(root / 'state/object-service-lab-metallb-vip-primary.json', {'uid': 'old'})
            with patch.object(check, 'optional', return_value=obj), self.assertRaisesRegex(ValueError, 'UID'):
                check.delete_plan(root, {'run': 'r'}, 'vip-primary')

    def test_broadcast_arp_detects_duplicate_and_unknown_mac(self):
        expected = '00:50:56:99:21:68'
        good = {'rc': 0, 'stdout': 'Unicast reply [00:50:56:99:21:68]\nUnicast reply [00:50:56:99:21:68]'}
        self.assertTrue(check.arp_check(good, expected)['passed'])
        good['stdout'] += '\nUnicast reply [00:50:56:99:22:69]'
        with self.assertRaisesRegex(ValueError, '唯一'):
            check.arp_check(good, expected)
        with self.assertRaisesRegex(ValueError, '唯一'):
            check.arp_check({'rc': 0, 'stdout': ''}, expected)

    def test_pending_case_rejects_unexpected_allocation(self):
        service = {'metadata': {'uid': 's', 'labels': {check.LABEL: 'r'}}, 'spec': {'ports': [{'port': 8080}]}, 'status': {'loadBalancer': {'ingress': None}}}
        with patch.object(check, 'get', return_value=service), patch.object(check.time, 'monotonic', side_effect=[0, 9]):
            self.assertTrue(check.pending({'run': 'r'}, Path('/unused'))['passed'])
        service['status']['loadBalancer']['ingress'] = [{'ip': check.VIP}]
        with patch.object(check, 'get', return_value=service), self.assertRaisesRegex(ValueError, '意外分配'):
            check.pending({'run': 'r'}, Path('/unused'))

    def test_withdrawal_does_not_accept_malformed_http_as_network_failure(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(check, 'optional', return_value=None), patch.object(check, 'l2_status', return_value=[]), patch.object(check, 'allocations', return_value=[]), patch.object(monitor, 'request', return_value={'passed': False, 'error_type': 'ValueError'}):
            with self.assertRaisesRegex(ValueError, '明确的网络'):
                check.withdrawn(Path(folder), {}, Path(folder), 'vip-primary')

    def test_cleanup_preserves_foreign_objects(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            obj = {'metadata': {'uid': 'original', 'labels': {check.LABEL: 'r'}}}
            check.save(root / 'state/object-namespace--lab-metallb.json', {'uid': 'original'})
            foreign = {'kind': 'Secret', 'metadata': {'name': 'external', 'labels': {}}}
            with patch.object(check, 'optional', return_value=obj), patch.object(check, 'get', return_value={'items': [foreign]}), self.assertRaisesRegex(ValueError, '外来资源'):
                check.cleanup_plan(root, {'run': 'r'})

    def test_missing_chapter_cannot_pass_complete_stage(self):
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(FileNotFoundError):
            check.accept(Path(folder), {}, Path(folder))

    def test_partial_primary_rollback_only_allows_new_owned_uid(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            context = {'run': 'r', 'cluster_uid': 'c', 'primary_preexisting': {'IPAddressPool': False, 'L2Advertisement': False}}
            obj = {'kind': 'IPAddressPool', 'metadata': {'uid': 'pool', 'labels': {'cnpl.io/component': check.COMPONENT, 'cnpl.io/cluster-uid': 'c'}}, 'spec': check.pool_spec('IPAddressPool')}
            check.save(root / 'state/object-ipaddresspool-metallb-system-cnpl-primary.json', {'uid': 'pool'})
            with patch.object(check, 'PRIMARY_RECORD', root / 'global.json'), patch.object(check, 'allocations', return_value=[]), patch.object(check, 'optional', side_effect=lambda kind, *args: obj if kind == 'ipaddresspool' else None):
                self.assertEqual(check.partial_plan(root, context)['delete'], [{'kind': 'ipaddresspool', 'name': check.POOL, 'uid': 'pool'}])
                context['primary_preexisting']['IPAddressPool'] = True
                with self.assertRaisesRegex(ValueError, '原有主池'):
                    check.partial_plan(root, context)

    def test_complete_primary_is_retained_and_registered_after_interruption(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            context = {'run': 'r', 'cluster_uid': 'c', 'component': {'namespace_uid': 'namespace'}}
            objects = {kind.lower(): {'kind': kind, 'metadata': {'uid': kind, 'labels': {'cnpl.io/component': check.COMPONENT, 'cnpl.io/cluster-uid': 'c'}}, 'spec': check.pool_spec(kind)} for kind in ['IPAddressPool', 'L2Advertisement']}
            for key, obj in objects.items():
                check.save(root / ('state/object-' + key + '-metallb-system-cnpl-primary.json'), {'uid': obj['metadata']['uid']})
            with patch.object(check, 'PRIMARY_RECORD', root / 'global.json'), patch.object(check, 'allocations', return_value=[]), patch.object(check, 'optional', side_effect=lambda kind, *args: objects[kind]), patch.object(check, 'get', side_effect=lambda kind, *args: objects[kind]):
                self.assertEqual(check.partial_plan(root, context)['delete'], [])
                self.assertTrue(json.loads((root / 'global.json').read_text())['passed'])

    def test_missing_persistent_primary_after_acceptance_cannot_close(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            check.save(root / 'passed.json', {'passed': True})
            with patch.object(check, 'optional', return_value=None), patch.object(check, 'allocations', return_value=[]), patch.object(check, 'speaker_ready', return_value={'passed': True}), patch.object(check.common.base, 'preflight', return_value={'cluster_uid': 'c'}):
                with self.assertRaisesRegex(ValueError, '持久主池缺失'):
                    check.final(root, {'cluster_uid': 'c'})


class ConnectionChecks(unittest.TestCase):
    def test_prewarm_can_recover_and_arp_transition_is_not_misattributed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            counts = {'old': 0, 'arp': 0}
            def request(connection, backends, kind, epoch=0):
                if kind == 'existing':
                    counts['old'] += 1
                    if counts['old'] == 7:
                        (root / 'monitor.stop').touch()
                    if counts['old'] == 1:
                        return {'kind': kind, 'passed': False, 'epoch': epoch}
                return {'kind': kind, 'passed': True, 'epoch': epoch, 'local': ['192.168.9.200', 40001], 'connection_close': False, 'response': {'uid': 'u'}}
            def arp(vip, macs):
                counts['arp'] += 1
                node = 'old' if counts['arp'] == 1 else 'new'
                return {'vm': node, 'mac': node, 'observed_mono': 1}
            with patch.object(monitor, 'request', side_effect=request), patch.object(monitor, 'arp', side_effect=arp), patch.object(monitor.time, 'sleep'):
                result = monitor.observe(root, check.VIP, {}, {}, seconds=10)
            self.assertTrue(result['stopped_by_controller'])
            warm = json.loads((root / 'monitor.ready.json').read_text())
            self.assertEqual(warm['initial_epoch'], 1)
            first = json.loads((root / 'traffic.jsonl').read_text().splitlines()[0])
            self.assertIsNone(first['arp']['vm'])
            self.assertTrue(first['arp']['changed_during_sample'])

    def test_real_http11_connection_is_reused_and_stale_backend_rejected(self):
        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            def do_GET(self):
                body = json.dumps({'pod': 'echo', 'uid': 'uid'}).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=1)
        try:
            first = monitor.request(connection, {'echo': 'uid'}, 'existing', 2)
            second = monitor.request(connection, {'echo': 'uid'}, 'existing', 2)
            self.assertTrue(first['passed'] and second['passed'])
            self.assertEqual(first['local'], second['local'])
            self.assertFalse(first['connection_close'])
            self.assertFalse(monitor.request(connection, {'echo': 'old'}, 'existing', 2)['passed'])
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_original_socket_identity_is_retained_on_send_failure(self):
        class Sock:
            def getsockname(self):
                return ('192.168.9.200', 40000)
        class Connection:
            sock = Sock()
            def request(self, *args, **kwargs):
                raise OSError(errno.EHOSTUNREACH, 'no route')
        value = monitor.request(Connection(), {}, 'existing', 3)
        self.assertFalse(value['passed'])
        self.assertEqual(value['local'], ['192.168.9.200', 40000])
        self.assertEqual(value['epoch'], 3)

    def test_failover_analysis_separates_old_connection_from_reconnect(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            check.save(root / 'monitor-summary.json', {'stopped_by_controller': True, 'rows': 5, 'existing_connection_epochs': 4})
            check.save(root / 'monitor.ready.json', {'ready': True, 'initial_local': ['192.168.9.200', 40000], 'initial_epoch': 2})
            check.save(root / 'fault-start.json', {'mono': 10})
            rows = [{'kind': 'new', 'passed': True, 'started_mono': t, 'finished_mono': t + 0.1, 'arp': {'vm': 'worker02', 'observed_mono': t + 0.2}} for t in [11, 12, 13]]
            rows += [{'kind': 'existing', 'passed': False, 'started_mono': 11, 'epoch': 2, 'local': ['192.168.9.200', 40000]}, {'kind': 'existing', 'passed': True, 'started_mono': 12, 'epoch': 3, 'local': ['192.168.9.200', 40001]}]
            (root / 'traffic.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))
            result = monitor.analyse(root, {'entry_vm': 'worker01'}, {'entry_vm': 'worker02'})
            self.assertEqual(result['original_connection_failed_samples_after_fault'], 1)
            self.assertEqual(result['original_connection_successes_after_fault'], 0)
            self.assertEqual(result['first_observed_new_connection_recovery_seconds'], 1.2)
            rows[0]['arp']['vm'] = 'worker01'
            (root / 'traffic.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))
            with self.assertRaisesRegex(ValueError, '至少三个'):
                monitor.analyse(root, {'entry_vm': 'worker01'}, {'entry_vm': 'worker02'})


if __name__ == '__main__':
    unittest.main()
