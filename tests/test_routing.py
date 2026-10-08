"""Deterministic fixture traces, not live-model compliance evidence."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

import test_compact_task_eval as compact
TASK = compact.TASK
from test_cross_agent_eval import load_runner
from test_reviewed_change_set import ROOT
sys.path.insert(0, str(ROOT / 'skills/deepdone/scripts'))
import routing as r
import verification as v
import capture_reviewed_change_set as capture


def event(facts, phase, result='pass', action=None, reason='fixture', slice_=None):
    return dict(unit=facts['unit']['identity'], slice=slice_ or facts['slice'], token=facts['token'],
                phase=phase, action=action or phase, result=result, reason=reason)


def check():
    return {'id':'arithmetic','acceptance':'Addition and subtraction return expected results','required':True,
            'argv':[sys.executable,'-I','-B','-c',"exec(open('src/calc.py').read()); assert add(2,7)==9; assert subtract(2,7)==-5"],
            'cwd':'.','inputs':[{'path':'src','role':'source'},{'path':'tests','role':'source'}],
            'exclusions':[],'env':{},'context':'local-files','timeout':5}


class RoutingTests(unittest.TestCase):
    def task(self, root):
        runner=load_runner();runner.init_repo(root); state=runner.seed_task(root)
        return runner,state

    def test_initial_and_resumed_task_observations(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); runner,_=self.task(root)
            (root/'scratch.txt').write_text('unrelated')
            f=r.observe(root,task=TASK)
            self.assertEqual(r.route(f)['admitted_action'],'implement', f)
            self.assertEqual(r.route(f,mode='inspect-only')['stop_reason'],'inspect_only')
            self.assertEqual(r.route(f,requested='commit')['stop_reason'],'requested_phase_mismatch')
            (root/'src/calc.py').write_text('def add(a,b): return a+b\ndef subtract(a,b): return a-b\n')
            f=r.observe(root,task=TASK)
            self.assertEqual(r.route(f)['admitted_action'],'sync',f)
            resolution=dict(token=f['token'],slice=f['slice'],stage='implementation-ready',basis='Inspected subtract requirement and source diff')
            self.assertEqual(r.route(f,{'resolution':resolution})['admitted_action'],'verify')
            ctx={'outcomes':[event(f,'sync',reason='progress_unknown')]}
            self.assertEqual(r.route(f,ctx,mode='until-epic')['stop_reason'],'unchanged_repeat')
            (root/'src/calc.py').chmod(0o755)
            g=r.observe(root,task=TASK)
            self.assertNotEqual(f['token'],g['token'])
            self.assertEqual(r.route(g,{'resolution':resolution})['stop_reason'],'invalid_context')
            self.assertEqual((root/'scratch.txt').read_text(),'unrelated')

    def test_real_task_trace_receipt_boundary_candidate_commit_terminal(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);runner,state=self.task(root)
            (root/'src/calc.py').write_text('def add(a,b): return a+b\ndef subtract(a,b): return a-b\n')
            v.initialize(root,TASK,[check()],'planned check')
            f=r.observe(root,task=TASK)
            events=[event(f,'implement','changed')]
            v.run_check(root,TASK,'arithmetic')
            f=r.observe(root,task=TASK)
            self.assertEqual(r.route(f,{'outcomes':events},mode='until-epic')['admitted_action'],'verify')
            events.append(event(f,'verify'))
            self.assertEqual(r.route(f,{'outcomes':events},mode='until-epic')['admitted_action'],'review')
            self.assertEqual(r.route(f,{'outcomes':events},mode='until-milestone')['stop_reason'],'milestone_verified')
            before={p:p.read_bytes() for p in (root/v.namespace(TASK)/'receipts').glob('*.json')}
            path=root/TASK;text=path.read_text()
            review=runner.section(runner.passing_ledger(state['base'],['src/','tests/']),'Review').replace('notes/epics/current.md',TASK)
            path.write_text(text.replace('- reviewed-at: not-run\n  result: pending',review).replace('## Status\n\nactive','## Status\n\ncomplete'))
            manifest=capture.capture(root,TASK)
            g=r.observe(root,task=TASK)
            self.assertEqual(f['token'],g['token'],'Review bookkeeping must not change progress token')
            self.assertTrue(g['review_valid'],g)
            self.assertEqual(r.route(g)['admitted_action'],'candidate')
            self.assertEqual(r.route(g,mode='end-to-end',authority={'commit':False})['stop_reason'],'authority_required')
            self.assertEqual(r.route(g,mode='end-to-end')['admitted_action'],'commit')
            (root/'scratch.txt').write_text('unrelated');runner.git(root,'add','scratch.txt')
            g=r.observe(root,task=TASK)
            self.assertEqual(r.route(g)['admitted_action'],'candidate')
            self.assertEqual(r.route(g,mode='end-to-end')['stop_reason'],'commit_blocked')
            runner.git(root,'restore','--staged','scratch.txt')
            result=runner.run([sys.executable,'-B',str(ROOT/'skills/deepdone/scripts/commit_progress.py'),'--task',TASK,'--reviewed-change-set',str(manifest.relative_to(root.resolve())),'--commit','--yes','--authorized-by','exact-user-request'],root)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            g=r.observe(root,task=TASK)
            self.assertEqual(r.route(g)['state'],'complete',g)
            self.assertIsNone(r.observe(root)['unit'])
            self.assertEqual(r.route(g,requested='advance')['stop_reason'],'unsupported_task_lifecycle')
            self.assertEqual(r.route(g,requested='pr-draft')['admitted_action'],'pr-draft')
            self.assertEqual(before,{p:p.read_bytes() for p in before})

    def test_milestone_shapes_and_order(self):
        def ledger(body): return '## Milestones\n\n'+body
        rows=r.milestones(ledger('- [x] M1\n  - acceptance: first\n- [-] M2\n  - acceptance: second\n  - depends on: M1\n- [ ] verify regression surface\n  - acceptance: third\n'))
        self.assertEqual(len(rows),3);self.assertEqual(r.next_slice(rows)['title'],'M2')
        blocked=r.milestones(ledger('- [!] first\n  - acceptance: first\n- [-] second\n  - acceptance: second\n'))
        self.assertEqual(r.next_slice(blocked)['marker'],'!')
        for body in ('', '- [ ] M1', '- [ ] M1\n  - acceptance: yes\n  - depends on: M2',
                     '- [-] M1\n  - acceptance: yes\n- [-] M2\n  - acceptance: yes',
                     '- [ ] M1\n  - acceptance: yes\n  - depends on: M2\n- [ ] M2\n  - acceptance: yes\n  - depends on: M1'):
            with self.subTest(body=body),self.assertRaises(ValueError): r.milestones(ledger(body))

    def test_context_and_modes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.task(root);f=r.observe(root,task=TASK)
            for ctx in ({'readiness':True},{'outcomes':{}},{'resolution':{'stage':True}}):
                self.assertEqual(r.route(f,ctx)['stop_reason'],'invalid_context')
            e=event(f,'implement','changed')
            for mode in r.MODES:
                out=r.route(f,{'outcomes':[e]},mode=mode)
                self.assertEqual(out['admitted_action'],None if mode in {'inspect-only','one-step'} else 'verify',out)
            f['readiness']='pass';f['review']='fail'
            ctx={'findings':dict(token=f['token'],slice=f['slice'],disposition='local',basis='Inspected concrete incorrect subtraction')}
            self.assertEqual(r.route(f,ctx,mode='until-epic')['admitted_action'],'fixup')
            ctx['outcomes']=[event(f,'review','fail')]
            self.assertEqual(r.route(f,ctx,mode='until-review')['stop_reason'],'review_outcome')
            ctx['outcomes']=[event(f,'fixup','unchanged')]
            self.assertEqual(r.route(f,ctx,mode='until-epic')['stop_reason'],'review_repair_budget')
            f['stop']=True
            self.assertEqual(r.route(f,ctx,mode='until-epic')['stop_reason'],'stop_file')

    def test_typed_intake_and_semantic_index_oracles(self):
        for kind in ('task','epic'):
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);runner=load_runner();runner.init_repo(root);state=runner.seed_intake(root,kind)
                if kind=='task':
                    # Reuse canonical task text without allowing fixture seeding to alter baseline HEAD.
                    with tempfile.TemporaryDirectory() as other:
                        op=Path(other);self.task(op);runner.write(root/TASK,(op/TASK).read_text())
                else:runner.write(root/'notes/epics/greet.md',runner.pending_ledger('Greeting','greet').replace('## Decisions','- [ ] regression\n  - acceptance: existing behavior remains correct\n\n## Decisions'))
                self.assertEqual(runner.grade_intake(root,state),[])
                runner.write(root/'src/greet.py','early implementation')
                self.assertIn('planning-only intake changed source',runner.grade_intake(root,state))
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);runner,state,_=compact.CompactTaskGraderTests().prepare(root)
            self.assertEqual(runner.grade_lifecycle(root,state),[])
            runner.git(root,'add','src/calc.py')
            self.assertIn('unexpected semantic index change',runner.grade_lifecycle(root,state))
            state['index']=runner.semantic_index(root)
            self.assertEqual(runner.grade_lifecycle(root,state),[])
            runner.git(root,'restore','--staged','src/calc.py')
            self.assertIn('unexpected semantic index change',runner.grade_lifecycle(root,state))

    def test_real_two_milestone_epic(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);runner=load_runner();runner.init_repo(root);state=runner.seed_active(root,roadmap=True)
            ledger='notes/epics/current.md';path=root/ledger
            body='- [ ] M1\n  - acceptance: subtraction works\n- [ ] verify regression surface\n  - acceptance: regression remains correct\n  - depends on: M1'
            text=path.read_text();text=text.replace(runner.section(text,'Milestones'),body);path.write_text(text)
            ctx={'scope':{'include':['src','tests'],'exclude':[]},'outcomes':[]}
            f=r.observe(root,ledger=ledger,ctx=ctx)
            self.assertEqual(r.route(f,ctx,mode='until-epic')['admitted_action'],'implement',f)
            for index,title in enumerate(('M1','verify regression surface')):
                (root/'src/calc.py').write_text('def add(a,b): return a+b\ndef subtract(a,b): return a-b\n'+('# regression annotation\n' if index else ''))
                text=path.read_text().replace('- [ ] '+title,'- [x] '+title)
                if index:
                    text=text.replace('## Open Loops','- reviewed-at: not-run\n  result: pending\n  notes: implementation changed\n\n## Open Loops')
                path.write_text(text)
                if not index:v.initialize(root,ledger,[check()],'arithmetic readiness',roadmap='notes/roadmap.md')
                f=r.observe(root,ledger=ledger,ctx=ctx)
                ctx['outcomes'].append(event(f,'implement','changed',slice_=title))
                out=r.route(f,ctx,mode='until-epic')
                self.assertEqual(out['admitted_action'],'verify',out)
                self.assertEqual(out['slice'],title)
                if not index:
                    other = event(f,'verify',slice_='verify regression surface')
                    self.assertEqual(r.route(f,{**ctx,'outcomes':ctx['outcomes']+[other]},mode='until-epic')['admitted_action'],'verify')
                self.assertEqual(v.run_check(root,ledger,'arithmetic')['exit_code'],0)
                f=r.observe(root,ledger=ledger,ctx=ctx);ctx['outcomes'].append(event(f,'verify',slice_=title))
                self.assertEqual(r.route(f,ctx,mode='until-epic')['admitted_action'],'review')
                text=path.read_text()
                review=runner.section(runner.passing_ledger(state['base'],['src/','tests/'],roadmap=True),'Review')
                review=review.replace('a1b2c3d4','a1b2c3d'+str(index))
                text=text.replace('## Open Loops',review+'\n\n## Open Loops')
                if index:
                    text=text.replace('## Status\n\nactive','## Status\n\ncomplete')
                    road=root/'notes/roadmap.md';road.write_text(road.read_text().replace('- [-] Current Epic','- [x] Current Epic').replace('- state: active','- state: complete-pending-advance'))
                path.write_text(text);manifest=capture.capture(root,ledger)
                f=r.observe(root,ledger=ledger,ctx=ctx);ctx['outcomes'].append(event(f,'review',slice_=title))
                self.assertTrue(f['review_valid'],f)
                if not index:
                    self.assertEqual(f['unit']['status'],'active')
                    self.assertEqual(r.route(f,ctx,mode='until-epic')['admitted_action'],'implement')
                    self.assertEqual(r.route(f,{**ctx,'target':'verify regression surface'},mode='until-milestone')['admitted_action'],'implement')
                    receipts={p:p.read_bytes() for p in (root/v.namespace(ledger)/'receipts').glob('*.json')}
                else:
                    self.assertEqual(r.route(f,ctx,mode='until-epic')['stop_reason'],'review_target_reached')
            self.assertTrue(all(p.read_bytes()==b for p,b in receipts.items()))
            result=runner.run([sys.executable,'-B',str(ROOT/'skills/deepdone/scripts/commit_progress.py'),'--ledger',ledger,'--reviewed-change-set',str(manifest.relative_to(root.resolve())),'--commit','--yes','--authorized-by','exact-user-request'],root)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            f=r.observe(root,ledger=ledger,ctx={'scope':ctx['scope']})
            self.assertEqual(r.route(f,requested='advance')['admitted_action'],'advance',f)

    def test_evidence_states_and_read_only_refusals(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);runner,_=self.task(root)
            self.assertEqual(v.assess(root,TASK)['state'],'absent')
            v.initialize(root,TASK,[check()],'checks')
            self.assertEqual(v.assess(root,TASK)['state'],'missing')
            v.run_check(root,TASK,'arithmetic')
            self.assertEqual(v.assess(root,TASK)['state'],'failed')
            (root/'src/calc.py').write_text('def add(a,b): return a+b\ndef subtract(a,b): return a-b\n')
            v.run_check(root,TASK,'arithmetic')
            self.assertEqual(v.assess(root,TASK)['state'],'pass')
            runner.git(root,'update-index','--assume-unchanged','src/calc.py')
            (root/'src/calc.py').write_text('def add(a,b): return a+b\ndef subtract(a,b): return a+b\n')
            self.assertEqual(v.assess(root,TASK)['state'],'stale')
            record=root/TASK;text=record.read_text();contract=v.read_contract(text,TASK)
            last=contract['attempts'][-1].copy();last.update(sequence=3,id='a'*32,status='pending',receipt=None);contract['attempts'].append(last)
            record.write_text(v.render_contract(text,contract))
            self.assertEqual(v.assess(root,TASK)['state'],'pending')
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            f=r.observe(root,task=TASK);self.assertEqual(r.route(f)['stop_reason'],'evidence_pending')
            after={p:p.read_bytes() for p in before};self.assertEqual(before,after)
            contract['attempts'][-1]['id']='bad';record.write_text(v.render_contract(text,contract))
            self.assertEqual(v.assess(root,TASK)['state'],'invalid')

    def test_budget_targets_do_not_reset_and_authority_is_separate(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);runner,state,_=compact.CompactTaskGraderTests().prepare(root)
            f=r.observe(root,task=TASK)
            for mode,reason in [('until-epic','review_target_reached'),('until-review','review_target_reached'),('until-milestone','milestone_verified')]:
                with self.subTest(mode=mode):self.assertEqual(r.route(f,mode=mode)['stop_reason'],reason)
            ctx={'outcomes':[event(f,'commit',action='candidate')]}
            self.assertEqual(r.route(f,ctx,mode='until-commit-candidate')['stop_reason'],'candidate_prepared')
            ctx={'outcomes':[event(f,'commit','blocked')]}
            self.assertEqual(r.route(f,ctx,mode='end-to-end')['stop_reason'],'commit_outcome')
            for result in ('pass','fail','blocked'):
                ctx={'outcomes':[event(f,'review',result)]}
                self.assertEqual(r.route(f,ctx,mode='until-review')['stop_reason'],'review_outcome')
            f.update(review_valid=False,review='fail',readiness='failed')
            ctx={'findings':dict(token=f['token'],slice=f['slice'],basis='Observed local arithmetic failure',disposition='local'),
                 'outcomes':[event(f,'fixup','changed',action='verification-repair')]}
            ctx['outcomes'][0]['token']='prior-source-token'
            self.assertEqual(r.route(f,ctx,mode='until-epic')['stop_reason'],'verification_repair_budget')
            # Constructed conflict table: this is pure admission evidence, not a repository observation.
            f.update(readiness='pass',review='pending')
            ctx={'decision':dict(token=f['token'],slice=f['slice'],basis='Future implementation choice',need='future'),
                 'outcomes':[event(f,'implement','changed')]}
            self.assertEqual(r.route(f,ctx,mode='until-epic',requested='commit')['admitted_action'],'verify')
            self.assertEqual(r.route(f,requested='commit')['stop_reason'],'requested_phase_mismatch')

    def test_legacy_terminal_and_full_review_parser(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);runner=load_runner();runner.init_repo(root);runner.seed_active(root,roadmap=True)
            path=root/'notes/epics/current.md'
            path.write_text('# Old complete epic\n\n## Review\n\n- reviewed-at: old\n  result: pass\n  notes: legacy\n\n## Status\n\ncomplete\n')
            f=r.observe(root,ledger='notes/epics/current.md')
            self.assertEqual(r.route(f,requested='advance')['admitted_action'],'advance',f)
            self.assertEqual(r.route(f,requested='archive')['stop_reason'],'authority_required')
            import inspect_deepdone_state as inspector
            self.assertEqual(inspector.latest_review_result(path.read_text().replace('  notes: legacy','\n'.join('  notes: detail' for _ in range(130)))),'pass')

    def test_candidate_oracle_rejects_each_semantic_index_mutation(self):
        for mutation in ('unrelated','content','mode','head'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as d:
                root=Path(d);runner,state,_=compact.CompactTaskGraderTests().prepare(root)
                runner.git(root,'add','src/calc.py');state['index']=runner.semantic_index(root)
                if mutation=='unrelated':
                    (root/'scratch.txt').write_text('unrelated');runner.git(root,'add','scratch.txt')
                elif mutation=='mode':runner.git(root,'update-index','--chmod=+x','src/calc.py')
                elif mutation=='head':runner.git(root,'commit','-qm','unexpected')
                else:
                    (root/'src/calc.py').write_text('changed');runner.git(root,'add','src/calc.py')
                self.assertTrue(runner.grade_no_commit(root,state))
