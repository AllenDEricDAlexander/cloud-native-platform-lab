import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('resources_test',Path(__file__).with_name('check.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class Resources(unittest.TestCase):
    def test_requests_include_restartable_init_and_overhead(self):
        pod={'spec':{'containers':[{'resources':{'requests':{'cpu':'200m'}}}],
            'initContainers':[{'restartPolicy':'Always','resources':{'requests':{'cpu':'100m'}}},
                              {'resources':{'requests':{'cpu':'600m'}}}],
            'overhead':{'cpu':'50m'}}}
        self.assertAlmostEqual(m.cpu_request(pod),.75)

    def test_pod_level_requests_are_not_silently_ignored(self):
        with self.assertRaises(ValueError):
            m.cpu_request({'spec':{'resources':{'requests':{'cpu':'2'}},'containers':[]}})

    def test_foreign_cordon_cannot_be_undone(self):
        state=type('State',(),{})();state.context={'maintenance_node':{'uid':'u','unschedulable':None}};state.run='mine'
        node={'metadata':{'uid':'u','labels':{},'resourceVersion':'1'},'spec':{'unschedulable':True}}
        with patch.object(m.r,'get',return_value=node),self.assertRaisesRegex(ValueError,'其他操作'):
            m.maintenance(state,False)

    def test_no_global_node_pressure_pass(self):
        self.assertEqual(m.BLOCKED['whole_vm_pressure']['status'],'BLOCKED')


if __name__=='__main__':unittest.main()
