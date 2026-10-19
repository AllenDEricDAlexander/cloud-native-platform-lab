"""聚焦身份、授权恢复、TLS、配置结构及不完整验收；不访问实际集群。"""
import copy
import base64
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

import check as c


class Guards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='cnpl-gateway-unit-')
        self.addCleanup(self.tmp.cleanup)
        self.records = Path(self.tmp.name)
        (self.records / 'state').mkdir()
        self.context = {'cluster_uid': 'cluster', 'run': 'run'}
        self.reg = patch.object(c, 'REGISTRY', self.records / 'components.json')
        self.reg.start()
        self.addCleanup(self.reg.stop)

    def doc(self, kind='Service', namespace='lab-gateway-app', name='web-v1'):
        return {'apiVersion': 'v1', 'kind': kind, 'metadata': {'name': name, 'namespace': namespace, 'uid': 'original', 'labels': {c.LABEL: 'run', 'cnpl.io/cluster-uid': 'cluster', 'cnpl.io/component': c.COMPONENT}}, 'spec': {}}

    def gateway(self):
        value = self.doc('Gateway', 'cnpl-gateway', 'primary')
        value['metadata']['generation'] = 2
        value['spec'] = {'listeners': [{'name': 'http'}, {'name': 'https', 'tls': {'certificateRefs': [{'group': '', 'kind': 'Secret', 'name': 'primary-tls'}]}}]}
        return value

    def test_secret_reads_never_allow_aggregate_json(self):
        for kind in ['Secret', 'secrets', 'pods,secrets', 'secrets.v1']:
            with self.subTest(kind=kind), patch.object(c, 'call') as call:
                with self.assertRaisesRegex(ValueError, 'Secret'):
                    c.get(kind)
                call.assert_not_called()

    def test_new_object_cannot_take_over_unbound_uid(self):
        obj = self.doc()
        with patch.object(c, 'optional', return_value=obj):
            with self.assertRaisesRegex(ValueError, 'UID'):
                c.object_plan(self.records, self.context, obj)
        c.record_object(self.records, self.context, obj)
        with patch.object(c, 'optional', return_value=obj):
            self.assertTrue(c.object_plan(self.records, self.context, obj)['exists'])
        other = copy.deepcopy(obj)
        other['metadata']['uid'] = 'replacement'
        with patch.object(c, 'optional', return_value=other):
            with self.assertRaisesRegex(ValueError, 'UID'):
                c.object_plan(self.records, self.context, obj)

    def test_cluster_resource_must_match_locked_spec(self):
        obj = self.doc('CustomResourceDefinition', None, 'x.gateway.example')
        obj['metadata'].pop('namespace')
        context = dict(self.context, cluster_resources={'CustomResourceDefinition/x.gateway.example': c.l2.digest({})})
        with patch.object(c, 'optional', return_value=None):
            self.assertFalse(c.object_plan(self.records, context, obj)['exists'])
            obj['spec']['scope'] = 'Namespaced'
            with self.assertRaisesRegex(ValueError, '锁定CRD'):
                c.object_plan(self.records, context, obj)

    def test_foreign_namespace_and_run_rejected(self):
        for namespace, run in [('kube-system', 'run'), ('lab-gateway-app', 'different')]:
            obj = self.doc(namespace=namespace)
            obj['metadata']['labels'][c.LABEL] = run
            with self.assertRaises(ValueError), patch.object(c, 'optional', return_value=None):
                c.object_plan(self.records, self.context, obj)

    def test_record_rejects_secret_payload(self):
        obj = self.doc('Secret')
        obj['data'] = {'tls.key': 'never-archive'}
        with self.assertRaisesRegex(ValueError, '禁止包含data'):
            c.record_object(self.records, self.context, obj)
        self.assertFalse(list((self.records / 'state').glob('object*')))

    def test_condition_requires_current_generation(self):
        obj = self.gateway()
        conditions = [{'type': 'Accepted', 'status': 'True', 'observedGeneration': 1}]
        self.assertFalse(c.condition(obj, conditions, 'Accepted', 'True'))
        conditions[0]['observedGeneration'] = 2
        self.assertTrue(c.condition(obj, conditions, 'Accepted', 'True'))
        self.assertFalse(c.condition(obj, None, 'Accepted', 'True'))

    def test_foreign_controller_status_cannot_satisfy_route(self):
        obj = self.doc('HTTPRoute')
        obj['metadata']['generation'] = 1
        obj['status'] = {'parents': [{'controllerName': 'foreign', 'parentRef': {'name': 'primary', 'namespace': 'cnpl-gateway'}, 'conditions': [{'type': 'ResolvedRefs', 'status': 'True', 'observedGeneration': 1}]}]}
        with patch.object(c, 'get', return_value=obj):
            with self.assertRaisesRegex(ValueError, '本代'):
                c.route_condition('HTTPRoute', 'web-v1')

    def test_certificate_patch_restores_only_original_field_and_uid(self):
        obj = self.gateway()
        c.record_object(self.records, self.context, obj)
        original = copy.deepcopy(obj['spec'])
        with patch.object(c, 'get', return_value=obj):
            change = c.frontend_plan(self.records, self.context)
            self.assertEqual(change['patch'][0], {'op': 'test', 'path': '/metadata/uid', 'value': 'original'})
            obj['spec']['listeners'][1]['tls']['certificateRefs'] = change['patch'][-1]['value']
            restore = c.frontend_plan(self.records, self.context, restore=True)
            self.assertEqual(restore['patch'][-1]['value'], original['listeners'][1]['tls']['certificateRefs'])
            self.assertEqual(restore['patch'][-1]['path'], '/spec/listeners/1/tls/certificateRefs')
            obj['metadata']['uid'] = 'replacement'
            with self.assertRaisesRegex(ValueError, 'UID'):
                c.frontend_plan(self.records, self.context, restore=True)

    def test_certificate_patch_does_not_overwrite_third_party_change(self):
        obj = self.gateway()
        c.record_object(self.records, self.context, obj)
        with patch.object(c, 'get', return_value=obj):
            c.frontend_plan(self.records, self.context)
            obj['spec']['listeners'][1]['tls']['certificateRefs'] = [{'name': 'someone-else'}]
            with self.assertRaisesRegex(ValueError, '其他操作'):
                c.frontend_plan(self.records, self.context, restore=True)

    def test_delete_checks_uid_and_narrow_allowlist(self):
        obj = self.doc('ReferenceGrant', 'lab-gateway-backends', 'allow-shared')
        c.record_object(self.records, self.context, obj)
        with patch.object(c, 'optional', return_value=obj):
            self.assertTrue(c.delete_plan(self.records, self.context, 'ReferenceGrant', 'allow-shared', 'lab-gateway-backends')['exists'])
            obj['metadata']['uid'] = 'foreign'
            with self.assertRaisesRegex(ValueError, 'UID'):
                c.delete_plan(self.records, self.context, 'ReferenceGrant', 'allow-shared', 'lab-gateway-backends')
        with self.assertRaisesRegex(ValueError, '越界'):
            c.delete_plan(self.records, self.context, 'Gateway', 'primary', 'cnpl-gateway')

    def test_acceptance_missing_case_cannot_pass(self):
        attempt = self.records / 'attempts/run'
        attempt.mkdir(parents=True)
        c.save(attempt / 'compatibility.json', {'passed': True})
        with self.assertRaises(FileNotFoundError):
            c.accept(self.records, self.context, attempt)

    def test_cleanup_refuses_foreign_secret_without_reading_data(self):
        ns = self.doc('Namespace', None, 'lab-gateway-app')
        ns['metadata'].pop('namespace')
        c.record_object(self.records, self.context, ns)
        with patch.object(c, 'optional', return_value=ns), patch.object(c, 'get', return_value={'items': []}), patch.object(c, 'crd_names', return_value=set()), patch.object(c, 'secret_list', return_value=[self.doc('Secret', name='foreign')]) as secrets:
            secrets.return_value[0]['metadata']['labels'][c.LABEL] = 'other'
            with self.assertRaisesRegex(ValueError, '外来资源'):
                c.cleanup_plan(self.records, self.context, 'lab-gateway-app')

    def test_stop_marker_exists_even_before_async_pid_is_written(self):
        attempt = self.records / 'attempts/slow-start'
        attempt.mkdir(parents=True)
        c.save(attempt / 'disrupt-plan.json', {})
        self.assertTrue(c.stop_observers(self.records)['stopped'])
        self.assertTrue((attempt / 'observer.stop').exists())

    def test_dns_preserves_existing_records_and_is_idempotent(self):
        path = self.records / 'before.zone'
        original = '$TTL 300\n@\tIN SOA dns. admin. (\n\t2026101702\t; serial\n\t300 )\nlegacy IN A 192.168.9.8\n'
        path.write_text(original)
        value = c.dns_plan(path)
        self.assertIn('legacy IN A 192.168.9.8\n', value['candidate'])
        self.assertEqual(value['serial_after'], 2026101901)
        path.write_text(value['candidate'])
        self.assertFalse(c.dns_plan(path)['changed'])
        path.write_text(original + 'demo.svc IN A 192.168.9.99\n')
        with self.assertRaisesRegex(ValueError, '接管'):
            c.dns_plan(path)

    def test_dns_rejects_serial_regression(self):
        path = self.records / 'before.zone'
        path.write_text('@ IN SOA dns. a. (\n 2027101702 ; serial\n 300 )\n')
        with self.assertRaisesRegex(ValueError, 'serial'):
            c.dns_plan(path)

    def test_response_identity_requires_uid_version_nonce_and_success(self):
        backends = {'p': {'uid': 'uid', 'version': 'v1'}}
        value = {'pod': 'p', 'uid': 'uid', 'version': 'v1', 'nonce': 'new', 'protocol': 'tcp'}
        c.probe.identity(value, backends, nonce='new', protocol='tcp')
        for field, wrong in [('uid', 'old'), ('nonce', 'cached'), ('version', 'v2'), ('protocol', 'udp')]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                c.probe.identity(dict(value, **{field: wrong}), backends, nonce='new', protocol='tcp')
        with self.assertRaises(ValueError):
            c.probe.identity({'status': 500, 'body': value}, backends)
        rpc = dict(value, status='SERVING', protocol='grpc')
        c.probe.identity(rpc, backends, protocol='grpc')

    def test_xds_rejects_missing_nack_or_nonfinite_metrics(self):
        names = ['envoy_listener_manager_lds_update_rejected', 'envoy_cluster_manager_cds_update_rejected', 'envoy_listener_manager_lds_update_success', 'envoy_cluster_manager_cds_update_success']
        good = '\n'.join(n + ' ' + ('0' if n.endswith('rejected') else '1') for n in names)
        self.assertEqual(len(c.probe.xds_metrics(good)), 4)
        for text in ['', good.replace('rejected 0', 'rejected 1'), good.replace('success 1', 'success 0'), good.replace('success 1', 'success 1e999')]:
            with self.assertRaises(ValueError):
                c.probe.xds_metrics(text)

    def test_private_grpc_client_does_not_inherit_public_proxy(self):
        reply = {'passed': True, 'status': 'SERVING', 'authority': c.probe.GRPC, 'pod': 'p', 'uid': 'u', 'version': 'v1', 'protocol': 'grpc'}
        result = c.subprocess.CompletedProcess([], 0, json.dumps(reply), '')
        with patch.dict(os.environ, {'HTTPS_PROXY': 'http://127.0.0.1:9', 'http_proxy': 'http://127.0.0.1:9'}), patch.object(c.probe.subprocess, 'run', return_value=result) as run:
            c.probe.grpc(Path('/fixture-client'), '192.168.9.201', {'p': {'uid': 'u', 'version': 'v1'}})
            self.assertFalse({'https_proxy', 'http_proxy', 'all_proxy'} & {k.lower() for k in run.call_args.kwargs['env']})

    def test_partial_jsonl_ignores_only_incomplete_last_row(self):
        path = self.records / 'traffic.jsonl'
        path.write_text('{"passed":true}\n{"passed":')
        self.assertEqual(c.complete_rows(path), [{'passed': True}])

    def test_single_pod_experiment_rejects_both_pods_replaced(self):
        attempt = self.records / 'attempts/fault'
        attempt.mkdir(parents=True)
        common = {'gateway_uid': 'g', 'service_uid': 's', 'deployment_uid': 'd'}
        c.save(attempt / 'disrupt-plan.json', {'pod': {'uid': 'old1'}, 'before': dict(common, data_pods=[{'uid': 'old1'}, {'uid': 'old2'}])})
        with patch.object(c, 'data_plane', return_value=dict(common, data_pods=[{'uid': 'new1'}, {'uid': 'old2'}])):
            self.assertIn('observed_mono', c.disrupt_state(self.context, attempt))
        with patch.object(c, 'data_plane', return_value=dict(common, data_pods=[{'uid': 'new1'}, {'uid': 'new2'}])):
            with self.assertRaisesRegex(ValueError, '另一数据面'):
                c.disrupt_state(self.context, attempt)

    def test_structural_schema_rejects_unknown_fields(self):
        definitions = [{'kind': 'CustomResourceDefinition', 'spec': {'group': 'test.io', 'names': {'kind': 'Sample'}, 'versions': [{'name': 'v1', 'served': True, 'schema': {'openAPIV3Schema': {'type': 'object', 'properties': {'apiVersion': {'type': 'string'}, 'kind': {'type': 'string'}, 'metadata': {'type': 'object'}, 'spec': {'type': 'object', 'properties': {'replicas': {'type': 'integer', 'minimum': 1}}}}}}}]}}]
        doc = {'apiVersion': 'test.io/v1', 'kind': 'Sample', 'metadata': {'name': 'a'}, 'spec': {'replicas': 2}}
        self.assertTrue(c.mat.validate_custom([doc], definitions)['passed'])
        doc['spec']['replica'] = 3
        with self.assertRaisesRegex(ValueError, 'replica'):
            c.mat.validate_custom([doc], definitions)

    def test_release_namespace_replacement_cannot_be_uninstalled(self):
        obj = self.doc('Namespace', None, 'ingress-compare')
        obj['metadata'].pop('namespace')
        c.record_object(self.records, self.context, obj)
        obj['metadata']['uid'] = 'foreign-namespace'
        values = self.records / 'attempts/contract/compare-values.yaml'
        with patch.object(c, 'helm_render', return_value=('cnpl-compare', 'ingress-compare', [], [])), patch.object(c, 'optional', return_value=obj), patch.object(c, 'call') as call:
            with self.assertRaisesRegex(ValueError, 'Namespace UID'):
                c.helm_guard(self.context, values, 'compare')
            call.assert_not_called()

    def test_null_service_ports_remain_a_waiting_condition(self):
        gateway = self.gateway()
        klass = self.doc('GatewayClass')
        klass['metadata']['generation'] = 1
        klass['status'] = {'conditions': [{'type': 'Accepted', 'status': 'True', 'observedGeneration': 1}]}
        gateway['status'] = {'conditions': [{'type': k, 'status': 'True', 'observedGeneration': 2} for k in ['Accepted', 'Programmed']]}
        service = self.doc(namespace='envoy-gateway-system', name='cnpl-primary')
        service['spec'] = {'allocateLoadBalancerNodePorts': False, 'loadBalancerSourceRanges': ['192.168.9.200/32'], 'ports': None}
        service['status'] = {'loadBalancer': {'ingress': [{'ip': '192.168.9.201'}]}}
        with patch.object(c, 'get', side_effect=[gateway, klass, service]):
            with self.assertRaisesRegex(ValueError, '端口尚未'):
                c.data_plane(dict(self.context, mac_ip='192.168.9.200'))

    def test_recovery_distinguishes_incomplete_main_from_formal_success(self):
        c.save(self.records / 'state/protected.json', {})
        with patch.object(c, 'stop_observers'), patch.object(c, 'optional', return_value=None), patch.object(c, 'protected', return_value={}), patch.object(c.l2.common.base, 'preflight', return_value=self.context), patch.object(c, 'main_exists', return_value={'exists': True}), patch.object(c, 'data_plane', side_effect=ValueError('not ready')):
            value = c.final(self.records, self.context, self.records / 'attempts/recovery')
            self.assertEqual(value['main_status'], 'incomplete_retained')
            self.assertFalse(value['formal_acceptance_passed'])
            self.assertEqual(value['pending_main_reason'], 'not ready')
            (self.records / 'passed.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'not ready'):
                c.final(self.records, self.context, self.records / 'attempts/recovery')


class Certificates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='cnpl-gateway-test-ca-')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        public, private = self.base / 'public', self.base / 'private'
        public.mkdir()
        (private / 'intermediate').mkdir(parents=True)
        now = datetime.now(timezone.utc)
        root_key, issuer_key = ec.generate_private_key(ec.SECP384R1()), ec.generate_private_key(ec.SECP384R1())
        root_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'isolated unit root')])
        issuer_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'isolated constrained issuer')])
        def builder(subject, issuer, key):
            return x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=60)).add_extension(x509.BasicConstraints(ca=True, path_length=1 if subject == root_name else 0), critical=True).add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False, data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
        root = builder(root_name, root_name, root_key).sign(root_key, hashes.SHA384())
        issuer = builder(issuer_name, root_name, issuer_key).add_extension(x509.NameConstraints(permitted_subtrees=[x509.DNSName('internal.egon.top')], excluded_subtrees=None), critical=True).sign(root_key, hashes.SHA384())
        pem = lambda cert: cert.public_bytes(serialization.Encoding.PEM)
        (public / 'cnpl-lab-root-ca.crt').write_bytes(pem(root))
        (public / 'cnpl-lab-issuing-ca.crt').write_bytes(pem(issuer))
        (private / 'intermediate/intermediate.crt').write_bytes(pem(issuer))
        (private / 'intermediate/intermediate.key').write_bytes(issuer_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.BestAvailableEncryption(b'unit-only')))
        for scope in [patch.object(c.pki, 'PUBLIC', public), patch.object(c.pki, 'PRIVATE', self.base / 'leaves'), patch.dict(os.environ, {'CNPL_PKI_DIR': str(private)})]:
            scope.start()
            self.addCleanup(scope.stop)

    def test_wrong_password_creates_no_leaf_and_no_cluster_mutation(self):
        with self.assertRaisesRegex(ValueError, '口令'):
            c.pki.issue(self.base / 'records', {'run': 'run'}, b'wrong')
        self.assertFalse((self.base / 'leaves').exists())

    def test_independent_signed_profiles_validated_and_reused(self):
        records = self.base / 'records'
        value = c.pki.issue(records, {'run': 'run'}, b'unit-only')
        self.assertEqual(set(value), {'primary', 'foreign', 'compare', 'backend'})
        self.assertEqual(len({v['sha256'] for v in value.values()}), 4)
        for item in value.values():
            self.assertEqual(Path(item['private_key']).stat().st_mode & 0o777, 0o600)
            self.assertTrue(Path(item['fullchain']).is_file())
        self.assertEqual(c.pki.existing(records, c.pki.authority()), value)
        raw = (records / 'state/tls.json').read_text()
        self.assertNotIn('PRIVATE KEY', raw)
        self.assertNotIn('unit-only', raw)
        value['primary']['sha256'] = 'tampered'
        (records / 'state/tls.json').write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, '指纹'):
            c.pki.existing(records, c.pki.authority())

    def test_wrong_leaf_key_is_rejected_before_any_api_call(self):
        records = self.base / 'records'
        values = c.pki.issue(records, {'run': 'run'}, b'unit-only')
        primary = values['primary']
        doc = {'apiVersion': 'v1', 'kind': 'Secret', 'metadata': {'name': 'primary-tls', 'namespace': 'cnpl-gateway', 'labels': {'cnpl.io/component': c.COMPONENT, 'cnpl.io/cluster-uid': 'cluster'}}, 'type': 'kubernetes.io/tls', 'data': {'tls.crt': base64.b64encode(Path(primary['fullchain']).read_bytes()).decode(), 'tls.key': base64.b64encode(Path(values['foreign']['private_key']).read_bytes()).decode()}}
        path = self.base / 'leaves/run/secret-test.json'
        path.write_text(json.dumps(doc))
        with patch.object(c, 'optional') as api:
            with self.assertRaisesRegex(ValueError, '私钥不匹配'):
                c.secret_plan(records, {'run': 'run', 'cluster_uid': 'cluster'}, path)
            api.assert_not_called()


if __name__ == '__main__':
    unittest.main()
