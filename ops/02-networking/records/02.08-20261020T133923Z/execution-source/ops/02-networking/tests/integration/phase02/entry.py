#!/usr/bin/env python3
import fcntl
import os
from pathlib import Path
import sys
import runtime as r

TOPICS = {'scheduling':'02.07','resource-governance':'02.08','dataplane':'02.09','mesh':'02.10'}


def main():
    topic, mode, folder, invocation = sys.argv[1:]
    r.require(topic in TOPICS and mode in ['all','validate','cleanup','recover'], '入口参数错误')
    records = Path(folder)
    r.require(not records.is_symlink() and records.resolve().parent == r.PHASE / 'records'
              and records.name.startswith(TOPICS[topic] + '-'), '入口路径越界')
    if mode != 'validate':
        fd = os.open(r.PHASE / 'records/components/.gateway-batch.lock', os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            sys.exit('其他网络批次正在运行，请顺序执行各专题。')
        os.set_inheritable(fd, True)
    if mode == 'all':
        r.require(not any((records / p).exists() for p in ['passed.json','state/closed.json','state/protected.json']), '批次已使用：先原批 recover，再用新目录 all')
    else:
        r.require(mode == 'validate' or (records / 'context.json').exists(), '恢复缺少原上下文')
    exe = Path.home() / '.venvs/cnpl-ansible/bin/ansible-playbook'
    os.execv(str(exe), [str(exe), str(r.PHASE / ('ansible/playbooks/' + topic + '.yml')), '-e', '@' + invocation])


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as error:
        sys.exit(str(error))
