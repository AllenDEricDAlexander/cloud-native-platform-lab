"""02.05 的受限测试 CA、真实 TLS 客户端、UID 与部分验收回归；不接触真实根私钥。"""
import base64
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import ssl
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

import check as c


class Authority(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='cnpl-certificates-ca-')
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        base = self.folder / 'pki'
        (base / 'root').mkdir(parents=True)
        key = ec.generate_private_key(ec.SECP384R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'isolated root')])
        now = datetime.now(timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=1000))
                .add_extension(x509.BasicConstraints(ca=True, path_length=1), True)
                .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False, data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True, encipher_only=False, decipher_only=False), True)
                .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), False)
                .sign(key, hashes.SHA384()))
        self.public = base / 'root/root.crt'
        self.public.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        (base / 'root/root.key').write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.BestAvailableEncryption(b'unit-root')))
        for scope in [patch.dict(os.environ, {'CNPL_PKI_DIR': str(base)}), patch.object(c.pki, 'PUBLIC', self.public), patch.object(c.pki, 'PRIVATE', self.folder / 'private')]:
            scope.start()
            self.addCleanup(scope.stop)
        self.records = self.folder / 'records'
        self.context = {'cluster_uid': 'offline-cluster', 'run': 'unit'}

    def test_wrong_root_password_does_not_create_materials(self):
        with self.assertRaisesRegex(ValueError, '根 CA 口令'):
            c.pki.prepare(self.records, self.context, b'wrong')
        self.assertFalse(c.pki.PRIVATE.exists())

    def test_new_ca_scope_key_permissions_and_cached_reuse(self):
        value = c.pki.prepare(self.records, self.context, b'unit-root')
        cert = x509.load_pem_x509_certificate(Path(value['issuer']['certificate']).read_bytes())
        self.assertEqual(cert.extensions.get_extension_for_class(x509.BasicConstraints).value.path_length, 0)
        self.assertEqual(set(cert.extensions.get_extension_for_class(x509.NameConstraints).value.permitted_subtrees), {x509.DNSName(n) for n in c.pki.NAMES})
        self.assertEqual(len(value['profiles']), 5)
        for item in [value['issuer']] + list(value['profiles'].values()):
            self.assertEqual(Path(item['private_key']).stat().st_mode & 0o777, 0o600)
        self.assertEqual(c.pki.prepare(self.records, self.context), value)
        raw = (self.records / 'state/materials.json').read_text()
        self.assertNotIn('PRIVATE KEY', raw)
        self.assertNotIn('unit-root', raw)

    def test_ca_public_projection_does_not_require_leaf_san(self):
        materials = c.pki.prepare(self.records, self.context, b'unit-root')
        encoded = base64.b64encode(Path(materials['issuer']['fullchain']).read_bytes()).decode()
        with patch.object(c, 'call', return_value=encoded):
            value = c.public_certificate('issuer', 'cnpl-gateway')
        self.assertEqual(value['sans'], [])
        self.assertEqual(value['sha256'], materials['issuer']['sha256'])

    def test_python_and_go_really_reject_each_bad_certificate(self):
        materials = c.pki.prepare(self.records, self.context, b'unit-root')
        client = c.mat.lock()['client']['path']
        for profile in ['valid', 'san', 'unknown', 'incomplete', 'expired']:
            with self.subTest(profile=profile):
                class Handler(BaseHTTPRequestHandler):
                    def log_message(self, *args):
                        pass

                    def do_GET(self):
                        body = json.dumps({'nonce': self.headers.get('X-Cnpl-Nonce'), 'uid': 'test-pod'}).encode()
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(body)

                server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                item = materials['profiles'][profile]
                context.load_cert_chain(item['fullchain'], item['private_key'])
                server.socket = context.wrap_socket(server.socket, server_side=True)
                worker = threading.Thread(target=server.serve_forever, daemon=True)
                worker.start()
                try:
                    if profile == 'valid':
                        row = c.gw.probe.http('127.0.0.1', '/v1', port=server.server_port, ca=self.public)
                        self.assertEqual(row['status'], 200)
                    else:
                        with self.assertRaises(ssl.SSLCertVerificationError) as error:
                            c.gw.probe.http('127.0.0.1', '/v1', port=server.server_port, ca=self.public)
                        codes = {'san': [62], 'unknown': [18, 19, 20, 21], 'incomplete': [20, 21], 'expired': [10]}
                        self.assertIn(error.exception.verify_code, codes[profile])
                    reply = subprocess.run([client, '--target', '127.0.0.1:' + str(server.server_port), '--name', c.pki.NAMES[0], '--ca', str(self.public), '--nonce', 'unique'], capture_output=True, text=True, timeout=10)
                    value = json.loads(reply.stdout)
                    expected = {'valid': '', 'san': 'hostname', 'unknown': 'unknown_authority', 'incomplete': 'unknown_authority', 'expired': 'validity'}
                    self.assertEqual(value.get('error_class', ''), expected[profile])
                    self.assertEqual(reply.returncode, 0 if profile == 'valid' else 1)
                finally:
                    server.shutdown()
                    worker.join(5)
                    server.server_close()


class Guards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='cnpl-tls-guards-')
        self.addCleanup(self.tmp.cleanup)
        self.records = Path(self.tmp.name)
        (self.records / 'state').mkdir()
        self.context = {'cluster_uid': 'cluster', 'run': 'run'}
        scope = patch.object(c, 'REGISTRY', self.records / 'components.json')
        scope.start()
        self.addCleanup(scope.stop)

    def obj(self, kind='Service', name='fault-backend', ns='lab-tls'):
        return {'apiVersion': 'v1', 'kind': kind, 'metadata': {'name': name, 'namespace': ns, 'uid': 'original', 'labels': {c.LABEL: 'run', 'cnpl.io/component': c.COMPONENT, 'cnpl.io/cluster-uid': 'cluster'}}, 'spec': {}}

    def test_scope_and_uid_guards(self):
        obj = self.obj()
        with patch.object(c, 'optional', return_value=obj):
            with self.assertRaisesRegex(ValueError, '未登记'):
                c.object_plan(self.records, self.context, obj)
        c.record(self.records, self.context, obj)
        with patch.object(c, 'optional', return_value=obj):
            self.assertTrue(c.object_plan(self.records, self.context, obj)['exists'])
            obj['metadata']['uid'] = 'foreign'
            with self.assertRaisesRegex(ValueError, '替换'):
                c.object_plan(self.records, self.context, obj)
        with self.assertRaisesRegex(ValueError, '范围'):
            c.object_plan(self.records, self.context, self.obj(ns='kube-system'))

    def test_record_never_accepts_secret_payload(self):
        for key in ['data', 'stringData']:
            obj = self.obj('Secret', 'tls-test-valid')
            obj[key] = {'tls.key': 'not-archive'}
            with self.assertRaisesRegex(ValueError, '私有数据'):
                c.record(self.records, self.context, obj)

    def test_renewal_requires_new_key_same_uid_and_timer(self):
        attempt = self.records / 'attempts/renewal'
        attempt.mkdir(parents=True)
        now = datetime.now(timezone.utc)
        first = {'certificate_uid': 'c', 'secret_uid': 's', 'sha256': 'old', 'spki_sha256': 'key', 'revision': 1, 'renewal_time': now.isoformat()}
        c.save(attempt / 'certificate-initial.json', first)
        second = dict(first, sha256='new', spki_sha256='key', revision=2, not_before=now.isoformat())
        with patch.object(c, 'main_tls', return_value=second):
            with self.assertRaisesRegex(ValueError, '等待'):
                c.rotation(self.records, self.context, attempt)
            second['spki_sha256'] = 'new-key'
            self.assertTrue(c.rotation(self.records, self.context, attempt)['automatic_timer_renewal'])
            second['secret_uid'] = 'replacement'
            with self.assertRaisesRegex(ValueError, '重建'):
                c.rotation(self.records, self.context, attempt)

    def test_public_blocked_never_becomes_full_phase_pass(self):
        attempt = self.records / 'attempts/accept'
        attempt.mkdir(parents=True)
        names = ['compatibility', 'controller-ready', 'policies-ready', 'authorization', 'certificate-initial', 'rotation', 'steady', 'fault-valid', 'fault-san', 'fault-unknown', 'fault-incomplete', 'fault-expired', 'fault-restored']
        for name in names:
            c.save(attempt / (name + '.json'), {'passed': True})
        c.save(attempt / 'public.json', {'status': 'BLOCKED', 'public_passed': False})
        c.save(self.records / 'state/protected.json', {})
        c.save(self.records / 'state/source.json', {})
        with patch.object(c, 'protected', return_value={}), patch.object(c, 'source', return_value={}), patch.object(c, 'main_unchanged', return_value={}), patch.object(c, 'steady', return_value={'passed': True}):
            result = c.accept(self.records, self.context, attempt)
            self.assertTrue(result['internal_passed'])
            self.assertFalse(result['passed'])
            self.assertFalse(result['phase_complete'])
            (attempt / 'fault-expired.json').unlink()
            with self.assertRaises(FileNotFoundError):
                c.accept(self.records, self.context, attempt)

    def test_incomplete_recovery_does_not_claim_acceptance(self):
        with patch.object(c, 'optional', return_value=None):
            value = c.final(self.records, self.context, self.records)
        self.assertTrue(value['cleanup_passed'])
        self.assertFalse(value['internal_passed'])
        self.assertFalse(value['phase_complete'])

    def test_gateway_patch_has_uid_test_and_refuses_third_party_ref(self):
        obj = self.obj('Gateway', 'primary', 'cnpl-gateway')
        original = [{'group': '', 'kind': 'Secret', 'name': 'primary-tls'}]
        obj['spec'] = {'listeners': [{'name': 'http'}, {'name': 'https', 'tls': {'certificateRefs': original}}]}
        context = dict(self.context, main_original={'Gateway': {'uid': 'original'}}, gateway_original_refs=original)
        with patch.object(c, 'get', return_value=obj):
            plan = c.gateway_patch(self.records, context)
            self.assertEqual(plan['patch'][0]['path'], '/metadata/uid')
            obj['spec']['listeners'][1]['tls']['certificateRefs'] = [{'name': 'someone-else'}]
            with self.assertRaisesRegex(ValueError, '其他操作'):
                c.gateway_patch(self.records, context, True)


if __name__ == '__main__':
    unittest.main()
