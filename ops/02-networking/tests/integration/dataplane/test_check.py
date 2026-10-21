import importlib.util
import json
from pathlib import Path
import tempfile
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import yaml

spec=importlib.util.spec_from_file_location('dataplane_vm_test',Path(__file__).with_name('vm.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
PEER_IPS=dict(zip(m.r.WORKERS,['10.244.8.40','10.244.9.1']))


class VM(unittest.TestCase):
    def test_helm_four_list_includes_all_statuses_without_removed_flag(self):
        result=[{'name':'cilium','chart':'cilium-1.20.2','revision':'4','status':'deployed'}]
        with patch.object(m.r,'call',return_value=json.dumps(result)) as call:
            self.assertEqual(m.release()['revision'],'4')
        self.assertNotIn('--all',call.call_args.args[0])
    def test_profiles_keep_original_cluster_pool_and_vm_addresses(self):
        for name in ['ebpf','native','l2','bgp']:
            v=m.profile(name)
            self.assertNotIn('ipam',v)
            self.assertEqual(v['k8sServiceHost'],'192.168.9.100')
            self.assertEqual(v['devices'],['ens33'])
            self.assertEqual(v['routingMode'],'native' if name=='native' else 'tunnel')
            self.assertEqual(v['operator'],{'rollOutPods':True})
            self.assertEqual(v['defaultLBServiceIPAM'],'none')

    def test_non_migration_values_cannot_drift(self):
        before={'kubeProxyReplacement':'false','hubble':{'enabled':True},'bpf':{'preallocateMaps':True}}
        after={'kubeProxyReplacement':True,'hubble':{'enabled':True},'bpf':{'preallocateMaps':True,'masquerade':True}}
        self.assertEqual(m.untouched(before),m.untouched(after))
        after['hubble']['enabled']=False
        self.assertNotEqual(m.untouched(before),m.untouched(after))

    def test_operator_rollout_setting_does_not_allow_other_operator_changes(self):
        before={'operator':{'replicas':2,'rollOutPods':False}}
        after={'operator':{'replicas':2,'rollOutPods':True}}
        self.assertEqual(m.untouched(before),m.untouched(after))
        after['operator']['replicas']=1
        self.assertNotEqual(m.untouched(before),m.untouched(after))

    def test_recovery_keeps_the_previous_batches_hash_contract(self):
        values={'operator':{'replicas':2,'rollOutPods':False},'routingMode':'tunnel'}
        self.assertEqual(m.untouched(values,operator_rollout=False),{'operator':{'replicas':2,'rollOutPods':False}})
        self.assertEqual(m.untouched(values),{'operator':{'replicas':2}})
        values['defaultLBServiceIPAM']='lbipam'
        self.assertEqual(m.untouched(values,operator_rollout=False,isolated_lbipam=False),{'operator':{'replicas':2,'rollOutPods':False},'defaultLBServiceIPAM':'lbipam'})

    def test_operator_requires_new_ready_pods_with_current_manifest_checksum(self):
        checksum='a'*64
        config={'enable-l2-announcements':'true','enable-bgp-control-plane':'false','default-lb-service-ipam':'none'}
        deployment={'kind':'Deployment','metadata':{'name':'cilium-operator'},'spec':{'replicas':2,'template':{'metadata':{'annotations':{m.CHECKSUM:checksum}}}}}
        cm={'kind':'ConfigMap','metadata':{'name':'cilium-config'},'data':config}
        def pod(uid,signature=checksum):
            return {'metadata':{'uid':uid,'name':uid,'annotations':{m.CHECKSUM:signature}},'status':{'conditions':[{'type':'Ready','status':'True'}]}}
        with tempfile.TemporaryDirectory() as folder:
            s=SimpleNamespace(attempt=Path(folder),context={'operator_rollouts':{'l2-enable':{'before_uids':['old1','old2']}}})
            for pods,ok in [([pod('old1'),pod('new2')],False),([pod('new1','b'*64),pod('new2')],False),([pod('new1'),pod('new2')],True)]:
                with self.subTest(pods=pods),patch.object(m.r,'call',return_value=yaml.safe_dump_all([deployment,cm])),patch.object(m.r,'get',return_value=deployment),patch.object(m,'operator_pods',return_value=pods):
                    if ok:self.assertEqual(m.operator_rollout(s,'l2-enable',config)['expected_checksum'],checksum)
                    else:
                        with self.assertRaisesRegex(ValueError,'新 Pod'):m.operator_rollout(s,'l2-enable',config)
            self.assertTrue((s.attempt/'l2-enable-operator-last.json').is_file())

    def test_bgp_switch_releases_l2_service_before_upgrading_operator(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            s=SimpleNamespace(attempt=root,path=root/'context.json',context={'chart':{'local_source':'chart.tgz'},'owned_revisions':[7]},
                command=lambda a:{'argv':a},document=lambda *a:a,delete=lambda o:[{'argv':['delete-l2']}])
            with patch.object(m,'guard'),patch.object(m,'release',return_value={'revision':'7'}),patch.object(m,'operator_pods',return_value=[{'metadata':{'uid':'old'}}]):
                commands=m.plan(s,'bgp-enable')
            self.assertEqual(commands[0]['argv'],['delete-l2'])
            self.assertIn('upgrade',commands[1]['argv'])
            self.assertEqual(s.context['operator_rollouts']['bgp-enable']['before_uids'],['old'])
            self.assertTrue(yaml.safe_load((root/'bgp-enable.values.yaml').read_text())['operator']['rollOutPods'])

    def test_vip_failure_preserves_actual_service_and_pool(self):
        with tempfile.TemporaryDirectory() as folder:
            s=SimpleNamespace(attempt=Path(folder),context={'dp_name':'pool'},owned=lambda o:None)
            service={'status':{'loadBalancer':{},'conditions':[{'reason':'no_pool'}]}}
            pool={'spec':{},'status':{'conditions':[{'type':'cilium.io/PoolConflict','status':'False'}]}}
            with patch.object(m.r,'get',side_effect=[service,pool]),self.assertRaisesRegex(ValueError,'实际=\\[\\]'):
                m.lb_address(s,'l2')
            self.assertEqual(json.loads((s.attempt/'l2-lb-last.json').read_text())['service'],service)

    def test_arp_probe_distinguishes_replies_absence_and_tool_errors(self):
        s=SimpleNamespace(context={'vm_facts':{m.ARP_OBSERVER:{'arping':'/usr/sbin/arping'}}})
        for rc,stdout,responses in [(0,'Unicast reply from 192.168.9.211 [00:50:56:AA:BB:CC] 0.1ms\nReceived 2 response(s)',2),(1,'Received 0 response(s)',0),(2,'bind failed',None)]:
            with self.subTest(rc=rc),patch.object(m.r,'call',return_value=json.dumps({'rc':rc,'stdout':stdout,'stderr':''})):
                if responses is None:
                    with self.assertRaisesRegex(ValueError,'ARP 探测异常'):m.arp_probe(s,'192.168.9.211')
                else:
                    row=m.arp_probe(s,'192.168.9.211');self.assertEqual(row['responses'],responses)
                    self.assertEqual(row['macs'],['00:50:56:aa:bb:cc'] if responses else [])

    def test_l2_rejects_a_mac_that_does_not_match_the_lease(self):
        with tempfile.TemporaryDirectory() as folder:
            s=SimpleNamespace(attempt=Path(folder),context={'vm_facts':{m.r.WORKERS[0]:{'links':[{'address':'00:50:56:aa:bb:cc'}]}}})
            lease={'spec':{'holderIdentity':m.r.WORKERS[0]}}
            with patch.object(m,'lb_address',return_value='192.168.9.211'),patch.object(m.r,'get',return_value=lease),patch.object(m,'arp_probe',return_value={'rc':0,'responses':2,'macs':['00:50:56:dd:ee:ff']}),self.assertRaisesRegex(ValueError,'实际 ARP'):
                m.l2(s)

    def test_l2_withdraw_needs_three_actual_no_reply_probes(self):
        with tempfile.TemporaryDirectory() as folder:
            s=SimpleNamespace(attempt=Path(folder),context={'dp_name':'pool'})
            m.r.save(s.attempt/'l2.json',{'vip':'192.168.9.211'})
            with patch.object(m.r,'optional',return_value=None),patch.object(m,'arp_probe',return_value={'rc':1,'responses':0}) as probe:
                self.assertTrue(m.observe(s,'l2-withdraw')['passed']);self.assertEqual(probe.call_count,3)
            with patch.object(m.r,'optional',return_value=None),patch.object(m,'arp_probe',side_effect=[{'rc':1,'responses':0},{'rc':0,'responses':1},{'rc':1,'responses':0}]),self.assertRaisesRegex(ValueError,'仍收到 ARP'):
                m.observe(s,'l2-withdraw')

    def test_l2_handoff_and_resume_cannot_pass_by_changing_the_vip(self):
        with tempfile.TemporaryDirectory() as folder:
            s=SimpleNamespace(attempt=Path(folder),context={})
            m.r.save(s.attempt/'l2.json',{'vip':'192.168.9.211'})
            for name in ['l2-handoff','l2-resume']:
                with self.subTest(name=name),patch.object(m,'l2',return_value={'vip':'192.168.9.212'}),self.assertRaisesRegex(ValueError,'VIP 不应改变'):
                    m.observe(s,name)

    def test_bgp_withdraw_does_not_pass_because_the_sessions_went_down(self):
        with tempfile.TemporaryDirectory() as folder:
            s=SimpleNamespace(attempt=Path(folder),context={'dp_name':'pool','bgp_peer_addresses':PEER_IPS},pod=lambda *a:{'metadata':{'name':'frr'}})
            peers={PEER_IPS[n]:{'state':'Established','remoteAs':65010,'localAs':65009} for n in m.r.WORKERS}
            for state,ok in [('Established',True),('Active',False)]:
                peers[PEER_IPS[m.r.WORKERS[0]]]['state']=state
                with self.subTest(state=state),patch.object(m,'bgp_nodes',return_value={}),patch.object(m.r,'call',side_effect=[json.dumps({'routes':{}}),json.dumps({'ipv4Unicast':{'routerId':'10.255.255.9','as':65009,'peers':peers}})]),patch.object(m.r,'optional',return_value=None):
                    if ok:self.assertTrue(m.observe(s,'bgp-withdraw')['passed'])
                    else:
                        with self.assertRaisesRegex(ValueError,'撤回期间断开'):m.observe(s,'bgp-withdraw')

    def test_bgp_requires_exact_prefixes_and_valid_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            cidrs=dict(zip(m.r.WORKERS,['10.244.8.0/24','10.244.9.0/24']))
            s=SimpleNamespace(attempt=Path(folder),context={'pod_cidrs':cidrs,'bgp_peer_addresses':PEER_IPS},pod=lambda *a:{'metadata':{'name':'frr'}})
            peers={PEER_IPS[n]:{'state':'Established','remoteAs':65010,'localAs':65009} for n in m.r.WORKERS}
            wanted={ip:[{'valid':True}] for ip in list(cidrs.values())+['192.168.9.211/32']}
            for routes,ok in [(wanted,True),({**wanted,'192.168.9.212/32':[{'valid':True}]},False),({ip:[{'valid':False}] for ip in wanted},False)]:
                with self.subTest(routes=routes),patch.object(m,'bgp_nodes',return_value={}),patch.object(m.r,'call',side_effect=[json.dumps({'routes':routes}),json.dumps({'ipv4Unicast':{'routerId':'10.255.255.9','as':65009,'peers':peers}})]),patch.object(m,'lb_address',return_value='192.168.9.211'):
                    if ok:self.assertTrue(m.observe(s,'bgp')['passed'])
                    else:
                        with self.assertRaises(ValueError):m.observe(s,'bgp')

    def test_diagnostics_timeout_preserves_the_original_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();records=root/'records/02.09-unit'
            with patch.object(m.r,'PHASE',root):s=m.Session('dataplane','02.09',records,records/'attempts/unit',m.NAMESPACES)
            s.context={'run':'test'}
            with patch.object(m.r.Session,'wait',side_effect=ValueError('ORIGINAL_FAILURE')),patch.object(m.r,'call',side_effect=subprocess.TimeoutExpired('kubectl',3)),self.assertRaisesRegex(ValueError,'ORIGINAL_FAILURE.*现场诊断'):
                s.wait('l2',lambda:None)
            value=json.loads((s.attempt/'l2-diagnostics.json').read_text())
            self.assertEqual(value['error'],'ORIGINAL_FAILURE');self.assertTrue(value['collection_errors'])

    def test_bgp_requires_symmetric_overlay_source_in_the_generated_node_config(self):
        with tempfile.TemporaryDirectory() as folder:
            s=SimpleNamespace(attempt=Path(folder),context={'bgp_peer_addresses':PEER_IPS})
            def config(node,address):
                return {'metadata':{'name':node},'spec':{'bgpInstances':[{'name':'comparison','peers':[{'name':'frr','localAddress':address}]}]}}
            nodes=[config(node,PEER_IPS[node]) for node in m.r.WORKERS]
            with patch.object(m.r,'get',return_value={'items':nodes}):self.assertEqual(set(m.bgp_nodes(s)),set(m.r.WORKERS))
            nodes[0]['spec']['bgpInstances'][0]['peers'][0]['localAddress']='192.168.9.109'
            with patch.object(m.r,'get',return_value={'items':nodes}),self.assertRaisesRegex(ValueError,'Cilium 内部地址一致'):m.bgp_nodes(s)
            saved=json.loads((s.attempt/'bgp-node-configs-last.json').read_text())
            self.assertEqual(saved[m.r.WORKERS[0]]['spec']['bgpInstances'][0]['peers'][0]['localAddress'],'192.168.9.109')

    def test_bgp_peer_selection_uses_real_cilium_addresses_and_rejects_wrong_cidrs(self):
        cidrs=dict(zip(m.r.WORKERS,['10.244.8.0/24','10.244.9.0/24']))
        nodes=[{'metadata':{'name':node},'spec':{'addresses':[{'type':'InternalIP','ip':m.r.pol.base.NODES[node]},{'type':'CiliumInternalIP','ip':PEER_IPS[node]}]}} for node in m.r.WORKERS]
        self.assertEqual(m.bgp_addresses(nodes,cidrs),PEER_IPS)
        nodes[1]['spec']['addresses'][1]['ip']='192.168.9.110'
        with self.assertRaisesRegex(ValueError,'本机 PodCIDR 内 CiliumInternalIP'):m.bgp_addresses(nodes,cidrs)
        nodes[1]['spec']['addresses']=nodes[1]['spec']['addresses'][:1]
        with self.assertRaises(ValueError):m.bgp_addresses(nodes,cidrs)

    def test_node_override_apply_and_cleanup_are_run_and_uid_scoped(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();records=root/'records/02.09-unit'
            with patch.object(m.r,'PHASE',root):s=m.Session('dataplane','02.09',records,records/'attempts/unit',m.NAMESPACES)
            s.context={'run':'test','dp_name':'cnpl-dp-test'}
            obj={'apiVersion':'cilium.io/v2','kind':'CiliumBGPNodeConfigOverride','metadata':{'name':m.r.WORKERS[0],'labels':{m.r.LABEL:'test'}},'spec':{}}
            (s.attempt/'override.yaml').write_text(yaml.safe_dump(obj))
            with patch.object(m.r,'optional',return_value=None):commands=s.apply('override.yaml')
            self.assertEqual(commands[1]['key'],'CiliumBGPNodeConfigOverride//'+m.r.WORKERS[0])
            current=json.loads(json.dumps(obj));current['metadata']['uid']='original'
            s.record([{'phase_command':commands[1],'rc':0,'stdout':json.dumps(current)}])
            with patch.object(m.r,'optional',return_value=current):deletes=s.delete(obj)
            self.assertIn('/apis/cilium.io/v2/ciliumbgpnodeconfigoverrides/'+m.r.WORKERS[0],deletes[0]['argv'])
            body=json.loads(Path(deletes[0]['argv'][-1]).read_text());self.assertEqual(body['preconditions']['uid'],'original')
            current['metadata']['uid']='foreign'
            with patch.object(m.r,'optional',return_value=current),self.assertRaisesRegex(ValueError,'UID 改变'):s.delete(obj)
            obj['metadata']['name']='cp01.k8s.internal.egon.top'
            with self.assertRaisesRegex(ValueError,'覆盖对象越界'):s.owned(obj)

    def test_recovery_tracks_both_node_overrides_but_no_other_nodes(self):
        state=SimpleNamespace(context={'dp_name':'cnpl-dp-test'},document=lambda kind,name:{'kind':kind,'metadata':{'name':name}})
        objects=m.announcement_objects(state)
        self.assertEqual({o['metadata']['name'] for o in objects if o['kind']=='CiliumBGPNodeConfigOverride'},set(m.r.WORKERS))
        self.assertEqual(len(objects),7)

    def test_primary_vip_must_remain_owned_by_the_original_service(self):
        s=SimpleNamespace(context={'primary_service':{'uid':'main','ips':['192.168.9.201']}})
        for ips,ok in [(['192.168.9.201'],True),([],False),(['192.168.9.211'],False)]:
            current={'metadata':{'uid':'main'},'status':{'loadBalancer':{'ingress':[{'ip':ip} for ip in ips]}}}
            with self.subTest(ips=ips),patch.object(m.r,'get',return_value=current):
                if ok:m.primary_stable(s)
                else:
                    with self.assertRaisesRegex(ValueError,'主入口 Service UID/VIP'):m.primary_stable(s)

    def test_frr_readiness_requires_its_real_asn_router_id_and_vm_neighbors(self):
        with tempfile.TemporaryDirectory() as folder:
            s=SimpleNamespace(attempt=Path(folder),context={'bgp_peer_addresses':PEER_IPS},pod=lambda *a:{'metadata':{'name':'frr'}})
            peers={PEER_IPS[node]:{'remoteAs':65010,'localAs':65009,'state':'Idle'} for node in m.r.WORKERS}
            value={'ipv4Unicast':{'routerId':'10.255.255.9','as':65009,'peers':peers}}
            with patch.object(m.r,'call',return_value=json.dumps(value)):self.assertEqual(m.frr_state(s),value)
            with patch.object(m.r,'call',return_value='{}'),self.assertRaisesRegex(ValueError,'Router ID/ASN'):m.frr_state(s)

    def test_protection_allows_managed_pod_restart_but_preserves_other_pods(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();folder=root/'records/02.09-unit'
            with patch.object(m.r,'PHASE',root):s=m.Session('dataplane','02.09',folder,folder/'attempts/unit',m.NAMESPACES)
            s.context={'run':'test'}
            controller={'kind':'DaemonSet','metadata':{'name':'cilium','namespace':'kube-system','uid':'agent-ds'}}
            agent={'kind':'Pod','metadata':{'name':'agent','namespace':'kube-system','ownerReferences':[{'uid':'agent-ds'}]}}
            other={'kind':'Pod','metadata':{'name':'dns','namespace':'kube-system','ownerReferences':[{'uid':'other'}]}}
            before={'DaemonSet/kube-system/cilium':{'uid':'agent-ds','spec_sha256':'old'},'Pod/kube-system/agent':{'uid':'old-pod'},'Pod/kube-system/dns':{'uid':'keep'}}
            def get(kind,name=None,namespace=None):
                if kind=='configmap':return {'metadata':{'uid':'cm'}}
                if kind=='replicasets':return {'items':[]}
                if kind=='pods' and namespace=='kube-system':return {'items':[agent,other]}
                return {'items':[]}
            with patch.object(m,'controllers',return_value=[controller]),patch.object(m.r.pol,'protected',return_value=before),patch.object(m.r,'get',side_effect=get):
                value=s.protected()
            self.assertNotIn('Pod/kube-system/agent',value)
            self.assertEqual(value['Pod/kube-system/dns'],{'uid':'keep'})
            self.assertEqual(value['DaemonSet/kube-system/cilium'],{'uid':'agent-ds'})

    def test_missing_crd_before_first_apply_does_not_block_recovery(self):
        state=SimpleNamespace(context={'dp_name':'cnpl-dp-test'},document=lambda k,n:{'kind':k,'metadata':{'name':n}},receipt=lambda o:Path('/does-not-exist'))
        with patch.object(m.r,'optional') as optional:
            self.assertTrue(m.observe(state,'recover-announcements')['passed'])
        optional.assert_not_called()

    def test_proxy_selector_patch_keeps_uid_and_other_fields(self):
        with tempfile.TemporaryDirectory() as d:
            state=SimpleNamespace(attempt=Path(d),command=lambda argv: {'argv':[str(v) for v in argv]})
            original={'template':{'spec':{'nodeSelector':{'kubernetes.io/os':'linux'}}},'selector':{'matchLabels':{'app':'proxy'}}}
            wanted=json.loads(json.dumps(original));wanted['template']['spec']['nodeSelector'][m.PROXY_OFF]='run'
            obj={'metadata':{'uid':'uid'},'spec':original}
            with patch.object(m.r,'get',return_value=obj):commands=m.patch_spec(state,'DaemonSet','kube-proxy',{'uid':'uid'},wanted)
            operations=json.loads((Path(d)/'patch-DaemonSet-kube-proxy.json').read_text())
            self.assertEqual(operations[0],{'op':'test','path':'/metadata/uid','value':'uid'})
            self.assertEqual(operations[1]['value'],original)
            self.assertEqual(operations[2]['value']['selector'],original['selector'])
            self.assertNotIn('delete',commands[0]['argv'])
            with patch.object(m.r,'get',return_value={'metadata':{'uid':'foreign'},'spec':original}),self.assertRaises(ValueError):
                m.patch_spec(state,'DaemonSet','kube-proxy',{'uid':'uid'},wanted)

    def test_large_crd_uses_ssa_in_preview_and_actual_apply(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();folder=root/'records/02.09-unit'
            with patch.object(m.r,'PHASE',root):
                s=m.Session('dataplane','02.09',folder,folder/'attempts/unit',m.NAMESPACES)
            s.context={'run':'r','crd_inputs':{'large.example.test':{}},'dp_name':'cnpl-dp-r'}
            obj={'apiVersion':'apiextensions.k8s.io/v1','kind':'CustomResourceDefinition','metadata':{'name':'large.example.test','labels':{m.r.LABEL:'r'}},'spec':{'description':'x'*300000}}
            (s.attempt/'crd.yaml').write_text(yaml.safe_dump(obj))
            with patch.object(m.r,'optional',return_value=None):commands=s.apply('crd.yaml')
            self.assertGreater((s.attempt/'input-CustomResourceDefinition--large.example.test.json').stat().st_size,262144)
            self.assertEqual(len(commands),2)
            self.assertTrue(all('--server-side' in c['argv'] and '--field-manager=cnpl-gateway-crds' in c['argv'] for c in commands))
            self.assertTrue(all('--force-conflicts' not in c['argv'] for c in commands))

    def test_native_route_cleanup_scope_is_exact(self):
        state=SimpleNamespace(context={'pod_cidrs':{'worker01.k8s.internal.egon.top':'10.244.8.0/24'}})
        own={'dst':'10.244.8.0/24','gateway':'192.168.9.109','dev':'ens33'}
        self.assertEqual(m.direct_routes(state,[own,{'dst':'default','gateway':'192.168.9.1','dev':'ens33'},{**own,'gateway':'192.168.9.1'}]),[own])

    def test_templates_use_vm_targets_and_no_local_runtime(self):
        base=m.r.PHASE/'networking/dataplane'
        self.assertEqual(len(m.steps(None)),22)
        for file in base.glob('*.yaml.j2'):
            text=file.read_text()
            self.assertNotIn('cnpl.io/kind-role',text)
            self.assertNotIn('172.30.90.',text)
        self.assertEqual(m.BLOCKED['external_bgp_forwarding']['status'],'BLOCKED')
        self.assertEqual(m.RESTORE_STEPS[-1]['name'],'recover-firewall')

    def test_l2_and_bgp_selectors_and_frr_neighbor_configuration_agree(self):
        base=m.r.PHASE/'networking/dataplane';env=m.r.Environment(undefined=m.r.StrictUndefined)
        values={'name':'cnpl-dp-test','run':'test','frr_ip':'10.244.8.20','frr_image':'registry/frr@sha256:'+'a'*64,
            'workers':m.r.WORKERS,'node_ips':m.r.pol.base.NODES,'peer_ips':PEER_IPS,'pod_cidrs':dict(zip(m.r.WORKERS,['10.244.8.0/24','10.244.9.0/24']))}
        docs={name:list(yaml.safe_load_all(env.from_string((base/(name+'.yaml.j2')).read_text()).render(**values))) for name in ['l2','bgp','frr']}
        l2_service=docs['l2'][-1];bgp_service=docs['bgp'][-1]
        l2_selector=docs['l2'][1]['spec']['serviceSelector']['matchLabels']
        bgp_selector=docs['bgp'][1]['spec']['advertisements'][1]['selector']['matchLabels']
        self.assertTrue(all(l2_service['metadata']['labels'][k]==v for k,v in l2_selector.items()))
        self.assertFalse(all(bgp_service['metadata']['labels'].get(k)==v for k,v in l2_selector.items()))
        self.assertTrue(all(bgp_service['metadata']['labels'][k]==v for k,v in bgp_selector.items()))
        self.assertFalse(all(l2_service['metadata']['labels'].get(k)==v for k,v in bgp_selector.items()))
        frr=docs['frr'][0]['data'];cluster=next(o for o in docs['bgp'] if o['kind']=='CiliumBGPClusterConfig')['spec']['bgpInstances'][0]
        overrides=[o for o in docs['bgp'] if o['kind']=='CiliumBGPNodeConfigOverride']
        self.assertEqual({o['metadata']['name'] for o in overrides},set(m.r.WORKERS))
        for obj in overrides:self.assertEqual(obj['spec']['bgpInstances'][0]['peers'][0]['localAddress'],PEER_IPS[obj['metadata']['name']])
        self.assertIn('router bgp '+str(cluster['peers'][0]['peerASN']),frr['frr.conf'])
        self.assertIn('ip nht resolve-via-default',frr['frr.conf'])
        for node in m.r.WORKERS:
            ip=PEER_IPS[node]
            self.assertIn('neighbor '+ip+' remote-as '+str(cluster['localASN']),frr['frr.conf'])
            self.assertIn('neighbor '+ip+' ebgp-multihop '+str(docs['bgp'][0]['spec']['ebgpMultihop']),frr['frr.conf'])
            self.assertIn('neighbor '+ip+' passive',frr['frr.conf'])
        self.assertIn('service integrated-vtysh-config',frr['vtysh.conf'])
        self.assertIn('bgpd_options=" -A 127.0.0.1 -n"',frr['daemons'])
        self.assertEqual(docs['frr'][1]['spec']['volumes'][0]['configMap']['defaultMode'],0o644)


if __name__=='__main__':unittest.main()
