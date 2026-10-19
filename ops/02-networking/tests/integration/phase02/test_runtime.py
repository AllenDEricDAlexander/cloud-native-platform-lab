import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import runtime as r


class Runtime(unittest.TestCase):
    def test_ansible_custom_loop_var_records_uid(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();records=root/'records/02.07-unit'
            with patch.object(r,'PHASE',root):
                s=r.Session('scheduling','02.07',records,records/'attempts/test',['lab-scheduling'])
                s.context={'run':'test'}
                obj={'kind':'Pod','metadata':{'name':'p','namespace':'lab-scheduling','uid':'original','labels':{r.LABEL:'test'}}}
                s.record([{'phase_command':{'key':s.key(obj)},'rc':0,'stdout':json.dumps(obj)}])
                self.assertEqual(json.loads(s.receipt(obj).read_text())['uid'],'original')

    def test_partial_previous_is_accepted_only_after_cleanup(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);folder=root/'records/02.06-20261020';folder.mkdir(parents=True)
            r.save(folder/'passed.json',{'cluster_uid':'u','run':'r','available_cases_passed':True,'phase_complete':False})
            with patch.object(r,'PHASE',root):
                with self.assertRaises(ValueError):r.previous('02.07','u',True)
                r.save(folder/'state/closed.json',{'cluster_uid':'u','run':'r','cleanup_passed':True})
                self.assertEqual(r.previous('02.07','u',True)['run'],'r')
                with self.assertRaises(ValueError):r.previous('02.07','another',True)


if __name__=='__main__':
    unittest.main()
