"""复用正常演练的安装检查点，实跑授权 always 与中断 recover；不访问实际集群。"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

import yaml

source = Path(sys.argv[1]).resolve()
root = Path(__file__).resolve().parents[5]
python = Path.home() / '.venvs/cnpl-ansible/bin/python'
work = Path(tempfile.mkdtemp(prefix='cnpl-gateway-failure-recover-')).resolve()
for name in ['api.py', 'check.py', 'helm', 'kubectl', 'crane', 'extra.json', 'inventory.yml']:
    shutil.copy2(source / name, work / name)
shutil.copytree(source / 'checkpoint/records', work / 'records')
for name in ['store.json', 'components.json']:
    shutil.copy2(source / 'checkpoint' / name, work / name)
for name in ['api.py', 'extra.json']:
    p = work / name
    p.write_text(p.read_text().replace(str(source), str(work)))
path = work / 'check.py'
path.write_text(path.read_text().replace("if 'success'=='failure'", "if 'failure'=='failure'"))
records = work / 'records'
attempt = next(p for p in (records / 'attempts').iterdir() if p.name.endswith('-all'))
context = json.loads((records / 'context.json').read_text())
extra = json.loads((work / 'extra.json').read_text())
extra.update(gateway_attempt=str(attempt), gateway_context=context, gateway_run=context['run'])
(work / 'extra.json').write_text(json.dumps(extra))
env = dict(os.environ, ANSIBLE_CONFIG=str(root / 'ops/00-preparation/ansible/ansible.cfg'))


def run(playbook, log):
    with (work / log).open('w') as output:
        return subprocess.run([str(python.parent / 'ansible-playbook'), str(playbook), '-i', str(work / 'inventory.yml'), '-e', '@' + str(work / 'extra.json')], stdout=output, stderr=subprocess.STDOUT, env=env)


failure = run(root / 'ops/02-networking/ansible/playbooks/gateway-authorization.yml', 'failure-ansible.txt')
state = json.loads((work / 'store.json').read_text())
gateway = state['gateway/cnpl-gateway/primary']
original_refs = gateway['spec']['listeners'][1]['tls']['certificateRefs']
restored = original_refs == [{'group': '', 'kind': 'Secret', 'name': 'primary-tls'}] and 'referencegrant/lab-gateway-backends/allow-frontend-secret' not in state
expected_failure = failure.returncode == 2 and restored

# Simulate interruption after the exact recorded foreign reference and grant were applied.
gateway['spec']['listeners'][1]['tls']['certificateRefs'] = [{'group': '', 'kind': 'Secret', 'name': 'foreign-frontend', 'namespace': 'lab-gateway-backends'}]
gateway['metadata']['generation'] += 1
state['referencegrant/lab-gateway-backends/allow-frontend-secret'] = json.loads((attempt / 'applied-ReferenceGrant-allow-frontend-secret.json').read_text())
(work / 'store.json').write_text(json.dumps(state))
sys.path.insert(0, str(work))
import api
state = api.read()
api.reconcile(state)
api.reconcile(state)
api.write(state)
observer_attempt = records / 'attempts/interrupted-observer'
observer_attempt.mkdir()
(observer_attempt / 'disrupt-plan.json').write_text('{}')
observer_log = (work / 'observer.txt').open('w')
observer = subprocess.Popen([str(python), str(work / 'check.py'), 'observe', '--records', str(records), '--attempt', str(observer_attempt), '--output', str(observer_attempt / 'result.json')], stdout=observer_log, stderr=subprocess.STDOUT, env=env)
deadline = time.monotonic() + 10
while not (observer_attempt / 'observer-pid.json').exists() and observer.poll() is None and time.monotonic() < deadline:
    time.sleep(.1)
recovery_attempt = records / 'attempts/recovery'
recovery_attempt.mkdir()
for name in ['gateway-base.yaml', 'compare-values.yaml']:
    shutil.copy2(attempt / name, recovery_attempt / name)
extra.update(gateway_mode='recover', gateway_attempt=str(recovery_attempt))
(work / 'extra.json').write_text(json.dumps(extra))
recovery = run(root / 'ops/02-networking/ansible/playbooks/gateway-finish.yml', 'recover-ansible.txt')
try:
    observer.wait(timeout=10)
finally:
    if observer.poll() is None:
        observer.terminate()
        observer.wait(timeout=5)
    observer_log.close()
closed = json.loads((records / 'state/closed.json').read_text()) if (records / 'state/closed.json').exists() else {}
after = json.loads((work / 'store.json').read_text())
clean = not any(k.split('/')[1] in ['lab-gateway-app', 'lab-gateway-backends', 'lab-gateway-denied', 'ingress-compare'] for k in after)
report = {'harness_passed': expected_failure and recovery.returncode == 0 and clean and closed.get('cleanup_passed') and observer.returncode == 0, 'deliberate_failure_rc': failure.returncode, 'always_restored_certificate_and_revoked_grant': restored, 'recover_rc': recovery.returncode, 'temporary_namespaces_removed': clean, 'leftover_observer_stopped': observer.returncode == 0, 'closed': closed, 'work': str(work), 'kubernetes_and_network_are_stubs': True}
(work / 'report.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
for name in ['failure-ansible.txt', 'recover-ansible.txt']:
    print(name)
    print('\n'.join((work / name).read_text().splitlines()[-14:]))
sys.exit(0 if report['harness_passed'] else 1)
