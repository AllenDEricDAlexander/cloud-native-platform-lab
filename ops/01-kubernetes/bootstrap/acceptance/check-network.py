#!/usr/bin/env python3
"""从每个现有诊断 Pod 检查十节点 HTTP、ClusterIP、Service DNS 和内外域解析；不创建/删除资源。"""
import argparse
import ipaddress
import json
from pathlib import Path
import subprocess


NAMESPACE = 'cnpl-phase01-acceptance'
EXPECTED = {name + '.k8s.internal.egon.top' for name in [
    'cp01', 'cp02', 'cp03', 'infra01', 'infra02', 'storage01', 'storage02', 'storage03', 'worker01', 'worker02']}


def command(argv, timeout=30):
    result = subprocess.run(argv, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise ValueError(f'命令失败 rc={result.returncode}: {" ".join(argv[:8])}\n{result.stdout}\n{result.stderr}')
    return result.stdout.strip()


def inspect_pods(pods):
    if len(pods) != 10 or {pod['spec']['nodeName'] for pod in pods} != EXPECTED:
        raise ValueError('必须十个诊断 Pod、每个预期节点恰好一个。')
    addresses = set()
    for pod in pods:
        if pod['spec'].get('hostNetwork', False):
            raise ValueError('验收必须使用普通 Pod 网络。')
        if not any(item['type'] == 'Ready' and item['status'] == 'True' for item in pod['status'].get('conditions', [])):
            raise ValueError(pod['metadata']['name'] + ' 尚未 Ready。')
        address = pod['status']['podIP']
        if ipaddress.ip_address(address) not in ipaddress.ip_network('10.244.0.0/16') or address in addresses:
            raise ValueError('诊断 Pod 地址不属于规划 Pod CIDR，或有重复。')
        addresses.add(address)


# 每个源 Pod 单次 exec；set -e 使任一 HTTP/DNS 失败都终止该源的检查。
PROBE = r'''
set -eu
service_ip=$1
shift
for target in "$@"; do
  ip=${target%%=*}
  expected=${target#*=}
  if ! response=$(wget -T 5 -q -O - "http://$ip:8080/"); then
    printf 'HTTP -> %s (%s) FAIL\n' "$expected" "$ip" >&2
    exit 1
  fi
  if test "$response" != "$expected"; then
    printf 'HTTP %s expected=%s actual=%s FAIL\n' "$ip" "$expected" "$response" >&2
    exit 1
  fi
  printf 'HTTP -> %s (%s) PASS\n' "$expected" "$ip"
done
for query in "network-smoke.cnpl-phase01-acceptance.svc.cluster.local=$service_ip" kubernetes.default.svc.cluster.local=192.168.20.1 harbor.k8s.internal.egon.top=192.168.9.12 kubernetes.io=; do
  name=${query%%=*}
  expected=${query#*=}
  if ! answer=$(nslookup -type=A "$name" 192.168.20.10 2>&1); then
    printf 'DNS %s FAIL\n%s\n' "$name" "$answer" >&2
    exit 1
  fi
  printf '%s\n' "$answer"
  if test -n "$expected"; then
    found=0
    set -f
    for word in $answer; do
      if test "$word" = "$expected"; then found=1; fi
    done
    if test "$found" != 1; then
      printf 'DNS %s expected=%s FAIL\n' "$name" "$expected" >&2
      exit 1
    fi
  fi
  printf 'DNS %s PASS\n' "$name"
done
for endpoint in "$service_ip" network-smoke.cnpl-phase01-acceptance.svc.cluster.local; do
  if ! response=$(wget -T 5 -q -O - "http://$endpoint:8080/"); then
    printf 'SERVICE %s FAIL\n' "$endpoint" >&2
    exit 1
  fi
  found=0
  for target in "$@"; do
    if test "$response" = "${target#*=}"; then found=1; fi
  done
  if test "$found" != 1; then
    printf 'SERVICE %s unexpected backend=%s FAIL\n' "$endpoint" "$response" >&2
    exit 1
  fi
  printf 'SERVICE %s -> %s PASS\n' "$endpoint" "$response"
done
'''

SHORT_PROBE = r'''
# BusyBox 在显式传 DNS 服务器时不读取 search；展开实际首个搜索域，随后用 wget 验证 libc 短名解析。
suffix=$(awk '$1 == "search" {print $2; exit}' /etc/resolv.conf)
if test "$suffix" != cnpl-phase01-acceptance.svc.cluster.local; then
  printf 'DNS unexpected search suffix=%s FAIL\n' "$suffix" >&2
  exit 1
fi
if ! answer=$(nslookup -type=A "network-smoke.$suffix" 192.168.20.10 2>&1); then
  printf 'DNS search suffix FAIL\n%s\n' "$answer" >&2
  exit 1
fi
printf '%s\n' "$answer"
found=0
for word in $answer; do
  if test "$word" = "$service_ip"; then found=1; fi
done
if test "$found" != 1; then printf 'DNS search suffix wrong address FAIL\n' >&2; exit 1; fi
printf 'DNS network-smoke (search suffix) PASS\n'
if ! response=$(wget -T 5 -q -O - http://network-smoke:8080/); then
  printf 'SERVICE network-smoke short-name resolver FAIL\n' >&2
  exit 1
fi
found=0
for target in "$@"; do
  if test "$response" = "${target#*=}"; then found=1; fi
done
test "$found" = 1
printf 'SERVICE network-smoke -> %s PASS\n' "$response"
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kubectl', default=str(Path.home() / '.cnpl/bin/kubectl'))
    parser.add_argument('--kubeconfig', default=str(Path.home() / '.cnpl-secrets/kubeconfig-lab-primary'))
    parser.add_argument('--short-name', action='store_true', help='01.03 额外验证 Service 短名的搜索域解析和 HTTP')
    args = parser.parse_args()
    kubectl = [args.kubectl, '--kubeconfig', args.kubeconfig, '--request-timeout=20s']
    server = command(kubectl + ['config', 'view', '--minify', '-o', 'jsonpath={.clusters[0].cluster.server}'])
    if server != 'https://api.k8s.internal.egon.top:6443':
        raise ValueError('kubeconfig 当前 Context 的 API 地址与本实验集群不符。')
    pods = json.loads(command(kubectl + ['-n', NAMESPACE, 'get', 'pods', '-l', 'app.kubernetes.io/name=network-smoke', '-o', 'json']))['items']
    inspect_pods(pods)
    service_ip = command(kubectl + ['-n', NAMESPACE, 'get', 'service', 'network-smoke', '-o', 'jsonpath={.spec.clusterIP}'])
    if ipaddress.ip_address(service_ip) not in ipaddress.ip_network('192.168.20.0/24'):
        raise ValueError('测试 Service IP 不在规划 Service CIDR 内。')
    targets = [pod['status']['podIP'] + '=' + pod['spec']['nodeName'] for pod in pods]
    # exec 流由 subprocess 总时限约束；不让普通 API 请求的 20 秒超时截断完整诊断输出。
    kubectl_exec = [args.kubectl, '--kubeconfig', args.kubeconfig, '--request-timeout=0']
    for pod in sorted(pods, key=lambda item: item['spec']['nodeName']):
        source = pod['spec']['nodeName']
        print('== 源节点 ' + source, flush=True)
        output = command(kubectl_exec + ['-n', NAMESPACE, 'exec', pod['metadata']['name'], '-c', 'probe', '--',
                                   '/bin/sh', '-ec', PROBE + (SHORT_PROBE if args.short_name else ''), 'probe', service_ip, *targets], timeout=240)
        print(output, flush=True)
        print(source + ': PASS', flush=True)
    print(f'NETWORK ACCEPTANCE PASS: 10 sources, 100 Pod HTTP paths (90 cross-node), {50 if args.short_name else 40} DNS checks, {30 if args.short_name else 20} Service HTTP requests.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.TimeoutExpired) as error:
        raise SystemExit('NETWORK ACCEPTANCE FAIL: ' + str(error))
