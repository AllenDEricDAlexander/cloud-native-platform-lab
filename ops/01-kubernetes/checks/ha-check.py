#!/usr/bin/env python3
"""HA 证据的纯文件核验；不访问网络、不创建或变更集群资源。"""
import argparse
from datetime import datetime
import json
from pathlib import Path

CP={'cp01':'192.168.9.101','cp02':'192.168.9.102','cp03':'192.168.9.103'}
WORKERS={'worker01.k8s.internal.egon.top','worker02.k8s.internal.egon.top'}


def require(value,reason):
    if not value:raise ValueError(reason)


def timestamp(value):
    parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    require(parsed.tzinfo is not None,'时间必须包含时区')
    return parsed.timestamp()


def healthy(rows,names):
    expected={'https://'+CP[name]+':2379' for name in names}
    require(len(rows)==len(names) and {r['endpoint'] for r in rows}==expected and all(r.get('health') is True for r in rows),'etcd endpoint 数量、身份或健康不符')


def verify(document):
    context=document['context'];binding=document['binding'];target=binding['target']
    require(target in CP and binding['target_ip']==CP[target],'故障目标/IP 不符')
    require(binding['run']==context['run'] and binding['cluster_uid']==context['cluster_uid'],'绑定身份不属于本批/集群')
    survivors=set(CP)-{target}
    require(set(binding['survivors'])==survivors and binding['initial_holder']==target+'.k8s.internal.egon.top','初始持有者或存活节点错误')
    require(document['new_holder'] in {n+'.k8s.internal.egon.top' for n in survivors},'未证明 VIP 接管')
    require(binding['target_uid'] and document['recovered_uid']==binding['target_uid'],'恢复后不是原 Node UID')
    started=timestamp(document['fault_started_at']);confirmed=timestamp(document['fault_confirmed_at']);recovered=timestamp(document['recovered_at'])
    require(started<confirmed<recovered,'故障、调度证明和恢复时序错误')
    require(len(document['port_checks'])==2,'缺少调度前/后的端口检查')
    for rows in document['port_checks']:
        require(len(rows)==2 and {int(r['port']) for r in rows}=={22,6443} and all(r['state']=='stopped' and not r.get('failed',False) for r in rows),'没有证明 SSH/API 两个端口均停止')
    healthy(document['quorum'],survivors);healthy(document['restored_etcd'],set(CP))
    pod=document['proof_pod'];meta=pod['metadata']
    require(meta['labels'].get('cnpl.io/replay-run')==context['run'] and pod['status']['phase']=='Succeeded' and pod['spec']['nodeName'] in WORKERS,'证明 Pod 归属、完成状态或调度落点不符')
    created=timestamp(meta['creationTimestamp'])
    require(started-1<=created<=confirmed,'证明 Pod 并非在本次故障窗口新创建')
    observer=document['observer'];rows=observer['rows'];apis=observer['api_rows']
    require(observer['target']==target and observer['stopped_by_ansible'] is True,'观测目标错误或观测自行超时退出')
    require(not observer.get('observer_error') and not observer.get('expired',False),'观测程序异常或过期')
    require(len(rows)>=5 and observer['app_errors']==0 and all(r.get('ok') and r.get('code')==200 for r in rows),'存在真实应用请求失败')
    require(len(binding['server_uids'])==2 and all(r['body'].get('uid') in binding['server_uids'] and r['body'].get('version')=='v1' for r in rows),'响应不是本次 HA Service 的实际副本')
    require(min(r['at'] for r in rows)<started and max(r['at'] for r in rows)>recovered,'业务观测未完整覆盖故障前、故障中和恢复后')
    during=[r for r in apis if started<=r['at']<=confirmed]
    failed_target=[r for r in during if r['api'].get(target) is False]
    require(failed_target,'没有取得故障窗口内目标 API 不可用的独立采样')
    require(any(r['api'].get('vip') and all(r['api'].get(n) for n in survivors) for r in failed_target),'没有取得目标 API 故障时 VIP 与两个存活 API 可用的样本')
    require(any(started<=r['at']<=confirmed for r in rows),'故障窗口没有应用响应样本')
    return {'passed':True,'run':context['run'],'target':target,'new_holder':document['new_holder'],
            'remote_ports_confirmed':True,'target_api_down_samples':len(failed_target),
            'business_requests':len(rows),'business_errors':0,'proof_pod_uid':meta['uid'],
            'fault_started_at':document['fault_started_at'],'fault_confirmed_at':document['fault_confirmed_at'],'recovered_at':document['recovered_at']}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    try:
        result=verify(json.loads(a.input.read_text()));a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
    except (OSError,ValueError,KeyError,TypeError) as error:
        raise SystemExit('HA CHECK FAIL: '+str(error))


if __name__=='__main__':main()
