import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import runtime as r
import batch


class Batch(unittest.TestCase):
    def test_validation_calls_all_five_in_order(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();folder=root/'records/batch-02.06-10-unit'
            with patch.object(r,'PHASE',root),patch.object(r,'ROOT',root),patch.object(batch.sys,'argv',['batch','validate',str(folder)]),patch.object(batch.subprocess,'run',return_value=SimpleNamespace(returncode=0)) as run:
                self.assertEqual(batch.main(),0)
            calls=[Path(v.args[0][1]).stem for v in run.call_args_list]
            self.assertEqual(calls,['policies','scheduling','resource-governance','dataplane','mesh'])
            self.assertTrue(json.loads((folder/'result.json').read_text())['completed'])

    def test_unexpected_failure_stops_remaining_stages(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();folder=root/'records/batch-02.06-10-unit'
            with patch.object(r,'PHASE',root),patch.object(r,'ROOT',root),patch.object(batch.sys,'argv',['batch','validate',str(folder)]),patch.object(batch.subprocess,'run',side_effect=[SimpleNamespace(returncode=0),SimpleNamespace(returncode=7)]) as run:
                self.assertEqual(batch.main(),7)
            self.assertEqual(run.call_count,2)
            self.assertEqual(json.loads((folder/'result.json').read_text())['failed_stage'],'02.07')


if __name__=='__main__':unittest.main()
