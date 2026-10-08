"""Deterministic grader checks, without running a paid/live model."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

import test_cross_agent_eval as fixtures
from test_reviewed_change_set import ROOT
sys.path.insert(0, str(ROOT / 'skills/deepdone/scripts'))
import verification as v
import capture_reviewed_change_set as capture

TASK = '.deepdone/tasks/calculator.md'


class CompactTaskGraderTests(unittest.TestCase):
    def prepare(self, root, *, source=None, weak=False):
        runner=fixtures.load_runner(); runner.init_repo(root); state=runner.seed_task(root)
        runner.write(root/'src/calc.py', source or 'def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b\n')
        check={'id':'arithmetic','acceptance':'Addition and subtraction return expected results','required':True,
               'argv':[sys.executable,'-I','-B','-c', 'pass' if weak else "exec(open('src/calc.py').read()); assert add(2, 7) == 9; assert subtract(2, 7) == -5"],
               'cwd':'.','inputs':[{'path':'src','role':'source'},{'path':'tests','role':'source'}],
               'exclusions':[],'env':{},'context':'local-files','timeout':5}
        v.initialize(root,TASK,[check],'deterministic task fixture')
        self.assertEqual(v.run_check(root,TASK,'arithmetic')['exit_code'],0)
        path=root/TASK; text=path.read_text()
        review=runner.section(runner.passing_ledger(state['base'],['src/','tests/']),'Review').replace('notes/epics/current.md',TASK)
        text=text.replace('- reviewed-at: not-run\n  result: pending',review).replace('## Status\n\nactive','## Status\n\ncomplete')
        path.write_text(text); manifest=capture.capture(root,TASK)
        return runner,state,manifest

    def test_valid_task_candidate_and_unexpected_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);runner,state,manifest=self.prepare(root)
            before=v.git_context(root)
            self.assertEqual(runner.grade_lifecycle(root,state),[])
            self.assertEqual(v.git_context(root),before)
            self.assertFalse((root/'notes/epics').exists())
            m=json.loads(manifest.read_text());capture.stage_paths_from_commit(root,m['review_commit'],{'src/calc.py'})
            runner.git(root,'commit','-qm','unauthorized for candidate fixture')
            self.assertIn('lifecycle changed HEAD before authorized commit',runner.grade_lifecycle(root,state))

    def test_broken_behavior_with_real_weak_tests_is_rejected(self):
        for source in ('def add(a,b): return a+b\ndef subtract(a,b): return a+b\n',
                       'def add(a,b): return a-b\ndef subtract(a,b): return a-b\n'):
            with self.subTest(source=source),tempfile.TemporaryDirectory() as tmp:
                runner,state,_=self.prepare(Path(tmp),source=source,weak=True)
                self.assertTrue(any('behavior check failed' in e for e in runner.grade_lifecycle(Path(tmp),state)))

    def test_fake_markers_stale_and_cross_unit_evidence(self):
        for variant in ('markers','stale','cross-unit'):
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);runner,state,manifest=self.prepare(root)
                if variant=='markers':
                    path=root/TASK;path.write_text(path.read_text().split('## Verification Contract')[0])
                elif variant=='stale': (root/'src/calc.py').write_text((root/'src/calc.py').read_text()+'# changed\n')
                else:
                    m=json.loads(manifest.read_text());m['ledger_path']='notes/epics/current.md';manifest.write_text(json.dumps(m))
                errors=runner.grade_lifecycle(root,state)
                self.assertTrue(errors)
                self.assertTrue(any(word in ';'.join(errors) for word in ('verification contract','stale','ledger does not match')))
