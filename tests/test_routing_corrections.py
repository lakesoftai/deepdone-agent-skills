"""Genuine controls for the three independently reproduced DD-006 defects."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

import test_compact_task_eval as compact
from test_cross_agent_eval import load_runner
from test_routing import check
from test_reviewed_change_set import ROOT
sys.path.insert(0, str(ROOT/'skills/deepdone/scripts'))
import routing as r
import verification as v
import capture_reviewed_change_set as capture
import commit_progress as commit


def files(root):
    return {p.relative_to(root).as_posix(): (p.stat().st_mode, p.read_bytes())
            for p in root.rglob('*') if p.is_file()}


class RoutingCorrectionTests(unittest.TestCase):
    def test_candidate_ceiling_with_existing_authority(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);runner,state,_=compact.CompactTaskGraderTests().prepare(root)
            f=r.observe(root,task=compact.TASK);before=files(root)
            result=r.route(f,mode='until-commit-candidate',requested='commit',authority={'commit':True})
            self.assertEqual(result['required_action'],'candidate')
            self.assertEqual(result['admitted_action'],'candidate',result)
            self.assertEqual(r.route(f,requested='commit',authority={'commit':True})['admitted_action'],'commit')
            self.assertEqual(r.route(f,requested='commit',authority={'commit':False})['stop_reason'],'authority_required')
            self.assertEqual(r.route(f,mode='end-to-end')['admitted_action'],'commit')
            self.assertEqual(files(root),before)

    def test_excluded_generated_cache_and_overlapping_check_projection(self):
        for overlap in (False,True):
            with self.subTest(overlap=overlap),tempfile.TemporaryDirectory() as d:
                root=Path(d);runner=load_runner();runner.init_repo(root)
                ignore=root/'.gitignore';ignore.write_text(ignore.read_text()+'src/generated/\n')
                runner.write(root/'src/shared.py','VALUE = 1\n')
                state=runner.seed_active(root,roadmap=True);ledger='notes/epics/current.md';path=root/ledger
                runner.write(root/'src/generated/cache.txt','disposable generated cache')
                runner.write(root/'src/calc.py','def add(a,b): return a+b\ndef subtract(a,b): return a-b\n')
                text=path.read_text().replace('- [ ] add subtract','- [x] add subtract')
                path.write_text(text)
                first=check();first['inputs']=[{'path':'src','role':'source'}]
                first['exclusions']=[{'path':'src/generated','reason':'generated disposable cache'}]
                checks=[first]
                if overlap:
                    first['exclusions'].append({'path':'src/shared.py','reason':'covered by independent check'})
                    second=copy.deepcopy(first);second.update(id='shared',acceptance='shared source is readable',
                        inputs=[{'path':'src/shared.py','role':'source'}],exclusions=[],
                        argv=[sys.executable,'-I','-B','-c',"exec(open('src/shared.py').read()); assert isinstance(VALUE,int)"])
                    checks.append(second)
                v.initialize(root,ledger,checks,'genuine excluded source fixture',roadmap='notes/roadmap.md')
                for c in checks:self.assertEqual(v.run_check(root,ledger,c['id'])['exit_code'],0)
                review=runner.section(runner.passing_ledger(state['base'],['src/'],roadmap=True),'Review')
                review=review.replace('    exclude:\n','    exclude:\n      - src/generated\n')
                text=path.read_text().replace(runner.section(path.read_text(),'Review'),review).replace('## Status\n\nactive','## Status\n\ncomplete')
                path.write_text(text)
                road=root/'notes/roadmap.md';road.write_text(road.read_text().replace('- [-] Current Epic','- [x] Current Epic').replace('- state: active','- state: complete-pending-advance'))
                manifest=capture.capture(root,ledger)
                self.assertEqual(v.validate(root,ledger),[])
                self.assertEqual(commit.validate_reviewed_change_set(root,ledger,text,None,commit.parse_status_z(root))[2],[])
                before=files(root);f=r.observe(root,ledger=ledger)
                self.assertEqual(f['errors'],[],f)
                self.assertEqual(files(root),before)
                if overlap:
                    (root/'src/shared.py').write_text('VALUE = 2\n')
                    g=r.observe(root,ledger=ledger)
                    self.assertNotEqual(f['token'],g['token'])
                    self.assertEqual(g['readiness'],'stale',g)
                else:
                    result=runner.run([sys.executable,'-B',str(ROOT/'skills/deepdone/scripts/commit_progress.py'),'--ledger',ledger,
                        '--reviewed-change-set',str(manifest.relative_to(root.resolve())),'--commit','--yes','--authorized-by','exact-user-request'],root)
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                    before=files(root);g=r.observe(root,ledger=ledger)
                    self.assertEqual(r.route(g,requested='advance')['admitted_action'],'advance',g)
                    self.assertEqual(files(root),before)

    def test_explicit_epic_intake_requires_two_planned_milestones(self):
        bodies={
            'marker':'',
            'single':'- [ ] First\n  - acceptance: first works',
            'missing-acceptance':'- [ ] First\n  - acceptance: first works\n- [ ] Second',
            'duplicate':'- [ ] First\n  - acceptance: first works\n- [ ] First\n  - acceptance: second works',
            'already-complete':'- [x] First\n  - acceptance: first works\n- [ ] Second\n  - acceptance: second works',
            'valid':'- [ ] First\n  - acceptance: first works\n- [ ] Second\n  - acceptance: second works\n  - depends on: First',
        }
        for name,body in bodies.items():
            with self.subTest(name=name),tempfile.TemporaryDirectory() as d:
                root=Path(d);runner=load_runner();runner.init_repo(root);state=runner.seed_intake(root,'epic')
                text=runner.pending_ledger('Greet','temporary')
                text=text.replace(runner.section(text,'Milestones'),body)
                runner.write(root/'notes/epics/greet.md',text)
                errors=runner.grade_intake(root,state)
                self.assertEqual(bool(errors),name!='valid',errors)
