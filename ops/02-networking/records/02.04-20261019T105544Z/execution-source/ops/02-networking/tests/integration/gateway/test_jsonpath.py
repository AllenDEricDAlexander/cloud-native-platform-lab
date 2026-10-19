"""实际调用锁定 kubectl 的 JSONPath 解析器；API 仅为本机短期测试夹具。"""
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

import check as c


class KubectlJSONPath(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix='cnpl-jsonpath-')
        cls.addClassCleanup(cls.folder.cleanup)
        directory = Path(cls.folder.name)
        config = directory / 'kubeconfig'
        config.write_text('apiVersion: v1\nkind: Config\nclusters: []\nusers: []\ncontexts: []\n')
        cls.secret = {'apiVersion': 'v1', 'kind': 'Secret', 'metadata': {'name': 'leaf', 'namespace': 'fixture', 'uid': 'leaf-uid', 'labels': {'cnpl.io/gateway-run': 'fixture-run'}}, 'type': 'kubernetes.io/tls', 'data': {'tls.crt': base64.b64encode(b'PUBLIC CERTIFICATE FIXTURE').decode(), 'tls.key': 'PRIVATE-DATA-MUST-NOT-APPEAR'}}
        cls.empty = {'apiVersion': 'v1', 'kind': 'Secret', 'metadata': {'name': 'unlabelled', 'namespace': 'fixture', 'uid': 'empty-uid'}, 'type': 'Opaque'}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                path = urlsplit(self.path).path
                replies = {
                    '/api': {'apiVersion': 'v1', 'kind': 'APIVersions', 'versions': ['v1'], 'serverAddressByClientCIDRs': []},
                    '/apis': {'apiVersion': 'v1', 'kind': 'APIGroupList', 'groups': [{'name': 'apiextensions.k8s.io', 'versions': [{'groupVersion': 'apiextensions.k8s.io/v1', 'version': 'v1'}], 'preferredVersion': {'groupVersion': 'apiextensions.k8s.io/v1', 'version': 'v1'}}]},
                    '/api/v1': {'apiVersion': 'v1', 'kind': 'APIResourceList', 'groupVersion': 'v1', 'resources': [{'name': 'secrets', 'singularName': 'secret', 'namespaced': True, 'kind': 'Secret', 'verbs': ['get', 'list']}]},
                    '/apis/apiextensions.k8s.io/v1': {'apiVersion': 'v1', 'kind': 'APIResourceList', 'groupVersion': 'apiextensions.k8s.io/v1', 'resources': [{'name': 'customresourcedefinitions', 'singularName': 'customresourcedefinition', 'shortNames': ['crd', 'crds'], 'namespaced': False, 'kind': 'CustomResourceDefinition', 'verbs': ['get', 'list']}]},
                    '/apis/apiextensions.k8s.io/v1/customresourcedefinitions': {'apiVersion': 'apiextensions.k8s.io/v1', 'kind': 'CustomResourceDefinitionList', 'metadata': {}, 'items': [{'apiVersion': 'apiextensions.k8s.io/v1', 'kind': 'CustomResourceDefinition', 'metadata': {'name': name}} for name in ['gateways.gateway.networking.k8s.io', 'httproutes.gateway.networking.k8s.io']]},
                    '/api/v1/namespaces/fixture/secrets': {'apiVersion': 'v1', 'kind': 'SecretList', 'metadata': {}, 'items': [cls.secret, cls.empty]},
                    '/api/v1/namespaces/fixture/secrets/leaf': cls.secret,
                    '/api/v1/namespaces/fixture/secrets/unlabelled': cls.empty,
                }
                reply = replies.get(path)
                self.send_response(200 if reply else 404)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(reply or {'apiVersion': 'v1', 'kind': 'Status', 'reason': 'NotFound', 'code': 404}).encode())

        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.addClassCleanup(cls.server.server_close)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.addClassCleanup(cls.thread.join, 5)
        cls.addClassCleanup(cls.server.shutdown)
        cls.k = [str(Path.home() / '.cnpl/bin/kubectl'), '--kubeconfig', str(config), '--server', 'http://127.0.0.1:' + str(cls.server.server_port), '--cache-dir', str(directory / 'cache'), '--request-timeout=5s']

    def setUp(self):
        for scope in [patch.object(c, 'K', self.k), patch.object(c, '_crd_names', None)]:
            scope.start()
            self.addCleanup(scope.stop)

    def test_old_literal_newline_reproduces_real_parser_failure(self):
        expression = r'jsonpath={range .items[*]}{.metadata.name}{"\n"}{end}'.replace(r'\n', chr(10))
        with self.assertRaisesRegex(ValueError, 'unterminated quoted string'):
            c.call(self.k + ['get', 'crds', '-o', expression])

    def test_crd_names_and_cache_use_real_kubectl(self):
        self.assertEqual(c.crd_names(), {'gateways.gateway.networking.k8s.io', 'httproutes.gateway.networking.k8s.io'})
        with patch.object(c, 'call') as call:
            self.assertEqual(len(c.crd_names()), 2)
            call.assert_not_called()

    def test_secret_metadata_separators_and_missing_labels(self):
        value = c.secret_meta('leaf', 'fixture')
        self.assertEqual(value['metadata']['uid'], 'leaf-uid')
        self.assertEqual(value['metadata']['labels'], {'cnpl.io/gateway-run': 'fixture-run'})
        self.assertEqual(value['type'], 'kubernetes.io/tls')
        self.assertNotIn('PRIVATE-DATA', json.dumps(value))
        self.assertEqual(c.secret_meta('unlabelled', 'fixture')['metadata']['labels'], {})
        self.assertIsNone(c.secret_meta('missing', 'fixture'))

    def test_secret_list_tabs_and_newlines_hide_private_data(self):
        values = c.secret_list('fixture')
        self.assertEqual([v['metadata']['name'] for v in values], ['leaf', 'unlabelled'])
        self.assertEqual(values[1]['metadata']['labels'], {})
        self.assertNotIn('PRIVATE-DATA', json.dumps(values))

    def test_existing_dotted_public_certificate_path_stays_valid(self):
        with patch.object(c, 'tls_records', return_value={'fixture': {'sha256': 'public-fingerprint'}}), patch.object(c, 'record_object', return_value={'uid': 'leaf-uid'}), patch.object(c.pki, 'fingerprint', return_value='public-fingerprint'), patch.object(c.pki.x509, 'load_pem_x509_certificate') as parse:
            value = c.record_secret(Path(self.folder.name), {}, 'leaf', 'fixture', 'fixture')
            self.assertEqual(parse.call_args.args[0], b'PUBLIC CERTIFICATE FIXTURE')
            self.assertEqual(value['certificate_sha256'], 'public-fingerprint')


if __name__ == '__main__':
    unittest.main()
