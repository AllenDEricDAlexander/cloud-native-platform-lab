import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import yaml

spec=importlib.util.spec_from_file_location('dataplane_vm_test',Path(__file__).with_name('vm.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


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

    def test_non_migration_values_cannot_drift(self):
        before={'kubeProxyReplacement':'false','hubble':{'enabled':True},'bpf':{'preallocateMaps':True}}
        after={'kubeProxyReplacement':True,'hubble':{'enabled':True},'bpf':{'preallocateMaps':True,'masquerade':True}}
        self.assertEqual(m.untouched(before),m.untouched(after))
        after['hubble']['enabled']=False
        self.assertNotEqual(m.untouched(before),m.untouched(after))

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


if __name__=='__main__':unittest.main()
