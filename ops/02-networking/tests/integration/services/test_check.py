import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

spec = importlib.util.spec_from_file_location('services_check', Path(__file__).with_name('check.py'))
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def endpoint_data():
    service = {'metadata': {'name': 'echo', 'uid': 'svc'}}
    pods = [{'metadata': {'uid': 'pod-1'}, 'status': {'podIP': '10.244.9.4'}}]
    slices = [{'metadata': {'labels': {'kubernetes.io/service-name': 'echo'}, 'ownerReferences': [{'uid': 'svc'}]}, 'addressType': 'IPv4', 'ports': [{'name': 'http', 'protocol': 'TCP', 'port': 8080}], 'endpoints': [{'addresses': ['10.244.9.4'], 'targetRef': {'uid': 'pod-1'}, 'conditions': {'ready': True}}]}]
    return service, pods, slices


class ServiceChecks(unittest.TestCase):
    def test_cold_slice_null_arrays_are_not_ready(self):
        for ports, endpoints in [(None, None), (None, []), ([], None), ([], [])]:
            service, pods, slices = endpoint_data()
            slices[0].update(ports=ports, endpoints=endpoints)
            with self.subTest(ports=ports, endpoints=endpoints), patch.object(check, 'get', return_value={'items': slices}):
                self.assertFalse(check.endpoints(service, pods))

    def test_live_slice_with_empty_placeholder_converges(self):
        service, pods, slices = endpoint_data()
        empty = copy.deepcopy(slices[0])
        empty.update(ports=None, endpoints=None)
        slices.append(empty)
        with patch.object(check, 'get', return_value={'items': slices}):
            self.assertTrue(check.endpoints(service, pods))

    def test_stale_uid_wrong_port_unready_and_missing_reference_fail(self):
        for case in ['uid', 'port', 'ready', 'reference']:
            service, pods, slices = endpoint_data()
            if case == 'uid':
                slices[0]['endpoints'][0]['targetRef']['uid'] = 'old-uid'
            elif case == 'port':
                slices[0]['ports'][0]['port'] = 9999
            elif case == 'ready':
                slices[0]['endpoints'][0]['conditions']['ready'] = False
            else:
                slices[0]['endpoints'][0]['targetRef'] = None
            with self.subTest(case=case), patch.object(check, 'get', return_value={'items': slices}):
                self.assertFalse(check.endpoints(service, pods))

    def test_foreign_service_owner_rejected(self):
        service, pods, slices = endpoint_data()
        slices[0]['metadata']['ownerReferences'][0]['uid'] = 'other-service'
        with patch.object(check, 'get', return_value={'items': slices}), self.assertRaisesRegex(ValueError, 'owner UID'):
            check.endpoints(service, pods)

    def test_mac_unreachable_is_expected_only_for_negative_probe(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(check.urllib.request, 'build_opener') as opener:
            opener.return_value.open.side_effect = urllib.error.URLError(TimeoutError('timeout'))
            self.assertEqual(check.mac_request('http://192.168.9.109:31000/', Path(folder), 'local-negative', {}, fail=True)['error'], 'TimeoutError')
            with self.assertRaisesRegex(ValueError, 'Mac 请求失败'):
                check.mac_request('http://192.168.9.109:31000/', Path(folder), 'positive', {})
            self.assertEqual(len(list(Path(folder).glob('*.json'))), 2)

    def test_http_error_is_not_accepted_as_expected_network_drop(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(check.urllib.request, 'build_opener') as opener:
            opener.return_value.open.side_effect = urllib.error.HTTPError('http://example', 500, 'server error', {}, None)
            with self.assertRaisesRegex(ValueError, 'Mac 请求失败'):
                check.mac_request('http://example', Path(folder), 'negative', {}, fail=True)

    def test_http_identity_requires_current_uid(self):
        check.verify_echo({'pod': 'p', 'uid': 'current'}, {'p': 'current'})
        for body in [None, {}, {'pod': 'p'}, {'pod': 'p', 'uid': 'previous'}, {'pod': 'foreign', 'uid': 'current'}]:
            with self.subTest(body=body), self.assertRaisesRegex(ValueError, 'UID'):
                check.verify_echo(body, {'p': 'current'})

    def test_firewall_restores_runtime_and_permanent_independently(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            context = {'run': 'r', 'cluster_uid': 'c', 'mac_ip': '192.168.9.200'}
            rule = 'rule family="ipv4" source address="192.168.9.200/32" port port="31000" protocol="tcp" accept'
            document = {'run': 'r', 'cluster_uid': 'c', 'host': 'worker01', 'purpose': 'nodeport', 'rules': [rule], 'runtime': [0], 'permanent': [1]}
            check.save(root / 'state/firewall-nodeport-worker01-original.json', document)
            result = check.firewall_restore(root, context, 'worker01')['rules'][0]
            self.assertTrue(result['runtime'])
            self.assertFalse(result['permanent'])
            self.assertEqual(check.firewall_restore(root, context, 'worker02')['rules'], [])
            document['run'] = 'foreign'
            check.save(root / 'state/firewall-nodeport-worker01-original.json', document)
            with self.assertRaisesRegex(ValueError, '归属'):
                check.firewall_restore(root, context, 'worker01')

    def test_firewall_cannot_restore_broad_rule_or_incomplete_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            context = {'run': 'r', 'cluster_uid': 'c', 'mac_ip': '192.168.9.200'}
            document = {'run': 'r', 'cluster_uid': 'c', 'host': 'worker01', 'purpose': 'nodeport', 'rules': ['rule family="ipv4" source address="192.168.9.0/24" port port="31000" protocol="tcp" accept'], 'runtime': [1], 'permanent': [1]}
            target = root / 'state/firewall-nodeport-worker01-original.json'
            check.save(target, document)
            with self.assertRaisesRegex(ValueError, '范围'):
                check.firewall_restore(root, context, 'worker01')
            document['permanent'] = []
            check.save(target, document)
            with self.assertRaisesRegex(ValueError, '不完整'):
                check.firewall_restore(root, context, 'worker01')

    def test_pool_cannot_expand_or_automatically_assign(self):
        import yaml
        document = {'apiVersion': 'metallb.io/v1beta1', 'kind': 'IPAddressPool', 'metadata': {'namespace': check.META_NS}, 'spec': {'addresses': [check.VIP + '/32'], 'autoAssign': False}}
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'pool.yaml'
            target.write_text(yaml.safe_dump(document))
            self.assertTrue(check.validate_manifest(target)['passed'])
            for field, value in [('addresses', ['192.168.9.201-192.168.9.220']), ('autoAssign', True)]:
                altered = copy.deepcopy(document)
                altered['spec'][field] = value
                target.write_text(yaml.safe_dump(altered))
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, '测试池'):
                    check.validate_manifest(target)

    def test_metrics_separate_success_denial_and_ignore_comments(self):
        data = '\n'.join(['# coredns_cache_hits_total counter', 'coredns_cache_hits_total{server="dns://:53",type="success",zones="."} 8', 'coredns_cache_hits_total{server="dns://:53",type="denial",zones="."} 4', 'coredns_cache_misses_total{type="success"} 99'])
        self.assertEqual(check.cache_hits(data, 'success'), 8)
        self.assertEqual(check.cache_hits(data, 'denial'), 4)

    def test_delete_without_original_uid_receipt_is_refused(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(check, 'absent_or_owned', return_value={'metadata': {'uid': 'different'}}):
            records = Path(folder)
            check.save(records / 'state/object-service-lab-services-late.json', {'uid': 'original'})
            with self.assertRaisesRegex(ValueError, 'UID'):
                check.control('delete-plan', records, {'run': 'r'}, None, 'service', 'late', check.NS)

    def test_cleanup_before_crd_install_is_safe(self):
        with patch.object(check, 'get', return_value={'items': []}):
            self.assertFalse(check.control('delete-plan', Path('/unused'), {'run': 'r'}, None, 'ipaddresspool', check.POOL, check.META_NS)['exists'])

    def test_missing_or_failed_chapter_cannot_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            records = Path(folder)
            attempt = records / 'attempts/test'
            attempt.mkdir(parents=True)
            with self.assertRaises(FileNotFoundError):
                check.control('accept', records, {'run': 'r'}, attempt, '', '', '')
            for name in ['nodeport', 'affinity', 'loadbalancer', 'loadbalancer-reuse', 'discovery', 'aliases', 'dns-before', 'dns-after']:
                check.save(attempt / (name + '.json'), {'passed': name != 'dns-after'})
            with self.assertRaisesRegex(ValueError, '未通过'):
                check.control('accept', records, {'run': 'r'}, attempt, '', '', '')

    def test_reuse_requires_different_service_uid(self):
        with tempfile.TemporaryDirectory() as folder:
            records = Path(folder)
            attempt = records / 'attempts/test'
            for name in ['nodeport', 'affinity', 'loadbalancer', 'loadbalancer-reuse', 'discovery', 'aliases', 'dns-before', 'dns-after']:
                check.save(attempt / (name + '.json'), {'passed': True, 'service_uid': 'same-service', 'vip': check.VIP})
            with self.assertRaisesRegex(ValueError, '不同 Service UID'):
                check.control('accept', records, {'run': 'r'}, attempt, '', '', '')

    def test_externalname_negative_must_be_hostname_mismatch(self):
        state = {'ok': True, 'backends': {'p': 'u'}}
        alias = 'registry-alias.' + check.NS + '.svc.cluster.local'
        replies = [[], [{'echo': {'pod': 'p', 'uid': 'u', 'host': 'echo-alias.' + check.NS + '.svc.cluster.local:8080'}}], [{'status': 401}], [{'status': 0, 'error': 'x509: certificate signed by unknown authority'}]]
        with patch.object(check, 'fixtures', return_value=state), patch.object(check, 'net', side_effect=replies):
            with self.assertRaisesRegex(ValueError, 'SNI'):
                check.aliases({}, Path('/unused'))
        replies[-1] = [{'status': 0, 'error': 'x509: certificate is valid for harbor.k8s.internal.egon.top, not ' + alias}]
        with patch.object(check, 'fixtures', return_value=state), patch.object(check, 'net', side_effect=replies):
            self.assertTrue(check.aliases({}, Path('/unused'))['passed'])

    def test_vm_bindings_use_current_ip_and_interface_mac(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for index, (name, ip) in enumerate(check.WORKERS.items()):
                (root / ('host-' + name.split('.')[0] + '.txt')).write_text('active\n' + json.dumps([{'ifname': 'ens33', 'address': '00:0c:29:01:02:0' + str(index), 'addr_info': [{'local': ip}]}]) + '\n')
            bound = check.hosts(root, {'run': 'r'}, root)
            self.assertEqual(len(set(bound['worker_macs'].values())), 2)
            (root / 'host-worker01.txt').write_text('active\n')
            with self.assertRaisesRegex(ValueError, '接口只读取证'):
                check.hosts(root, {'run': 'r'}, root)

    def test_vip_arp_requires_known_worker_mac_and_normalizes_zeros(self):
        service = {'metadata': {'uid': 'loadbalancer'}, 'spec': {'allocateLoadBalancerNodePorts': False, 'loadBalancerSourceRanges': ['192.168.9.200/32']}, 'status': {'loadBalancer': {'ingress': [{'ip': check.VIP}]}}}
        context = {'mac_ip': '192.168.9.200', 'worker_macs': {'worker01.k8s.internal.egon.top': '00:0c:29:01:02:03'}}
        state = {'ok': True, 'echoes': [], 'backends': {}}
        with patch.object(check, 'get', return_value=service), patch.object(check, 'fixtures', return_value=state), patch.object(check, 'endpoints', return_value=True), patch.object(check, 'mac_request', return_value={'response': {'uid': 'p'}}), patch.object(check, 'call', return_value='(192.168.9.202) at 0:c:29:1:2:3 on en0'):
            self.assertEqual(check.lb(context, Path('/unused'), 'loadbalancer')['entry_vm'], 'worker01.k8s.internal.egon.top')
            context['worker_macs'] = {'worker01.k8s.internal.egon.top': '00:0c:29:11:22:33'}
            with self.assertRaisesRegex(ValueError, 'ARP 持有者'):
                check.lb(context, Path('/unused'), 'loadbalancer')

    def test_cleanup_keeps_foreign_objects_and_rejects_recreated_namespace(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            check.save(root / 'state/namespace.json', {'uid': 'original'})
            ns = {'metadata': {'uid': 'original'}}
            foreign = {'kind': 'Secret', 'metadata': {'name': 'foreign', 'labels': {}}}
            with patch.object(check, 'call', return_value='{}'), patch.object(check, 'absent_or_owned', return_value=ns), patch.object(check, 'get', return_value={'items': [foreign]}):
                with self.assertRaisesRegex(ValueError, '外来资源'):
                    check.cleanup_plan(root, {'run': 'r'})
                ns['metadata']['uid'] = 'new-namespace'
                with self.assertRaisesRegex(ValueError, 'Namespace UID'):
                    check.cleanup_plan(root, {'run': 'r'})


if __name__ == '__main__':
    unittest.main()
