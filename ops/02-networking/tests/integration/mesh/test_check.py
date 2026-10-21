import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import yaml

spec=importlib.util.spec_from_file_location('mesh_test',Path(__file__).with_name('check.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class Mesh(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory(prefix='cnpl-mesh-source-')
        cls.session=object.__new__(m.Session)
        cls.session.topic='mesh'
        cls.session.context={'run':'20261021T000000Z-1234abcd'}
        cls.session.attempt=Path(cls.folder.name)
        cls.images=m.locks()['mesh_vm']['images']
        cls.session.render({'workers':m.r.WORKERS,'socket_path':'/run/cnpl/mesh-20261021T000000Z-1234abcd/spire',
            'excluded_namespaces':['kube-system','istio-system'],
            'image':cls.images['resource']['runtime_image'],'identity_image':cls.images['identity']['runtime_image'],
            'spire_server':cls.images['spire-server']['runtime_image'],'spire_agent':cls.images['spire-agent']['runtime_image'],
            'proxy_image':cls.images['proxyv2']['runtime_image'],'pilot_image':cls.images['pilot']['runtime_image'],
            'cni_image':cls.images['install-cni']['runtime_image'],'ztunnel_image':cls.images['ztunnel']['runtime_image'],
            'spire_server_hcl':(m.r.PHASE/'networking/mesh/spire-server.conf').read_text(),
            'spire_agent_hcl':(m.r.PHASE/'networking/mesh/spire-agent.conf').read_text()})
        cls.generated=m.generate(cls.session)

    @classmethod
    def tearDownClass(cls):cls.folder.cleanup()

    def docs(self,name):return m.documents(self.session.attempt/(name+'.yaml'))

    def test_agent_ids_accept_pinned_cli_json_shapes(self):
        identity='spiffe://internal.egon.top/spire/agent/k8s_psat/cnpl-vm/node'
        self.assertEqual(m.agent_ids({'agents':[{'id':{'trust_domain':'internal.egon.top','path':'/spire/agent/k8s_psat/cnpl-vm/node'}}]}),[identity])
        self.assertEqual(m.agent_ids({'agents':[{'spiffe_id':identity}]}),[identity])

    def test_wrong_trust_domain_attestor_cluster_and_duplicates_are_rejected(self):
        for identity in ['spiffe://other/spire/agent/k8s_psat/x','spiffe://internal.egon.top/spire/agent/join_token/x','spiffe://internal.egon.top/spire/agent/k8s_psat/cnpl-kind/node']:
            with self.assertRaises(ValueError):m.agent_ids({'agents':[{'id':identity}]})
        identity='spiffe://internal.egon.top/spire/agent/k8s_psat/cnpl-vm/node'
        with self.assertRaises(ValueError):m.agent_ids([{'id':identity},{'id':identity}])

    def test_null_agent_list_is_pending_not_type_error(self):
        self.assertEqual(m.agent_ids({'agents':None}),[])
        with self.assertRaises(ValueError):m.agent_ids(None)

    def test_experiment_namespaces_do_not_overlap(self):
        self.assertEqual(len(set(m.NAMESPACES)),6)
        self.assertEqual(len(self.docs('workloads')),24)

    def test_workloads_are_cross_vm_and_have_no_container_engine_selector(self):
        for obj in self.docs('workloads')+self.docs('spire-workloads')+self.docs('held'):
            if obj['kind']!='Pod':continue
            role=obj['metadata']['name']
            expected=m.r.WORKERS[0 if role=='server' else 1]
            self.assertEqual(obj['spec']['nodeSelector'],{'kubernetes.io/hostname':expected})
            expected_policy='IfNotPresent' if obj['metadata']['namespace'].startswith('lab-mesh-') else 'Never'
            self.assertTrue(all(c['imagePullPolicy']==expected_policy for c in obj['spec']['containers']))

    def test_mesh_enrollment_is_separate_and_opt_in(self):
        spaces={o['metadata']['name']:o['metadata']['labels'] for o in self.docs('workloads') if o['kind']=='Namespace'}
        self.assertEqual(spaces[m.SIDECAR]['istio.io/rev'],'cnpl0210')
        self.assertNotIn('istio.io/dataplane-mode',spaces[m.SIDECAR])
        self.assertEqual(spaces[m.AMBIENT]['istio.io/dataplane-mode'],'ambient')
        self.assertEqual(spaces[m.AMBIENT]['istio-injection'],'disabled')
        self.assertEqual(spaces[m.PLAIN]['istio-injection'],'disabled')

    def test_istiod_uses_verified_host_access_in_overlay(self):
        obj=next(o for o in self.generated if o['kind']=='Deployment' and o['metadata']['name']=='istiod-cnpl0210')
        pod=obj['spec']['template']['spec']
        self.assertTrue(pod['hostNetwork'])
        self.assertEqual(pod['dnsPolicy'],'ClusterFirstWithHostNet')
        self.assertEqual(pod['nodeSelector']['kubernetes.io/hostname'],m.r.WORKERS[0])
        self.assertEqual({p['containerPort'] for p in pod['containers'][0]['ports']},m.PILOT_PORTS)
        env={v['name']:v.get('value') for v in pod['containers'][0]['env']}
        self.assertEqual(env['PILOT_ENABLE_GATEWAY_API_GATEWAYCLASS_CONTROLLER'],'false')

    def test_cni_and_ztunnel_only_target_two_workers(self):
        for obj in self.generated:
            if obj['kind']!='DaemonSet':continue
            pod=obj['spec']['template']['spec']
            terms=pod['affinity']['nodeAffinity']['requiredDuringSchedulingIgnoredDuringExecution']['nodeSelectorTerms']
            self.assertEqual(terms[0]['matchExpressions'][0]['values'],m.r.WORKERS)
            self.assertNotIn('hostPID',pod)
        self.assertEqual(sum(o['kind']=='DaemonSet' for o in self.generated),2)

    def test_all_generated_images_are_locked_amd64(self):
        known={v['runtime_image'] for v in self.images.values()}
        for obj in self.generated:
            pod=obj.get('spec',{}).get('template',{}).get('spec',{})
            for container in pod.get('containers',[])+pod.get('initContainers',[]):
                self.assertIn(container['image'],known)
                self.assertEqual(container['imagePullPolicy'],'Never')
        self.assertTrue(all(v['architecture']=='amd64' for v in self.images.values()))

    def test_injection_cannot_capture_unrelated_namespaces(self):
        count=0
        for obj in self.generated:
            for webhook in obj.get('webhooks',[]):
                self.assertEqual(webhook['namespaceSelector']['matchLabels'][m.r.LABEL],self.session.run)
                count+=1
        self.assertGreater(count,0)
        cm=next(o for o in self.generated if o['kind']=='ConfigMap' and 'mesh' in o.get('data',{}))
        mesh=yaml.safe_load(cm['data']['mesh'])
        self.assertEqual(mesh['discoverySelectors'],[{'matchLabels':{m.r.LABEL:self.session.run}}])

    def test_offline_injection_does_not_add_network_init(self):
        pod=self.docs('injected-example')[0]['spec']['template']['spec']
        names={c['name'] for c in pod['containers']+pod.get('initContainers',[])}
        self.assertIn('istio-proxy',names)
        self.assertNotIn('istio-init',names)
        known={v['runtime_image'] for v in self.images.values()}
        for container in pod['containers']+pod.get('initContainers',[]):
            if container['name'].startswith('istio-'):
                self.assertIn(container['image'],known)

    def test_generated_istio_configs_are_narrowly_recognized(self):
        obj={'kind':'ConfigMap','metadata':{'name':'istio-ca-crl','namespace':m.AMBIENT,'labels':{'istio.io/config':'true'}},'data':{'ca-crl.pem':''}}
        self.assertTrue(m.generated_istio_config(obj))
        obj['data']['unexpected']='foreign'
        self.assertFalse(m.generated_istio_config(obj))
        obj['data']={'ca-crl.pem':''};obj['metadata']['labels']={}
        self.assertFalse(m.generated_istio_config(obj))
        leader={'kind':'ConfigMap','metadata':{'name':'istio-leader','namespace':m.SYSTEM}}
        self.assertTrue(m.generated_istio_config(leader))
        leader['data']={'foreign':'data'}
        self.assertFalse(m.generated_istio_config(leader))

    def test_host_dependency_selection_contains_only_two_rocky_rpms(self):
        values=m.host_packages()
        self.assertEqual({v['name'].split('-1.8')[0] for v in values},{'iptables-libs','iptables-nft'})

    def test_image_smoke_requires_actual_kubelet_pods_on_each_worker(self):
        pods=[o for o in self.docs('image-smoke') if o['kind']=='Pod']
        self.assertEqual({o['spec']['nodeSelector']['kubernetes.io/hostname'] for o in pods},set(m.r.WORKERS))
        self.assertEqual(len(pods),2)
        self.assertTrue(all(o['spec']['containers'][0]['imagePullPolicy']=='IfNotPresent' for o in pods))

    def test_waypoint_uses_locked_proxy_on_worker(self):
        cm=next(o for o in self.generated if o['kind']=='ConfigMap' and 'values' in o.get('data',{}))
        values=json.loads(cm['data']['values'])
        self.assertEqual(values['global']['proxy']['image'],self.images['proxyv2']['runtime_image'])
        config,gateway=self.docs('waypoint')
        deployment=yaml.safe_load(config['data']['deployment'])
        self.assertEqual(deployment['spec']['template']['spec']['nodeSelector']['kubernetes.io/hostname'],m.r.WORKERS[1])
        self.assertEqual(gateway['spec']['infrastructure']['parametersRef']['name'],config['metadata']['name'])
        self.assertEqual(gateway['spec']['infrastructure']['labels'][m.r.LABEL],self.session.run)

    def test_spire_agent_uses_verified_kubelet_and_scoped_socket(self):
        agent=self.docs('spire-agent')
        config=next(o for o in agent if o['kind']=='ConfigMap')['data']['agent.conf']
        self.assertIn('skip_kubelet_verification = false',config)
        self.assertNotIn('cnpl-kind',config)
        pod=next(o for o in agent if o['kind']=='DaemonSet')['spec']['template']['spec']
        self.assertTrue(pod['hostPID'])
        token=next(v for v in pod['volumes'] if v['name']=='psat')['projected']['sources'][0]['serviceAccountToken']
        self.assertEqual(token,{'path':'spire-agent','audience':'spire-server','expirationSeconds':600})
        socket=next(v for v in pod['volumes'] if v['name']=='socket')['hostPath']['path']
        self.assertEqual(socket,'/run/cnpl/mesh-20261021T000000Z-1234abcd/spire')
        role=next(o for o in agent if o['kind']=='ClusterRole')
        self.assertEqual(role['rules'][0]['resourceNames'],m.r.WORKERS)

    def test_cilium_profile_preserves_primary_data_plane(self):
        before={'kubeProxyReplacement':False,'routingMode':'tunnel','bpf':{'masquerade':False},'cni':{'exclusive':True,'customConf':False},'socketLB':{'enabled':False}}
        after=copy.deepcopy(before)
        for key,value in m.profile().items():after.setdefault(key,{}).update(value)
        self.assertEqual(m.untouched(before),m.untouched(after))
        after['bpf']['masquerade']=True
        self.assertNotEqual(m.untouched(before),m.untouched(after))
        self.assertNotIn('kubeProxyReplacement',m.profile())

    def test_foreign_global_objects_are_not_owned(self):
        s=object.__new__(m.Session);s.context={'run':'mine','global_objects':{}}
        obj={'kind':'ClusterRole','metadata':{'name':'other','labels':{m.r.LABEL:'mine'}}}
        with self.assertRaises(ValueError):s.owned(obj)
        s.context['global_objects']['ClusterRole//other']={}
        s.owned(obj)
        obj['metadata']['labels'][m.r.LABEL]='someone-else'
        with self.assertRaises(ValueError):s.owned(obj)

    def test_recovery_order_exits_apps_before_network_uninstall(self):
        names=[v['name'] for v in m.RESTORE_STEPS]
        self.assertLess(names.index('recover-applications'),names.index('recover-components'))
        self.assertLess(names.index('recover-components'),names.index('recover-cilium'))
        file=yaml.safe_load((m.r.PHASE/'networking/mesh/restore-cases.yml').read_text())
        self.assertEqual(m.RESTORE_STEPS,file)

    def test_large_crds_use_server_side_apply(self):
        s=object.__new__(m.Session);s.context={'run':'mine','global_objects':{'CustomResourceDefinition//test.istio.io':{}}};s.attempt=self.session.attempt;s.records=self.session.attempt
        s.k=m.r.K
        obj={'apiVersion':'apiextensions.k8s.io/v1','kind':'CustomResourceDefinition','metadata':{'name':'test.istio.io','labels':{m.r.LABEL:'mine'}}}
        path=s.attempt/'large-crd.yaml';path.write_text(yaml.safe_dump(obj))
        with patch.object(m,'guard'),patch.object(m.r,'optional',return_value=None): commands=s.apply(path.name)
        self.assertEqual(len(commands),2)
        self.assertTrue(all('--server-side' in v['argv'] for v in commands))

    def test_runtime_has_no_local_container_backend(self):
        source=Path(m.__file__).read_text()+Path(m.evidence.__file__).read_text()
        self.assertNotIn('import isolated',source)
        self.assertNotIn("['docker'",source)
        self.assertNotIn('iso.Cluster',source)

    def test_namespace_with_foreign_pod_is_never_deleted(self):
        s=object.__new__(m.Session);s.context={'run':'mine','global_objects':{}};s.attempt=self.session.attempt;s.records=self.session.attempt;s.k=m.r.K
        ns={'apiVersion':'v1','kind':'Namespace','metadata':{'name':m.PLAIN,'uid':'namespace-uid','labels':{m.r.LABEL:'mine'}}}
        receipt=s.receipt(ns);receipt.parent.mkdir(exist_ok=True);receipt.write_text(json.dumps({'uid':'namespace-uid','run':'mine'}))
        foreign={'kind':'Pod','metadata':{'name':'foreign','namespace':m.PLAIN,'uid':'other','labels':{}}}
        with patch.object(m.r,'optional',side_effect=lambda kind,*args:ns if kind=='Namespace' else None),patch.object(m.r,'get',side_effect=lambda kind,**kwargs:{'items':[foreign] if kind=='pods' else []}),patch.object(s,'delete') as delete:
            with self.assertRaisesRegex(ValueError,'外来对象'):m.delete_namespace(s,m.PLAIN)
        delete.assert_not_called()

    def test_firewall_cleanup_does_not_depend_on_helm_recovery(self):
        s=object.__new__(m.Session);s.k=m.r.K;s.context={'execution_backend':'vm-primary','run':'mine','cluster_uid':'cluster','node_uids':{n:n for n in m.r.WORKERS},'firewall_rules':{m.r.WORKERS[0]:['owned-rule']}}
        def get(kind,name):return {'metadata':{'uid':'cluster' if kind=='namespace' else name}}
        with patch.object(m,'guard',side_effect=AssertionError('Helm guard must not prevent firewall cleanup')),patch.object(m.r,'get',side_effect=get),patch.object(m.dp,'remote_facts',return_value={'rich_rules':['owned-rule']}):
            commands=m.plan(s,'recover-firewall')
        self.assertEqual(len(commands),1)
        self.assertIn('--remove-rich-rule=owned-rule',commands[0]['argv'][-1])

    def test_external_helm_revision_blocks_mutation(self):
        s=object.__new__(m.Session);s.context={'cluster_uid':'cluster','node_uids':{},'owned_revisions':[42]}
        with patch.object(m.r,'get',return_value={'metadata':{'uid':'cluster'}}),patch.object(m.r,'call',return_value='https://api.k8s.internal.egon.top:6443'),patch.object(m.dp,'release',return_value={'revision':'43'}):
            with self.assertRaisesRegex(ValueError,'revision'):m.guard(s)

    def test_recovery_before_any_helm_change_does_not_roll_back(self):
        s=object.__new__(m.Session);s.context={'execution_backend':'vm-primary','cluster_uid':'cluster'}
        with patch.object(m,'guard'),patch.object(m.dp,'helm',side_effect=AssertionError('No Helm mutation occurred')):
            self.assertEqual(m.plan(s,'recover-cilium'),[])

    def test_installed_hcl_matches_standalone_inputs(self):
        for name,key in [('spire-server','server.conf'),('spire-agent','agent.conf')]:
            config=next(o for o in self.docs(name) if o['kind']=='ConfigMap')
            self.assertEqual(config['data'][key],(m.r.PHASE/'networking/mesh'/(name+'.conf')).read_text())


if __name__=='__main__':unittest.main()
