"""HTTP 头名大小写与持久连接回归，不运行服务。"""
import importlib.util
from pathlib import Path
import unittest

BASE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('traffic_headers',BASE/'checks/traffic.py')
traffic=importlib.util.module_from_spec(spec);spec.loader.exec_module(traffic)


class TrafficHeaderTests(unittest.TestCase):
    def test_go_canonical_header_and_other_casings_keep_original_evidence(self):
        for spelling in ['X-Connection-Id','X-Connection-ID','x-connection-id','X-CONNECTION-ID']:
            with self.subTest(spelling=spelling):
                response={'headers':{spelling:'77'}}
                self.assertEqual(traffic.header(response,'X-Connection-ID'),'77')
                self.assertEqual(response['headers'],{spelling:'77'})
        self.assertIsNone(traffic.header({'headers':{}},'X-Connection-ID'))


if __name__=='__main__':unittest.main()
