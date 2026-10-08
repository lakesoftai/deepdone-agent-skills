"""Local fixture/stub exercises; not live-model or policy-compliance proof."""
import base64
from pathlib import Path
import sys
import tempfile
import unittest

import test_compact_task_eval as compact
from test_cross_agent_eval import load_runner
from test_routing import event
from test_reviewed_change_set import ROOT
sys.path.insert(0,str(ROOT/'skills/deepdone/scripts'))
import capture_reviewed_change_set as capture
import routing as r
import verification as v

LEDGER='notes/epics/current.md'
CORRECT="def allowed(role):\n    return role in {'admin'}\n"
BROKEN="def allowed(role):\n    return bool(role)\n"
STRONG="exec(open('src/auth.py').read()); assert allowed('admin') is True; assert allowed('viewer') is False, 'NONADMIN_ALLOWED'"


def access_check(script=STRONG):
    return {'id':'access','acceptance':'Only admin is allowed','required':True,
            'argv':[sys.executable,'-I','-B','-c',script], 'cwd':'.',
            'inputs':[{'path':'src','role':'source'},{'path':'tests','role':'source'}],
            'exclusions':[],'env':{},'context':'local-files','timeout':5}


def evidence(root):
    return {p:p.read_bytes() for p in (root/v.namespace(LEDGER)).rglob('*.json')}


def append_review(root,result,notes):
    path=root/LEDGER
    path.write_text(path.read_text().replace('## Open Loops',f'- reviewed-at: fixture\n  result: {result}\n  notes: {notes}\n\n## Open Loops'))


class BehavioralWorkflowTests(unittest.TestCase):
    def seed(self,root):
        runner=load_runner();runner.init_repo(root);state=runner.seed_review_fix(root)
        return runner,state

    def reviewed(self,root,source=CORRECT,weak=False):
        runner,state=self.seed(root)
        (root/'src/auth.py').write_text(source)
        (root/'tests/test_auth.py').write_text("import unittest\nfrom src.auth import allowed\nclass AuthTests(unittest.TestCase):\n    def test_admin(self): self.assertTrue(allowed('admin'))\n    def test_viewer(self): self.assertFalse(allowed('viewer'))\n")
        script="exec(open('src/auth.py').read()); assert isinstance(allowed('admin'),bool)" if weak else STRONG
        v.initialize(root,LEDGER,[access_check(script)],'fixture-owned current checks')
        self.assertEqual(v.run_check(root,LEDGER,'access')['exit_code'],0)
        append_review(root,'fail','fixture reviewer found incomplete denied-role coverage')
        path=root/LEDGER;review=runner.section(runner.passing_ledger(state['base'],['src/','tests/']),'Review')
        path.write_text(path.read_text().replace('## Open Loops',review+'\n\n## Open Loops').replace('## Status\n\nactive','## Status\n\ncomplete'))
        capture.capture(root,LEDGER)
        return runner,state

    def test_review_oracle_rejects_broken_behavior_despite_real_weak_checks(self):
        for source in (BROKEN,"def allowed(role): return role != 'viewer'\n","def allowed(role): return False\n"):
            with self.subTest(source=source),tempfile.TemporaryDirectory() as d:
                root=Path(d);runner,state=self.reviewed(root,source,weak=True)
                self.assertTrue(any('behavior check failed' in e for e in runner.grade_review_fix(root,state)))

    def test_fake_markers_stale_evidence_and_index_are_rejected(self):
        for variant in ('markers','source','index'):
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as d:
                root=Path(d);runner,state=self.reviewed(root)
                self.assertEqual(runner.grade_review_fix(root,state),[])
                if variant=='markers':
                    path=root/LEDGER;path.write_text(path.read_text().split('## Verification Contract')[0])
                elif variant=='source':(root/'src/auth.py').write_text(BROKEN)
                else:runner.git(root,'add','src/auth.py')
                self.assertTrue(runner.grade_review_fix(root,state))

    def test_diagnostic_symptom_setup_failure_feedback_and_readiness(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);runner,_=self.seed(root)
            v.initialize(root,LEDGER,[access_check()],'reproduce the specified denied-role behavior')
            diagnostic=v.run_check(root,LEDGER,'access','diagnostic')
            stderr=base64.b64decode(diagnostic['output']['stderr']['excerpt']).decode()
            self.assertNotEqual(diagnostic['exit_code'],0)
            self.assertIn('AssertionError: NONADMIN_ALLOWED',stderr)
            old=evidence(root)
            setup=access_check('import missing_fixture_dependency');setup.update(id='setup',required=False)
            v.initialize(root,LEDGER,[access_check(),setup],'distinguish setup from product failure')
            failed_setup=v.run_check(root,LEDGER,'setup','diagnostic')
            output=base64.b64decode(failed_setup['output']['stderr']['excerpt']).decode()
            self.assertIn('ModuleNotFoundError',output);self.assertNotIn('NONADMIN_ALLOWED',output)
            (root/'src/auth.py').write_text(CORRECT)
            self.assertEqual(v.run_check(root,LEDGER,'access','feedback')['exit_code'],0)
            self.assertTrue(v.validate(root,LEDGER),'feedback must not become readiness')
            self.assertEqual(v.run_check(root,LEDGER,'access','readiness')['exit_code'],0)
            self.assertEqual(v.validate(root,LEDGER),[])
            self.assertTrue(all(p.read_bytes()==content for p,content in old.items()))
            contract=v.read_contract((root/LEDGER).read_text(),LEDGER)
            self.assertEqual([a['purpose'] for a in contract['attempts']][-4:],['diagnostic','diagnostic','feedback','readiness'])

    def test_changed_repair_crosses_verify_before_another_repair(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);runner,_=self.seed(root)
            v.initialize(root,LEDGER,[access_check()],'required denied-role check')
            self.assertNotEqual(v.run_check(root,LEDGER,'access')['exit_code'],0)
            f=r.observe(root,ledger=LEDGER)
            events=[event(f,'implement','changed'),event(f,'verify','fail')]
            findings=dict(token=f['token'],slice=f['slice'],basis='Actual NONADMIN_ALLOWED assertion failure',disposition='local')
            self.assertEqual(r.route(f,{'outcomes':events,'findings':findings},mode='until-epic')['admitted_action'],'verification-repair')
            old=evidence(root)
            (root/'src/auth.py').write_text(CORRECT)
            g=r.observe(root,ledger=LEDGER);events.append(event(g,'fixup','changed',action='verification-repair'))
            self.assertEqual(r.route(g,{'outcomes':events},mode='until-epic')['admitted_action'],'verify')
            self.assertEqual(v.run_check(root,LEDGER,'access','feedback')['exit_code'],0)
            self.assertEqual(v.run_check(root,LEDGER,'access')['exit_code'],0)
            g=r.observe(root,ledger=LEDGER);events.append(event(g,'verify'))
            self.assertEqual(r.route(g,{'outcomes':events},mode='until-epic')['admitted_action'],'review')
            # A distinct review repair has its own allowance.
            append_review(root,'fail','fixture reviewer requests the missing test-file regression')
            g=r.observe(root,ledger=LEDGER)
            findings=dict(token=g['token'],slice=g['slice'],basis='test_auth.py has only an admin case',disposition='local')
            self.assertEqual(r.route(g,{'outcomes':events,'findings':findings},mode='until-epic')['admitted_action'],'fixup')
            with (root/'tests/test_auth.py').open('a') as file:file.write("\n    def test_viewer(self): self.assertFalse(allowed('viewer'))\n")
            append_review(root,'pending','regression added')
            g=r.observe(root,ledger=LEDGER);events.append(event(g,'fixup','changed'))
            self.assertEqual(r.route(g,{'outcomes':events},mode='until-epic')['admitted_action'],'verify')
            self.assertEqual(v.run_check(root,LEDGER,'access')['exit_code'],0)
            g=r.observe(root,ledger=LEDGER);events.append(event(g,'verify'))
            self.assertEqual(r.route(g,{'outcomes':events},mode='until-epic')['admitted_action'],'review')
            # A new source observation cannot reset either consumed allowance.
            (root/'src/auth.py').write_text(BROKEN)
            g=r.observe(root,ledger=LEDGER);events.append(event(g,'implement','changed'))
            self.assertNotEqual(v.run_check(root,LEDGER,'access')['exit_code'],0)
            g=r.observe(root,ledger=LEDGER);events.append(event(g,'verify','fail'))
            findings=dict(token=g['token'],slice=g['slice'],basis='Observed repeated denial failure',disposition='local')
            self.assertEqual(r.route(g,{'outcomes':events,'findings':findings},mode='until-epic')['stop_reason'],'verification_repair_budget')
            self.assertEqual(r.route(g,{'outcomes':events},mode='until-epic')['stop_reason'],'verification_repair_budget')
            self.assertTrue(all(p.read_bytes()==content for p,content in old.items()))

    def test_clean_task_epic_and_rejected_wrong_advice(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);runner,state=self.reviewed(root)
            before=(root/'src/auth.py').read_bytes()
            # Fixture adjudication: an isolated counterexample refutes the advice; never apply it.
            advice="def allowed(role): return role != 'admin'\nassert allowed('admin') is True"
            result=runner.run([sys.executable,'-I','-B','-c',advice],root)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual((root/'src/auth.py').read_bytes(),before)
            self.assertEqual(runner.grade_review_fix(root,state),[])
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);runner,state,_=compact.CompactTaskGraderTests().prepare(root)
            self.assertEqual(runner.grade_lifecycle(root,state),[])
