#!/usr/bin/env python3
"""在 always 清理和 PLAY RECAP 之后重述首个失败；只读日志，不连接集群。"""
import argparse
import json
from pathlib import Path
import re


ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')


def summarize(log, records, status, mode):
    lines = ANSI.sub('', log.read_text(errors='replace')).splitlines()
    failures, task, origin, cleanup_started, cleanup_finished, execution_started = [], '', '', False, False, False
    for number, line in enumerate(lines, 1):
        match = re.match(r'^TASK \[(.*)\] \*+\s*$', line)
        if match:
            task, origin = match.group(1), ''
            if task == '复核原资源、节点字段和主入口':
                cleanup_finished = False
        if line.startswith(('included:', 'ok:', 'changed:', 'fatal:', 'failed:')):
            cleanup_started |= task in ['成功或失败都恢复原状态并清理本批资源', '原批显式恢复', '根据原 UID 和字段归属生成恢复与清理计划']
            execution_started |= task == '顺序执行专题计划，避免全局状态并发'
        if line.startswith('Origin: '):
            origin = line.removeprefix('Origin: ')
        if task == '复核原资源、节点字段和主入口' and line.startswith('ok: [localhost]'):
            cleanup_finished = True
        failed = re.match(r'^(?:fatal|failed): \[[^\]]+\]: (?:FAILED|UNREACHABLE)! => (.*)$', line)
        if not failed:
            continue
        try:
            value = json.loads(failed.group(1))
        except json.JSONDecodeError:
            value = {'msg': failed.group(1)}
        argv = value.get('cmd') or []
        argv = argv if isinstance(argv, list) else []
        case, attempt = '', ''
        if '--case' in argv and argv.index('--case') + 1 < len(argv):
            case = argv[argv.index('--case') + 1]
        if '--attempt' in argv and argv.index('--attempt') + 1 < len(argv):
            attempt = argv[argv.index('--attempt') + 1]
        if not case:
            match = re.match(r'^(?:等待并验证 |为 )?([a-z][a-z0-9-]+)(?: 命令| 的真实结果| 核对)', task)
            case = match.group(1) if match else ''
        failures.append({'task': task, 'case': case, 'rc': value.get('rc'), 'line': number, 'origin': origin,
            'error': ANSI.sub('', str(value.get('stderr') or value.get('msg') or '命令失败')).strip(), 'attempt': attempt})
    closed, context = {}, {}
    for filename, target in [('state/closed.json', closed), ('context.json', context)]:
        file = records / filename
        if file.exists():
            try:
                target.update(json.loads(file.read_text()))
            except (OSError, ValueError, TypeError):
                pass  # 损坏的回执不能证明本次清理通过；原文仍留在 records。
    matching = not context or all(closed.get(k) == context.get(k) for k in ['run', 'cluster_uid'])
    cleanup = 'PASS' if cleanup_finished and matching and closed.get('cleanup_passed') else 'NOT_CONFIRMED' if cleanup_started else 'NOT_RUN'
    fallback = next((v for v in reversed(lines) if v.strip() and not re.match(r'^(?:TASK |PLAY |ok: |changed: |skipping: |included: |localhost\s*:)', v)), '入口提前退出或执行被中断')
    return {'mode': mode, 'exit_code': status, 'process_succeeded': status == 0, 'cleanup_status': cleanup,
        'execution_started': execution_started, 'cleanup_started': cleanup_started,
        'first_failure': failures[0] if failures else None, 'failures': failures,
        'entry_error': fallback if status and not failures else None, 'log': str(log), 'records': str(records)}


def report(value, output):
    failed, mode = bool(value['exit_code']), value['mode']
    print('\n执行失败汇总' if failed else '\n执行结果汇总')
    if failed:
        first = value['first_failure']
        print('退出码：' + str(value['exit_code']))
        if first:
            print('首个失败步骤：' + (first['case'] or first['task']))
            print('任务：' + first['task'])
            print('原因：' + first['error'])
            print('日志位置：' + value['log'] + ':' + str(first['line']))
            if first['origin']:
                print('任务来源：' + first['origin'])
            if len(value['failures']) > 1:
                print('后续还有 ' + str(len(value['failures']) - 1) + ' 个失败，详见汇总 JSON。')
            if first['attempt'] and first['case']:
                file = Path(first['attempt']) / (first['case'] + '-diagnostics.json')
                if file.is_file():
                    print('失败现场：' + str(file))
        else:
            print('入口错误：' + value['entry_error'])
    elif mode == 'validate':
        print('前检与服务端预览通过；正式实验尚未执行。')
    elif mode in ['cleanup', 'recover']:
        print('恢复与清理进程成功结束；回执见 state/closed.json。')
    else:
        print('进程成功结束；用例结果与 BLOCKED 项见 passed.json。')
    if mode != 'validate':
        print('本次回退与清理：' + value['cleanup_status'])
        if failed and value['cleanup_status'] != 'PASS':
            root = Path(__file__).resolve().parents[5]
            context = Path(value['records']) / 'context.json'
            if context.exists() and (value['execution_started'] or value['cleanup_started'] or mode in ['cleanup', 'recover']):
                topics = {'02.07': 'scheduling', '02.08': 'resource-governance', '02.09': 'dataplane', '02.10': 'mesh'}
                topic = topics.get(Path(value['records']).name.split('-')[0])
                if topic:
                    print('原批恢复入口：bash ' + str(root / 'ops/02-networking/scripts' / (topic + '.sh')) + ' recover ' + value['records'])
            elif not value['execution_started'] and not value['cleanup_started']:
                print('本次尚未进入实验执行；处理入口错误后使用全新目录重跑。')
        elif failed:
            print('原状态已恢复；修复后请使用全新 records 目录重跑。')
    print('汇总 JSON：' + str(output))
    print('完整日志：' + value['log'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--records', type=Path, required=True)
    parser.add_argument('--status', type=int, required=True)
    parser.add_argument('--mode', choices=['all', 'validate', 'recover', 'cleanup'], required=True)
    args = parser.parse_args()
    output = args.log.with_name(args.log.name.replace('ansible-', 'summary-', 1) + '.json')
    value = summarize(args.log, args.records, args.status, args.mode)
    output.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    report(value, output)


if __name__ == '__main__':
    main()
