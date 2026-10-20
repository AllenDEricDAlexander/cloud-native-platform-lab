import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('schedule_test', Path(__file__).with_name('check.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Scheduling(unittest.TestCase):
    def test_noexecute_requires_infinite_matching_toleration(self):
        self.assertTrue(m.tolerates([{'operator':'Exists'}], 'test','run','NoExecute'))
        self.assertFalse(m.tolerates([{'operator':'Exists','tolerationSeconds':0}], 'test','run','NoExecute'))
        self.assertFalse(m.tolerates([{'operator':'Exists','effect':'NoSchedule'}], 'test','run','NoExecute'))
        self.assertFalse(m.tolerates([{'key':'other','operator':'Exists'}], 'test','run','NoExecute'))
        self.assertTrue(m.tolerates([{'key':'test','value':'run','effect':'NoExecute'}], 'test','run','NoExecute'))

    def test_patch_preserves_other_taints_and_checks_uid(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = m.r.Session(m.TOPIC,m.STAGE,m.r.PHASE/'records/02.07-unit',m.r.PHASE/'records/02.07-unit/attempts/test',m.NAMESPACES)
            # 构造器不创建集群资源；文件放测试目录，避免使用真实批次。
            s.attempt = Path(tmp)
            s.context = {'run':'unit','node_original':{m.STORAGE:{'uid':'original','labels':{},'taints':[{'key':'storage','effect':'NoSchedule'}]}}}
            node={'metadata':{'name':m.STORAGE,'uid':'original','resourceVersion':'1','labels':{}},'spec':{'taints':[{'key':'storage','effect':'NoSchedule'},{'key':m.TAINT,'value':'unit','effect':'NoSchedule'}]}}
            with patch.object(m.r,'get',return_value=node):
                cmds=m.node_patch(s,m.STORAGE,clear_taint=True)
            data=json.loads(Path(cmds[0]['argv'][cmds[0]['argv'].index('--patch-file')+1]).read_text())
            self.assertEqual(data[0],{'op':'test','path':'/metadata/uid','value':'original'})
            self.assertEqual(data[-1]['value'],[{'key':'storage','effect':'NoSchedule'}])
            node['metadata']['uid']='replacement'
            with patch.object(m.r,'get',return_value=node),self.assertRaises(ValueError):
                m.node_patch(s,m.STORAGE,clear_taint=True)

    def test_foreign_test_taint_cannot_be_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=type('State',(),{})();s.context={'node_original':{m.STORAGE:{'uid':'u','labels':{}}}};s.run='mine';s.attempt=Path(tmp)
            node={'metadata':{'uid':'u','labels':{}},'spec':{'taints':[{'key':m.TAINT,'value':'foreign','effect':'NoExecute'}]}}
            with patch.object(m.r,'get',return_value=node),self.assertRaisesRegex(ValueError,'其他操作'):
                m.node_patch(s,m.STORAGE,clear_taint=True)

    def test_quantity(self):
        self.assertEqual(m.r.quantity('1500m'),1.5)
        self.assertEqual(m.r.quantity('2Gi'),2*1024**3)
        with self.assertRaises(ValueError):m.r.quantity('all')


if __name__ == '__main__':
    unittest.main()
