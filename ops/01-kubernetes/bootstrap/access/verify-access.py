#!/usr/bin/env python3
"""用真实独立证书检查允许/拒绝请求；只创建短时 ConfigMap，不启动工作负载。"""
import argparse
import json
from pathlib import Path
import subprocess

import yaml


def request(kubectl, args, payload=None):
    return subprocess.run(kubectl + args, input=json.dumps(payload) if payload else None,
                          capture_output=True, text=True, timeout=30)


def success(kubectl, args, payload=None):
    result = request(kubectl, args, payload)
    if result.returncode:
        raise ValueError('请求失败：' + ' '.join(args) + '\n' + result.stderr)
    return result.stdout


def forbidden(kubectl, namespace):
    resource = {'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {'name': 'cnpl-forbidden-probe', 'namespace': namespace}, 'data': {'probe': 'non-sensitive'}}
    result = request(kubectl, ['create', '--dry-run=server', '-f', '-', '-o', 'name'], resource)
    if result.returncode == 0 or 'Forbidden' not in result.stderr:
        raise ValueError('预期真实 Forbidden，不能把成功、认证失败或网络错误当作权限拒绝。')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=Path.home() / '.cnpl-secrets/access/lab-primary')
    parser.add_argument('--kubectl', default=str(Path.home() / '.cnpl/bin/kubectl'))
    parser.add_argument('--admin-kubeconfig', default=str(Path.home() / '.cnpl-secrets/kubeconfig-lab-primary'))
    args = parser.parse_args()
    identities = yaml.safe_load((Path(__file__).parent / 'identities.yaml').read_text())['phase01_access_identities']
    admin = [args.kubectl, '--kubeconfig', args.admin_kubeconfig, '--request-timeout=15s']
    for identity in identities:
        if identity['role'] == 'recovery':
            continue
        client = [args.kubectl, '--kubeconfig', str(args.directory / (identity['client'] + '.conf')),
                  '--context', identity['context'], '--request-timeout=15s']
        who = json.loads(success(client, ['auth', 'whoami', '-o', 'json']))['status']['userInfo']
        if who['username'] != identity['name'] or set(who.get('groups', [])) & {'system:masters', 'kubeadm:cluster-admins'}:
            raise ValueError('实际认证身份错误或携带管理员组。')
        operator = identity['role'] == 'operator'
        checks = [
            (['list', 'nodes'], True),
            (['list', 'pods', '--all-namespaces'], True),
            (['get', 'secrets', '-n', 'kube-system'], False),
            (['get', 'secrets', '-n', 'lab-core'], False),
            (['get', 'nodes', '--subresource=proxy'], False),
            (['create', 'namespaces'], False),
            (['create', 'clusterrolebindings'], False),
            (['impersonate', 'users'], False),
            (['create', 'configmaps', '-n', 'lab-core'], operator),
            (['create', 'pods', '--subresource=exec', '-n', 'lab-core'], operator),
            (['create', 'configmaps', '-n', 'kube-system'], False),
        ]
        for check, allowed in checks:
            result = request(client, ['auth', 'can-i', *check, '--quiet'])
            errors = [line for line in result.stderr.splitlines() if line.strip() and not (line.startswith('Warning: resource ') and 'is not namespace scoped' in line)]
            if result.returncode != (0 if allowed else 1) or errors:
                raise ValueError(identity['name'] + ' 权限不符：' + ' '.join(check) + '\n' + result.stderr)
        success(client, ['get', 'nodes', '-o', 'name'])
        forbidden(client, 'kube-system' if operator else 'lab-core')
        if operator:
            resource = {'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {'generateName': 'cnpl-access-probe-', 'namespace': 'lab-core'}, 'data': {'probe': identity['name']}}
            created = json.loads(success(client, ['create', '-f', '-', '-o', 'json'], resource))
            name = created['metadata']['name']
            try:
                actual = json.loads(success(client, ['-n', 'lab-core', 'get', 'configmap', name, '-o', 'json']))
                if actual['data'] != resource['data']:
                    raise ValueError('实验运维写入/读取不一致。')
            finally:
                deleted = request(client, ['-n', 'lab-core', 'delete', 'configmap', name, '--ignore-not-found=true'])
                if deleted.returncode:
                    success(admin, ['-n', 'lab-core', 'delete', 'configmap', name, '--ignore-not-found=true'])
                    raise ValueError('运维身份无法清理测试 ConfigMap；已用引导管理员清理。')
        print(identity['context'] + ': authenticated CN, allow/deny matrix and real requests PASS', flush=True)
    recovery = [args.kubectl, '--kubeconfig', str(args.directory / 'recovery/recovery.conf'), '--request-timeout=15s']
    who = json.loads(success(recovery, ['auth', 'whoami', '-o', 'json']))['status']['userInfo']
    if who['username'] != 'cnpl-recovery-admin' or 'system:masters' not in who.get('groups', []):
        raise ValueError('恢复身份不符。')
    success(recovery, ['get', 'clusterrolebindings', '-o', 'name'])
    for target in ['cp01', 'cp02', 'cp03', 'vip']:
        success(recovery, ['--context', 'lab-primary-recovery-' + target, 'get', '--raw=/readyz'])
        print('recovery ' + target + ' TLS/API PASS', flush=True)
    print('ACCESS ACCEPTANCE PASS: four independent restricted identities, recovery identity, direct API contexts; temporary ConfigMaps cleaned.')
    print('adminhost certificate tested from Mac; transfer/login on planned .15 remains pending.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.TimeoutExpired) as error:
        raise SystemExit('ACCESS ACCEPTANCE FAIL: ' + str(error))
