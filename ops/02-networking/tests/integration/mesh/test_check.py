import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('mesh_test',Path(__file__).with_name('check.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class Mesh(unittest.TestCase):
    def test_agent_ids_accept_pinned_cli_json_shapes(self):
        identifier='spiffe://internal.egon.top/spire/agent/k8s_psat/cnpl-kind/node'
        self.assertEqual(m.agent_ids({'agents':[{'id':{'trust_domain':'internal.egon.top','path':'/spire/agent/k8s_psat/cnpl-kind/node'}}]}),[identifier])
        self.assertEqual(m.agent_ids({'agents':[{'spiffe_id':identifier}]}),[identifier])

    def test_wrong_trust_domain_or_attestor_is_not_accepted(self):
        for identifier in ['spiffe://other/spire/agent/k8s_psat/x','spiffe://internal.egon.top/spire/agent/join_token/x']:
            with self.assertRaises(ValueError):m.agent_ids({'agents':[{'id':identifier}]})

    def test_null_agent_list_is_pending_not_type_error(self):
        self.assertEqual(m.agent_ids({'agents':None}),[])
        with self.assertRaises(ValueError):m.agent_ids(None)

    def test_three_mesh_modes_are_in_distinct_namespaces(self):
        self.assertEqual(len({m.SIDECAR,m.AMBIENT,m.PLAIN,m.SPIRE}),4)


if __name__=='__main__':unittest.main()
