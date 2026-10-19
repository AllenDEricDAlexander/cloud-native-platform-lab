import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import yaml
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('dataplane_tests',Path(__file__).with_name('check.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class Isolation(unittest.TestCase):
    def state(self):
        return SimpleNamespace(topic='dataplane',context={'cluster_uid':'primary','isolation':{
            'name':'owned','network':'owned-net','nodes':{},'docker_context':'desktop-linux','docker_id':'engine',
            'kubeconfig':'/private/test','cluster_uid':'isolated','pod_cidr':'10.246.0.0/16','subnet':'172.30.90.0/24'}},run='run')

    def test_primary_uid_is_rejected_even_on_loopback(self):
        c=m.iso.Cluster(self.state())
        with patch.object(c,'check_engine'),patch.object(m.r,'call',side_effect=['https://127.0.0.1:6443',json.dumps({'metadata':{'uid':'primary'}})]),self.assertRaises(ValueError):
            c.guard()

    def test_non_loopback_target_rejected(self):
        c=m.iso.Cluster(self.state())
        with patch.object(c,'check_engine'),patch.object(m.r,'call',return_value='https://api.k8s.internal.egon.top:6443'),self.assertRaises(ValueError):
            c.guard()

    def test_cilium_profiles_are_explicit_and_mesh_keeps_bpf_masquerade_off(self):
        c=m.iso.Cluster(self.state())
        baseline=c.cilium_values('baseline',mesh=True)
        self.assertFalse(baseline['kubeProxyReplacement'])
        self.assertFalse(baseline['bpf']['masquerade'])
        self.assertFalse(baseline['cni']['exclusive'])
        native=c.cilium_values('native')
        self.assertTrue(native['autoDirectNodeRoutes']);self.assertEqual(native['routingMode'],'native')
        self.assertEqual(native['operator']['image']['override'],c.lock['images']['operator']['runtime_image'])

    def test_foreign_resource_not_deleted(self):
        c=m.iso.Cluster(self.state())
        obj={'apiVersion':'v1','kind':'Service','metadata':{'uid':'u','name':'l2','namespace':'lab-dataplane','labels':{}}}
        with patch.object(c,'guard'),patch.object(c,'get',return_value=obj),self.assertRaises(ValueError):
            c.delete('Service','l2','lab-dataplane')

    def test_namespace_and_sa_are_applied_before_dependent_pod_dryrun(self):
        with tempfile.TemporaryDirectory() as d:
            state=self.state();state.attempt=Path(d)
            state.command=lambda argv:{'argv':[str(v) for v in argv]}
            c=m.iso.Cluster(state)
            objects=[{'apiVersion':'v1','kind':kind,'metadata':{'name':name,**({'namespace':'lab'} if kind!='Namespace' else {})}}
                for kind,name in [('Namespace','lab'),('ServiceAccount','app'),('Pod','app')]]
            file=Path(d)/'objects.yaml';file.write_text(yaml.safe_dump_all(objects))
            with patch.object(c,'guard'):commands=c.apply([file])
            self.assertEqual(len(commands),6)
            self.assertIn('--dry-run=server',commands[0]['argv'])
            self.assertNotIn('--dry-run=server',commands[1]['argv'])
            self.assertIn('--dry-run=server',commands[2]['argv'])
            self.assertIn('ServiceAccount',commands[3]['argv'][-1])


if __name__=='__main__':unittest.main()
