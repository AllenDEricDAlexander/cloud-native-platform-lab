import json
import contextlib
import io
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import summary


def failure(case, error):
    return ('TASK [等待并验证 ' + case + ' 的真实结果] ********\nOrigin: /tasks/phase02-case.yml:25:3\n'
        + 'fatal: [localhost]: FAILED! => ' + json.dumps({'rc':1,'cmd':['python','check.py','observe','--case',case],'stderr':error}) + '\n')


CLEANED = 'TASK [成功或失败都恢复原状态并清理本批资源] ********\nincluded: cleanup\nTASK [复核原资源、节点字段和主入口] ********\nok: [localhost]\nPLAY RECAP ********\nlocalhost : failed=1\n'


class Summary(unittest.TestCase):
    def test_first_failure_survives_cleanup_failure_and_stale_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'state').mkdir()
            (root/'state/closed.json').write_text(json.dumps({'cleanup_passed':True,'run':'old'}))
            log=root/'ansible-all-log';log.write_text(failure('l2','L2 VIP 未就绪') + 'TASK [成功或失败都恢复原状态并清理本批资源] ********\nincluded: cleanup\n' + failure('recover-cilium','rollback failed'))
            value=summary.summarize(log,root,2,'all')
            self.assertEqual(value['first_failure']['case'],'l2')
            self.assertEqual(len(value['failures']),2)
            self.assertEqual(value['cleanup_status'],'NOT_CONFIRMED')

    def test_a_completed_cleanup_does_not_turn_experiment_failure_into_success(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'state').mkdir()
            (root/'state/closed.json').write_text(json.dumps({'cleanup_passed':True,'run':'same','cluster_uid':'u'}))
            (root/'context.json').write_text(json.dumps({'run':'same','cluster_uid':'u'}))
            log=root/'ansible-all-log';log.write_text('\x1b[31m' + failure('l2','L2 VIP 未就绪') + '\x1b[0m' + CLEANED)
            value=summary.summarize(log,root,2,'all')
            self.assertEqual(value['cleanup_status'],'PASS')
            self.assertFalse(value['process_succeeded'])
            self.assertEqual(value['first_failure']['origin'],'/tasks/phase02-case.yml:25:3')

    def test_previous_run_receipt_cannot_confirm_current_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'state').mkdir()
            (root/'state/closed.json').write_text(json.dumps({'cleanup_passed':True,'run':'old','cluster_uid':'u'}))
            (root/'context.json').write_text(json.dumps({'run':'new','cluster_uid':'u'}))
            log=root/'ansible-all-log';log.write_text(CLEANED)
            self.assertEqual(summary.summarize(log,root,2,'all')['cleanup_status'],'NOT_CONFIRMED')

    def test_entry_rejection_and_command_failure_are_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);log=root/'ansible-all-log'
            log.write_text('其他网络批次正在运行，请顺序执行各专题。\n')
            value=summary.summarize(log,root,1,'all')
            self.assertEqual(value['cleanup_status'],'NOT_RUN')
            self.assertIn('其他网络批次',value['entry_error'])
            (root/'context.json').write_text('{}')
            stream=io.StringIO()
            with contextlib.redirect_stdout(stream):summary.report(value,root/'summary.json')
            self.assertNotIn('原批恢复入口',stream.getvalue())
            log.write_text('TASK [l2-enable 命令] ********\nfatal: [localhost]: FAILED! => ' + json.dumps({'rc':2,'msg':'Helm failed'}) + '\n')
            self.assertEqual(summary.summarize(log,root,2,'all')['first_failure']['case'],'l2-enable')

    def test_validation_skips_do_not_claim_experiment_or_cleanup_started(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);log=root/'ansible-validate-log'
            log.write_text('TASK [顺序执行专题计划，避免全局状态并发] ********\nskipping: [localhost]\nTASK [成功或失败都恢复原状态并清理本批资源] ********\nskipping: [localhost]\n')
            value=summary.summarize(log,root,0,'validate')
            self.assertFalse(value['execution_started'])
            self.assertEqual(value['cleanup_status'],'NOT_RUN')

    def test_shell_exit_trap_prints_failure_after_recap_and_preserves_exit_code(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);scripts=root/'ops/02-networking/scripts';scripts.mkdir(parents=True)
            checks=root/'ops/02-networking/tests/integration/phase02';checks.mkdir(parents=True)
            source=Path(__file__).resolve().parents[3]
            shutil.copy(source/'scripts/phase02.sh',scripts/'phase02.sh')
            shutil.copy(Path(summary.__file__),checks/'summary.py')
            records=root/'ops/02-networking/records/02.09-test'
            # 只替换临时仓库内的入口，不调用 Ansible、kubectl、Helm 或真实集群。
            (checks/'entry.py').write_text('import sys,json\nfrom pathlib import Path\nr=Path(sys.argv[3]);(r/"state").mkdir()\n(r/"state/closed.json").write_text(json.dumps({"cleanup_passed":True}))\nprint('+repr(failure('l2','EXPECTED_FAILURE') + CLEANED)+')\nsys.exit(7)\n')
            result=subprocess.run(['bash',str(scripts/'phase02.sh'),'dataplane','02.09','all',str(records)],capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,7,result.stderr)
            self.assertGreater(result.stdout.index('执行失败汇总'),result.stdout.index('PLAY RECAP'))
            self.assertIn('首个失败步骤：l2',result.stdout)
            self.assertIn('本次回退与清理：PASS',result.stdout)
            self.assertIn('完整日志：',result.stdout)
            value=json.loads(next(records.glob('summary-all-*.json')).read_text())
            self.assertEqual(value['exit_code'],7)
            saved=Path(value['log']).read_text()
            self.assertGreater(saved.index('执行失败汇总'),saved.index('PLAY RECAP'))


if __name__=='__main__':unittest.main()
