#!/usr/bin/env python3
"""仅由 pressure.py 在 worker02 调用：临时 soft 阈值及独立 systemd 回退；不消耗节点全部内存。"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


CONFIG = Path('/var/lib/kubelet/config.yaml')
ROOT = Path('/root/cnpl-pod-pressure')


def run(argv):
    return subprocess.check_output(argv, text=True, stderr=subprocess.STDOUT, timeout=40).strip()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def replace(data, original_stat):
    fd, name = tempfile.mkstemp(prefix='.cnpl-kubelet-', dir=CONFIG.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        os.chmod(temporary, original_stat.st_mode & 0o777)
        os.chown(temporary, original_stat.st_uid, original_stat.st_gid)
        os.replace(temporary, CONFIG)
        run(['restorecon', str(CONFIG)])
    finally:
        temporary.unlink(missing_ok=True)


def restore(directory):
    owner = json.loads((directory / 'owner.json').read_text())
    original = (directory / 'original').read_bytes()
    if sha(original) != owner['original_sha256']:
        raise ValueError('原配置副本校验失败')
    current = CONFIG.read_bytes()
    if sha(current) not in [owner['original_sha256'], owner['temporary_sha256']]:
        raise ValueError('配置被第三方修改，拒绝覆盖；保留原配置和 owner.json 供恢复')
    if current != original:
        replace(original, CONFIG.stat())
        run(['systemctl', 'restart', 'kubelet'])
    else:
        # 上次可能已恢复字节，却在重启服务时中断；重复 restore 也必须能恢复 kubelet。
        try:
            active = run(['systemctl', 'is-active', 'kubelet']) == 'active'
        except subprocess.CalledProcessError:
            active = False
        if not active:
            run(['systemctl', 'restart', 'kubelet'])
    if run(['systemctl', 'is-active', 'kubelet']) != 'active':
        raise ValueError('恢复后 kubelet 不 active')
    print(json.dumps({'restored': True, 'sha256': sha(CONFIG.read_bytes())}))


def arm(args, directory):
    if run(['getenforce']) != 'Enforcing' or run(['systemctl', 'is-active', 'firewalld']) != 'active':
        raise ValueError('安全基线异常')
    if any(ROOT.glob('*/owner.json')):
        # 已恢复的历史材料允许保留；拒绝仍有临时配置的其他运行。
        for path in ROOT.glob('*/owner.json'):
            if sha(CONFIG.read_bytes()) == json.loads(path.read_text())['temporary_sha256']:
                raise ValueError('另一个压力实验未恢复')
    data = json.load(sys.stdin)
    original = CONFIG.read_bytes()
    if sha(original) != data['original_sha256']:
        raise ValueError('kubelet 配置在前检后变化')
    temporary = (json.dumps(data['config'], indent=2) + '\n').encode()
    directory.mkdir(mode=0o700)
    (directory / 'original').write_bytes(original)
    (directory / 'owner.json').write_text(json.dumps({'original_sha256': sha(original), 'temporary_sha256': sha(temporary)}))
    # 先建立独立于 Mac/SSH 的回退，再修改配置；回退不依赖此 Python 进程继续存活。
    unit = 'cnpl-pod-pressure-' + args.run.lower()
    run(['systemd-run', '--unit=' + unit, '--on-active=150s', '--timer-property=AccuracySec=1s',
         '/usr/bin/python3', str(Path(__file__).resolve()), 'restore', '--run', args.run])
    try:
        replace(temporary, CONFIG.stat())
        run(['systemctl', 'restart', 'kubelet'])
    except BaseException:
        restore(directory)
        raise
    print(json.dumps({'armed': True, 'rollback_seconds': 150, 'unit': unit, 'original_sha256': sha(original)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['arm', 'restore'])
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}', args.run):
        raise ValueError('run 格式错误')
    if os.geteuid() != 0 or run(['hostnamectl', '--static']) != 'worker02.k8s.internal.egon.top':
        raise ValueError('只允许 root 在 worker02 执行')
    os.umask(0o077)
    ROOT.mkdir(mode=0o700, exist_ok=True)
    with (ROOT / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        directory = ROOT / args.run
        if args.mode == 'restore':
            restore(directory)
        else:
            arm(args, directory)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit('NODE PRESSURE FAIL: ' + str(error))
