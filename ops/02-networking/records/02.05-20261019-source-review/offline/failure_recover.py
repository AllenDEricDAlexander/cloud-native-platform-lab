"""从隔离检查点执行真实 rotation always 和 recover，不访问实际集群。"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

source = Path(sys.argv[1]).resolve()
root = Path(__file__).resolve().parents[5]
python = Path.home() / '.venvs/cnpl-ansible/bin/python'
work = Path(tempfile.mkdtemp(prefix='cnpl-tls-failure-recover-')).resolve()
for name in ['api.py', 'check.py', 'kubectl', 'helm', 'crane', 'extra.json', 'inventory.yml']:
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
extra.update(tls_attempt=str(attempt), tls_run=context['run'], tls_context=context)
env = dict(os.environ, ANSIBLE_CONFIG=str(root / 'ops/00-preparation/ansible/ansible.cfg'))


def run(playbook, log):
    (work / 'extra.json').write_text(json.dumps(extra))
    with (work / log).open('w') as output:
        return subprocess.run([str(python.parent / 'ansible-playbook'), str(playbook), '-i', str(work / 'inventory.yml'), '-e', '@' + str(work / 'extra.json')], stdout=output, stderr=subprocess.STDOUT, env=env)


failure = run(root / 'ops/02-networking/ansible/playbooks/certificates-rotation.yml', 'failure-ansible.txt')
state = json.loads((work / 'store.json').read_text())
refs = state['gateway/cnpl-gateway/primary']['spec']['listeners'][1]['tls']['certificateRefs']
stable = state['certificate/cnpl-gateway/primary-auto']['spec']['duration'] == '168h'
restored = refs == context['gateway_original_refs']

# Simulate an interruption after the managed reference and short-period spec were applied.
state['gateway/cnpl-gateway/primary']['spec']['listeners'][1]['tls']['certificateRefs'] = [{'group': '', 'kind': 'Secret', 'name': 'primary-managed-tls'}]
cert = state['certificate/cnpl-gateway/primary-auto']
cert['spec'].update(duration='1h', renewBefore='58m')
cert['metadata']['generation'] += 1
(work / 'store.json').write_text(json.dumps(state))
recovery_attempt = records / 'attempts/recovery'
recovery_attempt.mkdir()
for name in ['controller-values.yaml', 'certificate-stable.yaml']:
    shutil.copy2(attempt / name, recovery_attempt / name)
extra.update(tls_mode='recover', tls_attempt=str(recovery_attempt))
recovery = run(root / 'ops/02-networking/ansible/playbooks/certificates-finish.yml', 'recover-ansible.txt')
state = json.loads((work / 'store.json').read_text())
closed = json.loads((records / 'state/closed.json').read_text()) if (records / 'state/closed.json').exists() else {}
no_lab = not any('/lab-tls/' in k or k == 'namespace//lab-tls' for k in state)
success = failure.returncode == 2 and stable and restored and recovery.returncode == 0 and no_lab and closed.get('cleanup_passed') and not closed.get('internal_passed')
report = {'harness_passed': bool(success), 'deliberate_failure_rc': failure.returncode, 'always_restored_reference': restored, 'always_left_stable_duration': stable, 'recover_rc': recovery.returncode, 'lab_namespace_removed': no_lab, 'closed': closed, 'work': str(work), 'kubernetes_gateway_and_clock_are_stubs': True}
(work / 'report.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
for name in ['failure-ansible.txt', 'recover-ansible.txt']:
    print(name)
    print('\n'.join((work / name).read_text().splitlines()[-12:]))
sys.exit(0 if success else 1)
