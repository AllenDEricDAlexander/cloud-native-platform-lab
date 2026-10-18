import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('network_check', Path(__file__).with_name('check.py'))
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class EvidenceGuards(unittest.TestCase):
    def test_chart_and_cri_digest_references_match_without_accepting_drift(self):
        lock = {'version': '1.20.2', 'source': 'quay.io/cilium/hubble-relay@sha256:abc'}
        self.assertTrue(check.relay_image_matches(lock['source'], lock))
        self.assertTrue(check.relay_image_matches('quay.io/cilium/hubble-relay:v1.20.2@sha256:abc', lock))
        self.assertFalse(check.relay_image_matches('quay.io/cilium/hubble-relay:v1.20.2@sha256:changed', lock))
        self.assertFalse(check.relay_image_matches('other.example/relay:v1.20.2@sha256:abc', lock))

    def test_cleanup_rejects_changed_namespace_uid(self):
        with tempfile.TemporaryDirectory() as folder:
            records = Path(folder)
            check.save(records / 'context.json', {'run': 'ours'})
            check.save(records / 'state/lab-net.json', {'uid': 'original'})
            namespace = {'metadata': {'uid': 'replacement', 'labels': {check.LABEL: 'ours'}}}
            with patch.object(check, 'call', return_value=json.dumps(namespace)):
                with self.assertRaisesRegex(ValueError, 'UID'):
                    check.cleanup_plan(records)

    def test_cleanup_preserves_foreign_resource(self):
        with tempfile.TemporaryDirectory() as folder:
            records = Path(folder)
            check.save(records / 'context.json', {'run': 'ours'})
            namespace = {'metadata': {'uid': 'original', 'labels': {check.LABEL: 'ours'}}}
            foreign = {'kind': 'ConfigMap', 'metadata': {'name': 'user-settings', 'labels': {}}}
            with patch.object(check, 'call', return_value=json.dumps(namespace)), patch.object(check, 'get', return_value={'items': [foreign]}):
                with self.assertRaisesRegex(ValueError, '外来资源'):
                    check.cleanup_plan(records)

    def test_rollback_preserves_preexisting_hubble_access(self):
        with tempfile.TemporaryDirectory() as folder:
            records = Path(folder)
            check.save(records / 'state/hubble.json', {'owned': False})
            with patch.object(check, 'call', side_effect=AssertionError('must not inspect/delete policy')):
                self.assertEqual(check.rollback_policy(records), {'remove': False})

    def test_request_count_is_part_of_acceptance(self):
        pod = {'metadata': {'namespace': 'lab-net', 'name': 'net-one'}}
        output = '{"passed":true}\n'
        result = type('Result', (), {'returncode': 0, 'stdout': output, 'stderr': ''})()
        with tempfile.TemporaryDirectory() as folder, patch.object(check.subprocess, 'run', return_value=result):
            with self.assertRaisesRegex(ValueError, '数量'):
                check.execute(pod, [check.probe('http', 'http', 'http://example/', count=5)], Path(folder) / 'requests.jsonl')

    def flow_context(self):
        source = {'metadata': {'name': 'source'}, 'spec': {'nodeName': 'worker01.k8s.internal.egon.top'}}
        peer = {'status': {'podIP': '10.244.9.2'}}
        agent = {'metadata': {'name': 'agent', 'labels': {'k8s-app': 'cilium'}}, 'spec': {'nodeName': source['spec']['nodeName']}}
        return source, peer, agent

    def test_hubble_lost_events_cannot_pass(self):
        source, peer, agent = self.flow_context()
        def get(kind, name=None, namespace=None):
            return {'items': [agent]} if kind == 'pods' else {'spec': {'clusterIP': '192.168.20.20'}}
        def call(args, **kwargs):
            return 'Connected Nodes: 10/10' if args[-1] == 'status' else '{"lost_events":{"num_events_lost":1}}\n'
        with tempfile.TemporaryDirectory() as folder, patch.object(check, 'pods', return_value=([source], peer)), patch.object(check, 'get', side_effect=get), patch.object(check, 'call', side_effect=call):
            with self.assertRaisesRegex(ValueError, '丢事件'):
                check.flows('deny', '2026-10-18T00:00:00Z', Path(folder) / 'flows.jsonl')

    def test_unrelated_drop_reason_cannot_pass_policy_test(self):
        source, peer, agent = self.flow_context()
        def get(kind, name=None, namespace=None):
            return {'items': [agent]} if kind == 'pods' else {'spec': {'clusterIP': '192.168.20.20'}}
        def call(args, **kwargs):
            return 'Connected Nodes: 10/10' if args[-1] == 'status' else '{"flow":{"verdict":"DROPPED","drop_reason_desc":"INVALID_SOURCE_IP"}}\n'
        with tempfile.TemporaryDirectory() as folder, patch.object(check, 'pods', return_value=([source], peer)), patch.object(check, 'get', side_effect=get), patch.object(check, 'call', side_effect=call), patch.object(check.time, 'sleep'):
            with self.assertRaisesRegex(ValueError, '没有本次'):
                check.flows('deny', '2026-10-18T00:00:00Z', Path(folder) / 'flows.jsonl')


if __name__ == '__main__':
    unittest.main()
