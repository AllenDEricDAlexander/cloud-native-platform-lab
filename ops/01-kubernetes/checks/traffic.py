#!/usr/bin/env python3
"""有界只读 HTTP/流量/时间线观测；不创建、修改或删除 Kubernetes 资源。"""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import http.client
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import time
import urllib.request

import yaml

spec=importlib.util.spec_from_file_location('reader',Path(__file__).with_name('lab-check.py'))
reader_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader_module)
Reader,require,save=reader_module.Reader,reader_module.require,reader_module.save
WORKERS={'worker01.k8s.internal.egon.top':'192.168.9.109','worker02.k8s.internal.egon.top':'192.168.9.110'}
CP={'cp01':'192.168.9.101','cp02':'192.168.9.102','cp03':'192.168.9.103'}


@contextmanager
def tunnel(pod,port=8080):
    require(pod['spec']['nodeName'] in WORKERS,'只对本实验 worker 上的 Pod 做流量观测')
    require(ipaddress.ip_address(pod['status']['podIP']) in ipaddress.ip_network('10.244.0.0/16'),'Pod IP 不属于实验网')
    with socket.socket() as s:s.bind(('127.0.0.1',0));local=s.getsockname()[1]
    argv=['ssh','-N','-T','-S','none','-i',str(Path.home()/'.ssh/cnpl_lab_ed25519'),'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=5','-o','ExitOnForwardFailure=yes','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=2','-L',f'127.0.0.1:{local}:{pod["status"]["podIP"]}:{port}','root@'+WORKERS[pod['spec']['nodeName']]]
    with tempfile.TemporaryFile(mode='w+') as errors:
        process=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=errors)
        try:
            end=time.monotonic()+10
            while time.monotonic()<end:
                require(process.poll() is None,'只读 SSH 转发启动失败')
                try:
                    with socket.create_connection(('127.0.0.1',local),timeout=.2):break
                except OSError:time.sleep(.1)
            else:raise ValueError('SSH 转发没有监听')
            yield local
        finally:
            process.terminate()
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)


def get(port,path,timeout=3,connection=None):
    # 检查程序只允许 GET 数据/健康接口，不提供 POST 或控制入口。
    require(path.split('?')[0] in ['/','/work','/identity','/metrics','/local','/ready','/live','/startup','/status'],'拒绝检查器控制接口')
    c=connection or http.client.HTTPConnection('127.0.0.1',port,timeout=timeout)
    try:
        c.request('GET',path);response=c.getresponse();raw=response.read();headers=dict(response.getheaders())
        try:body=json.loads(raw)
        except ValueError:body=raw.decode(errors='replace')
        return {'code':response.status,'body':body,'headers':headers}
    finally:
        if connection is None:c.close()


def samples(a,r):
    pod=r.get('pod',a.pod);require(pod['metadata']['labels'].get('cnpl.io/replay-run')==r.context['run'],'目标 Pod 不属于本批')
    rows=[];consecutive=0;deadline=time.monotonic()+45
    with tunnel(pod,a.port) as port:
        while time.monotonic()<deadline:
            row={'at':time.time()}
            try:
                row.update(get(port,a.path));row['ok']=row['code']==a.status and (not a.version or row['body'].get('version')==a.version)
            except (OSError,ValueError,http.client.HTTPException) as e:row.update(ok=False,error=str(e))
            rows.append(row);consecutive=consecutive+1 if row['ok'] else 0
            if consecutive>=a.count:break
            time.sleep(.2)
    result={'rows':rows,'stable':rows[-a.count:],'ok':consecutive>=a.count}
    save(a.output,result);require(result['ok'],'没有取得连续预期响应；详见结果文件')
    return {'ok':True,'requests':len(rows),'last':rows[-1]}


def inspect(a,r):
    pod=r.get('pod',a.pod);require(pod['metadata']['labels'].get('cnpl.io/replay-run')==r.context['run'],'目标 Pod 不属于本批')
    with tunnel(pod,a.port) as port:response=get(port,a.path)
    require(response['code']==a.status,'HTTP 状态不符：'+str(response['code']))
    save(a.output,response['body']);return response['body']


def observe(a,r):
    pod=r.get('pod',a.pod);require(pod['metadata']['labels'].get('cnpl.io/replay-run')==r.context['run'],'目标 Pod 不属于本批');rows=[];graphs=[];sticky=[];connection=None;original=None
    deadline=time.monotonic()+a.seconds
    with tunnel(pod,a.port) as port, Path(a.timeline).open('w') as stream:
        try:
            if a.sticky:
                for _ in range(80):
                    c=http.client.HTTPConnection('127.0.0.1',port,timeout=3)
                    result=get(port,'/identity',connection=c)
                    if result['body'].get('pod')==a.sticky:
                        connection=c;original={'uid':result['body']['uid'],'connection_id':result['headers'].get('X-Connection-ID'),'client_port':c.sock.getsockname()[1]};break
                    c.close()
                require(connection is not None and original['connection_id'],'未建立指定副本的持久连接')
            save(a.ready,{'ready':True,'at':time.time(),'sticky':original})
            last_graph=0;last_sticky=0
            while time.monotonic()<deadline and not Path(a.stop).exists():
                now=time.time();row={'at':now,'stage':'before'}
                if a.phase_marker and Path(a.phase_marker).exists():row['stage']='after' if now-Path(a.phase_marker).stat().st_mtime>=3 else 'converging'
                try:row.update(get(port,a.path,timeout=2));row['ok']=row['code']==a.status
                except (OSError,ValueError,http.client.HTTPException) as e:row.update(ok=False,error=str(e))
                rows.append(row);stream.write(json.dumps({'http':row})+'\n');stream.flush()
                if connection and now-last_sticky>=1:
                    result={'at':now,'stage':row['stage']}
                    try:
                        result.update(get(port,'/identity',connection=connection));result['client_port']=connection.sock.getsockname()[1]
                        result['same_connection']=(result['body'].get('uid')==original['uid'] and result['headers'].get('X-Connection-ID')==original['connection_id'] and result['client_port']==original['client_port'])
                    except (OSError,ValueError,http.client.HTTPException) as e:result.update(same_connection=False,error=str(e))
                    sticky.append(result);last_sticky=now
                if a.deployment and now-last_graph>=1:
                    try:value=reader_module.graph(r,a.deployment,2);value['at']=now
                    except (OSError,ValueError,KeyError) as e:value={'at':now,'error':str(e)}
                    graphs.append(value);stream.write(json.dumps({'graph':value})+'\n');stream.flush();last_graph=now
                time.sleep(.2)
        finally:
            if connection:connection.close()
            result={'rows':rows,'requests':len(rows),'errors':sum(not x['ok'] for x in rows),'sticky':sticky,'original_connection':original,'graphs':graphs,'stopped_by_ansible':Path(a.stop).exists()}
            save(a.output,result)
    return {'requests':len(rows),'errors':result['errors'],'stopped_by_ansible':result['stopped_by_ansible']}


def long_requests(a,r):
    value=json.loads(Path(a.targets).read_text());pods=value['items'] if isinstance(value,dict) else value
    responses={};errors={}
    with ExitStack() as stack,ThreadPoolExecutor(max_workers=len(pods)) as pool:
        ports={}
        for p in pods:
            require(p['metadata']['labels'].get('cnpl.io/replay-run')==r.context['run'],'长请求目标不属于本批')
            ports[p['metadata']['uid']]=stack.enter_context(tunnel(p))
        futures={uid:pool.submit(get,port,'/work?seconds='+str(a.seconds)+'&id='+uid,a.seconds+10) for uid,port in ports.items()}
        end=time.monotonic()+8
        while time.monotonic()<end:
            if all(get(port,'/metrics')['body']['active']>=1 for port in ports.values()):break
            time.sleep(.1)
        else:raise ValueError('长请求没有全部进入应用')
        save(a.ready,{'ready':True,'uids':list(ports),'at':time.time()})
        for uid,future in futures.items():
            try:
                result=future.result(timeout=a.seconds+12);require(result['code']==200,'长请求 HTTP 失败');responses[uid]=result['body']
            except (OSError,ValueError,http.client.HTTPException) as e:errors[uid]=str(e)
    result={'responses':responses,'errors':errors,'targets':pods};save(a.output,result)
    return {'completed':len(responses),'errors':len(errors)}


@contextmanager
def tls():
    cfg=yaml.safe_load((Path.home()/'.cnpl-secrets/access/lab-primary/mac.conf').read_text())
    ca=next(x['cluster']['certificate-authority-data'] for x in cfg['clusters'] if x['name']=='lab-primary')
    user=next(x['user'] for x in cfg['users'] if x['name']=='cnpl-mac-reader')
    with tempfile.TemporaryDirectory(prefix='cnpl-readonly-tls-') as temp:
        folder=Path(temp)
        for name,data in [('ca',ca),('cert',user['client-certificate-data']),('key',user['client-key-data'])]:
            p=folder/name;p.write_bytes(base64.b64decode(data));p.chmod(0o600)
        ctx=ssl.create_default_context(cafile=str(folder/'ca'));ctx.load_cert_chain(str(folder/'cert'),str(folder/'key'));yield ctx


def port_states(ip):
    rows={}
    for port in [22,6443]:
        start=time.monotonic()
        try:
            with socket.create_connection((ip,port),timeout=.6):rows[str(port)]={'tcp_open':True}
        except OSError as error:rows[str(port)]={'tcp_open':False,'error':str(error)}
        rows[str(port)]['seconds']=round(time.monotonic()-start,3)
    return rows


def unavailable(ip):
    return all(not row['tcp_open'] for row in port_states(ip).values())


def ha(a,r):
    pod=r.get('pod',a.pod);require(pod['metadata']['labels'].get('cnpl.io/replay-run')==r.context['run'],'目标 Pod 不属于本批');rows=[];api_rows=[];seen_down=False
    def api_probe(host,ctx):
        try:
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=ctx))
            with opener.open('https://'+host+':6443/readyz',timeout=1.5) as response:return response.status==200
        except Exception:return False
    failure=None;stop_reason='not-started';end=time.monotonic()+a.seconds
    try:
        with tunnel(pod) as port,tls() as ctx,ThreadPoolExecutor(max_workers=5) as pool,Path(a.timeline).open('w') as stream:
            save(a.ready,{'ready':True,'target':a.target,'at':time.time(),'expires_at':time.time()+a.seconds});end=time.monotonic()+a.seconds
            while True:
                if time.monotonic()>=end:stop_reason='deadline';break
                if Path(a.stop).exists():stop_reason='ansible';break
                now=time.time();hosts={'vip':'api.k8s.internal.egon.top',**CP};future={n:pool.submit(api_probe,h,ctx) for n,h in hosts.items()}
                row={'at':now}
                try:row.update(get(port,'/work?id=ha',timeout=2));row['ok']=row['code']==200
                except (OSError,ValueError,http.client.HTTPException) as e:row.update(ok=False,error=str(e))
                ports=port_states(CP[a.target]);down=all(not x['tcp_open'] for x in ports.values());seen_down|=down;apis={n:f.result(timeout=3) for n,f in future.items()}
                rows.append(row);api_rows.append({'at':now,'target_down':down,'ports':ports,'api':apis});stream.write(json.dumps({'http':row,'api':api_rows[-1]})+'\n');stream.flush();time.sleep(.2)
    except (OSError,ValueError,KeyError,subprocess.SubprocessError,http.client.HTTPException) as error:
        failure=str(error);stop_reason='error';raise
    finally:
        result={'rows':rows,'api_rows':api_rows,'target':a.target,'observed_target_down':seen_down,'app_errors':sum(not x['ok'] for x in rows),'api_failures':{n:sum(not row['api'][n] for row in api_rows) for n in ['vip',*CP]},'stopped_by_ansible':stop_reason=='ansible','observer_error':failure,'expired':stop_reason=='deadline','stop_reason':stop_reason}
        save(a.output,result)
    return {k:v for k,v in result.items() if k not in ['rows','api_rows']}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['inspect','samples','observe','long','ha','unavailable'])
    p.add_argument('--context',type=Path,required=True);p.add_argument('--pod');p.add_argument('--path',default='/work');p.add_argument('--port',type=int,default=8080)
    p.add_argument('--version');p.add_argument('--status',type=int,default=200);p.add_argument('--count',type=int,default=6);p.add_argument('--seconds',type=int,default=240)
    p.add_argument('--output');p.add_argument('--ready');p.add_argument('--stop');p.add_argument('--timeline');p.add_argument('--sticky');p.add_argument('--phase-marker');p.add_argument('--deployment');p.add_argument('--targets');p.add_argument('--target',choices=list(CP))
    a=p.parse_args();ctx=json.loads(a.context.read_text());r=Reader(ctx)
    try:
        if a.action=='unavailable':
            ports=port_states(CP[a.target]);down=all(not row['tcp_open'] for row in ports.values())
            result={'ok':down,'unavailable':down,'target':a.target,'ip':CP[a.target],'ports':ports}
            if a.output:save(a.output,result)
            print(json.dumps(result,ensure_ascii=False));return 0 if down else 1
        else:result={'inspect':inspect,'samples':samples,'observe':observe,'long':long_requests,'ha':ha}[a.action](a,r)
        print(json.dumps(result,ensure_ascii=False))
    except (OSError,ValueError,KeyError,subprocess.SubprocessError,http.client.HTTPException) as e:
        print(json.dumps({'ok':False,'error':str(e)},ensure_ascii=False));raise SystemExit(1)


if __name__=='__main__':raise SystemExit(main())
