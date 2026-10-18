import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('service_check', Path(__file__).with_name('check.py'))
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def objects():
    run = 'test-run'
    deployment = {'metadata': {'uid': 'deployment', 'generation': 1, 'labels': {check.LABEL: run}}, 'spec': {'replicas': 2}, 'status': {'observedGeneration': 1, 'updatedReplicas': 2, 'readyReplicas': 2}}
    sets = [{'metadata': {'uid': 'replicaset', 'ownerReferences': [{'controller': True, 'uid': 'deployment'}]}}]
    pods = []
    endpoints = []
    for index, worker in enumerate(sorted(check.WORKERS)):
        name = 'backend-' + str(index)
        pod = {'metadata': {'name': name, 'uid': name, 'labels': {check.LABEL: run, 'app': 'svc-echo'}, 'ownerReferences': [{'controller': True, 'uid': 'replicaset'}]}, 'spec': {'nodeName': worker, 'automountServiceAccountToken': False, 'containers': [{'image': check.INPUTS['svc_backend_image']}]}, 'status': {'phase': 'Running', 'podIP': '10.244.8.' + str(10 + index), 'conditions': [{'type': 'Ready', 'status': 'True'}]}}
        pods.append(pod)
        endpoints.append({'addresses': [pod['status']['podIP']], 'conditions': {'ready': True}, 'targetRef': {'kind': 'Pod', 'uid': name}})
        pods.append({'metadata': {'name': 'client-' + str(index), 'uid': 'client-' + str(index), 'labels': {check.LABEL: run, 'app': 'svc-client'}}, 'spec': {'nodeName': worker, 'automountServiceAccountToken': False, 'containers': [{'image': check.INPUTS['svc_client_image']}]}, 'status': {'phase': 'Running', 'conditions': [{'type': 'Ready', 'status': 'True'}]}})
    service = {'metadata': {'uid': 'service', 'labels': {check.LABEL: run}}, 'spec': {'type': 'ClusterIP', 'clusterIP': '192.168.20.33', 'selector': {'app': 'svc-echo', check.LABEL: run}, 'ports': [{'name': 'http', 'port': 80, 'targetPort': 'http', 'protocol': 'TCP'}]}}
    slices = [{'metadata': {'ownerReferences': [{'uid': 'service'}]}, 'addressType': 'IPv4', 'ports': [{'name': 'http', 'port': 8080, 'protocol': 'TCP'}], 'endpoints': endpoints}]
    return deployment, sets, pods, service, slices


class ServiceEvidence(unittest.TestCase):
    def test_null_and_empty_slice_arrays_wait_instead_of_crashing_or_passing(self):
        for ports, endpoints in [(None, None), (None, []), ([], None), ([], [])]:
            with self.subTest(ports=ports, endpoints=endpoints):
                data = objects()
                data[-1][0].update(ports=ports, endpoints=endpoints)
                self.assertFalse(check.inspect(*data, 'test-run', 2, 2)['ok'])

    def test_pod_without_status_or_node_is_not_yet_converged(self):
        data = objects()
        data[2][0].pop('status')
        data[2][0]['spec'].pop('nodeName')
        self.assertFalse(check.inspect(*data, 'test-run', 2, 2)['ok'])

    def test_empty_placeholder_does_not_hide_complete_live_slices(self):
        data = objects()
        empty = copy.deepcopy(data[-1][0])
        empty.update(ports=None, endpoints=None)
        data[-1].append(empty)
        self.assertTrue(check.inspect(*data, 'test-run', 2, 2)['ok'])

    def test_cold_slice_converges_and_preserves_raw_poll_snapshots(self):
        cold = objects()
        cold[-1][0].update(ports=None, endpoints=None)
        warm = objects()
        def replies(data):
            deployment, sets, pods, service, slices = data
            return [deployment, {'items': sets}, {'items': pods}, service, {'items': slices}]
        with tempfile.TemporaryDirectory() as folder, patch.object(check, 'get', side_effect=replies(cold) + replies(warm)), patch.object(check.time, 'sleep'):
            output = Path(folder) / 'initial.json'
            result = check.wait({'run': 'test-run'}, 2, 2, None, output)
            self.assertTrue(result['ok'])
            raw = sorted(Path(folder).glob('*-input.json'))
            self.assertEqual(len(raw), 2)
            self.assertIsNone(json.loads(raw[0].read_text())['slices'][0]['ports'])

    def test_empty_slice_timeout_keeps_diagnostics(self):
        data = objects()
        data[-1][0].update(ports=None, endpoints=None)
        deployment, sets, pods, service, slices = data
        with tempfile.TemporaryDirectory() as folder, patch.object(check, 'get', side_effect=[deployment, {'items': sets}, {'items': pods}, service, {'items': slices}]), patch.object(check.time, 'monotonic', side_effect=[0, 91]):
            with self.assertRaisesRegex(ValueError, 'ports/endpoints 尚未就绪'):
                check.wait({'run': 'test-run'}, 2, 2, None, Path(folder) / 'initial.json')
            self.assertEqual(len(list(Path(folder).glob('*-input.json'))), 1)

    def test_backend_cache_requires_id_and_requested_repo_digest(self):
        for document in [{'status': None}, {'status': {}}, {'status': {'id': None}}, {'status': {'id': 'sha256:' + 'a' * 64, 'repoDigests': []}}]:
            with self.subTest(document=document), self.assertRaisesRegex(ValueError, '缓存'):
                check.backend_cache(document)
        self.assertTrue(check.backend_cache({'status': {'id': 'sha256:' + 'a' * 64, 'repoDigests': [check.INPUTS['svc_backend_image']]}})['backend_cached'])

    def test_completion_pointer_cannot_hide_failed_raw_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            records = root / 'ops/02-networking/records/run'
            check.save(records / 'passed.json', {'run': 'prior', 'cluster_uid': 'cluster', 'passed': True})
            check.save(records / 'closed.json', {'run': 'prior', 'cluster_uid': 'cluster', 'cleanup_passed': False})
            pointer = {'passed': True, 'cleanup_passed': True, 'cluster_uid': 'cluster', 'run': 'prior', 'next_step': '02.02.01', 'records': str(records), 'passed_receipt': 'passed.json', 'cleanup_receipt': 'closed.json', 'passed_receipt_sha256': hashlib.sha256((records / 'passed.json').read_bytes()).hexdigest(), 'cleanup_receipt_sha256': hashlib.sha256((records / 'closed.json').read_bytes()).hexdigest()}
            check.save(root / 'ops/02-networking/records/completed/02.01.json', pointer)
            with patch.object(check, 'ROOT', root):
                with self.assertRaisesRegex(ValueError, '清理回执'):
                    check.handoff('cluster')

    def test_two_ready_backends_match_endpoint_uids(self):
        state = check.inspect(*objects(), 'test-run', 2, 2)
        self.assertTrue(state['ok'])
        self.assertEqual(len(state['ready_backends']), 2)

    def test_stale_endpoint_uid_cannot_pass(self):
        data = objects()
        data[-1][0]['endpoints'][0]['targetRef']['uid'] = 'old-pod-at-same-ip'
        self.assertFalse(check.inspect(*data, 'test-run', 2, 2)['ok'])

    def test_unready_pod_must_be_removed_from_ready_endpoints(self):
        data = objects()
        data[0]['status']['readyReplicas'] = 1
        data[2][0]['status']['conditions'][0]['status'] = 'False'
        self.assertFalse(check.inspect(*data, 'test-run', 2, 1)['ok'])
        data[-1][0]['endpoints'][0]['conditions']['ready'] = False
        self.assertTrue(check.inspect(*data, 'test-run', 2, 1, {'name': 'backend-0', 'uid': 'backend-0'})['ok'])

    def test_duplicate_consistent_slices_are_deduplicated(self):
        data = objects()
        data[-1].append(copy.deepcopy(data[-1][0]))
        self.assertTrue(check.inspect(*data, 'test-run', 2, 2)['ok'])

    def test_foreign_service_owner_cannot_pass(self):
        data = objects()
        data[-1][0]['metadata']['ownerReferences'][0]['uid'] = 'foreign-service'
        self.assertFalse(check.inspect(*data, 'test-run', 2, 2)['ok'])

    def test_wrong_target_port_is_rejected(self):
        data = objects()
        data[3]['spec']['ports'][0]['targetPort'] = 9999
        with self.assertRaisesRegex(ValueError, '端口'):
            check.inspect(*data, 'test-run', 2, 2)

    def test_http_200_without_backend_identity_cannot_pass(self):
        state = check.inspect(*objects(), 'test-run', 2, 2)
        result = type('Result', (), {'returncode': 0, 'stdout': '{}', 'stderr': 'HTTP/1.1 200 OK'})()
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            graph = folder / 'graph.json'
            check.save(graph, state)
            with patch.object(check.subprocess, 'run', return_value=result):
                with self.assertRaisesRegex(ValueError, '请求'):
                    check.probe(graph, folder / 'probe.json')

    def test_non_object_or_invalid_identity_responses_are_failed_samples(self):
        state = check.inspect(*objects(), 'test-run', 2, 2)
        for body in ['null', '[]', '42', '{"pod":[],"uid":"invalid"}']:
            with self.subTest(body=body), tempfile.TemporaryDirectory() as folder:
                folder = Path(folder)
                check.save(folder / 'graph.json', state)
                result = type('Result', (), {'returncode': 0, 'stdout': body, 'stderr': 'HTTP/1.1 200 OK'})()
                with patch.object(check.subprocess, 'run', return_value=result), self.assertRaisesRegex(ValueError, '请求'):
                    check.probe(folder / 'graph.json', folder / 'probe.json')
                summary = json.loads((folder / 'probe.json').read_text())
                self.assertFalse(summary['passed'])
                self.assertEqual(len((folder / summary['requests_file']).read_text().splitlines()), 30)


if __name__ == '__main__':
    unittest.main()
