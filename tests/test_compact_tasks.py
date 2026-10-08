"""Real compact-task lifecycle, selection, and receipt isolation regressions."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

import test_reviewed_change_set as fixtures
from test_reviewed_change_set import ROOT, git
sys.path.insert(0, str(ROOT / 'skills/deepdone/scripts'))
import work_unit as w
import verification as v
import capture_reviewed_change_set as capture
import check_reviewed_change_set as terminal

TASK = '.deepdone/tasks/demo.md'
SCRIPTS = ROOT / 'skills/deepdone/scripts'


def task_text(task_id='demo'):
    value = {'schema': 1, 'kind': 'task', 'id': task_id, 'goal': 'Return the expected application value',
             'scope': {'include': ['src/'], 'exclude': []},
             'acceptance': [{'check_id': 'app', 'condition': 'Application has expected value'}], 'constraints': []}
    return ('# Demo task\n\n## Task\n\n```json\n' + json.dumps(value, indent=2) + '\n```\n\n'
            '## Verification Log\n\nNo executions yet.\n\n## Review\n\n- reviewed-at: not-run\n  result: pending\n\n'
            '## Open Loops\n\nnone\n\n## Next Action\n\nImplement and verify the task.\n\n## Status\n\nactive\n')


class CompactTaskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.fixture = fixtures.ReviewedChangeSetTests()
        self.base = self.fixture.init_repo(self.root)
        (self.root / 'notes/epics/demo.md').unlink()
        (self.root / 'notes/epics').rmdir()
        (self.root / 'notes').rmdir()
        (self.root / 'src/app.py').write_text('VALUE = 2\n')
        self.path = self.root / TASK
        self.path.parent.mkdir(parents=True)
        self.path.write_text(task_text())
        self.check = {'id': 'app', 'acceptance': 'Application has expected value', 'required': True,
                      'argv': [sys.executable, '-I', '-B', '-c', "exec(open('src/app.py').read()); assert VALUE == 2"],
                      'cwd': '.', 'inputs': [{'path': 'src', 'role': 'source'}],
                      'exclusions': [], 'env': {}, 'context': 'local-files', 'timeout': 5}

    def cli(self, script, *args):
        return subprocess.run([sys.executable, '-B', str(SCRIPTS / (script + '.py')), *args],
                              cwd=self.root, text=True, capture_output=True)

    def preserved(self):
        return {'git': v.git_context(self.root), 'flags': git(self.root, 'ls-files', '-v').stdout,
                'config': (self.root / '.git/config').read_bytes(), 'refs': git(self.root, 'show-ref').stdout,
                'files': {str(p.relative_to(self.root)): (p.read_bytes(), p.stat().st_mode) for p in self.root.rglob('*')
                          if p.is_file() and '.git' not in p.parts}}

    def edit_task(self, **changes):
        text = self.path.read_text()
        block = re.search(r'```json\n(.*?)\n```', text, re.S)
        value = json.loads(block[1]); value.update(changes)
        self.path.write_text(text[:block.start(1)] + json.dumps(value, indent=2) + text[block.end(1):])

    def ready(self):
        v.initialize(self.root, TASK, [self.check], 'Initialize task')
        self.assertEqual(v.run_check(self.root, TASK, 'app')['exit_code'], 0)
        self.assertEqual(v.validate(self.root, TASK), [])

    def review(self):
        value = w.load(self.root, TASK)['task']
        include = ''.join(f'      - {p}\n' for p in value['scope']['include'])
        exclude = ''.join(f'      - {p}\n' for p in value['scope']['exclude'])
        review = (f'- reviewed-at: 2026-10-08T12:00:00Z\n  result: pass\n  review-id: task-demo-0001\n'
                  f'  base-head: {self.base}\n  manifest: .deepdone/reviews/task-demo-0001.json\n'
                  f'  scope:\n    include:\n{include}    exclude:\n{exclude}  evidence:\n    ledger: {TASK}\n  notes: no blocking findings')
        text = self.path.read_text()
        text = re.sub(r'(?<=## Review\n\n).*?(?=\n\n##)', review, text, count=1, flags=re.S)
        text = text.replace('## Status\n\nactive', '## Status\n\ncomplete')
        self.path.write_text(text)

    def capture(self):
        self.ready(); self.review()
        return capture.capture(self.root, TASK)

    def candidate(self):
        result = self.cli('commit_progress', '--task', TASK, '--candidate')
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(re.search(r'```json\n(.*?)\n```', result.stdout, re.S)[1])

    def commit(self):
        return self.cli('commit_progress', '--task', TASK, '--commit', '--yes', '--authorized-by', 'exact-user-request',
                        '--reviewed-change-set', '.deepdone/reviews/task-demo-0001.json')

    def test_manifest_binding_at_candidate_commit_and_terminal(self):
        manifest = self.capture()
        original = json.loads(manifest.read_text())
        other = self.path.with_name('other.md'); other.write_text(task_text('other'))
        mutations = {
            'scope': lambda m: m.update(scope={'include':['elsewhere'],'exclude':[]}),
            'additional-include': lambda m: m['scope']['include'].append('elsewhere'),
            'omitted-include': lambda m: m['scope'].update(include=[]),
            'additional-exclude': lambda m: m['scope']['exclude'].append('src/elsewhere'),
            'missing-scope': lambda m: m.pop('scope'),
            'duplicate-scope': lambda m: m.update(scope={'include':['src','src/'],'exclude':[]}),
            'cross-task': lambda m: m.update(evidence=[capture.filesystem_evidence(self.root,'ledger','.deepdone/tasks/other.md')]),
            'missing-evidence': lambda m: m.update(evidence=[]),
            'duplicate-role': lambda m: m['evidence'].append(copy.deepcopy(m['evidence'][0])),
            'extra-role': lambda m: m['evidence'].append(capture.filesystem_evidence(self.root,'roadmap','.deepdone/tasks/other.md')),
            'unknown-role': lambda m: m['evidence'][0].update(role='other'),
            'malformed-path': lambda m: m['evidence'][0].update(path=[]),
            'malformed-role': lambda m: m['evidence'][0].update(role=[]),
            'evidence-kind': lambda m: m['evidence'][0].update(kind='symlink'),
            'evidence-mode': lambda m: m['evidence'][0].update(mode='100755'),
            'evidence-hash': lambda m: m['evidence'][0].update(sha256='0'*64),
        }
        for name, mutate in mutations.items():
            with self.subTest(consumer='candidate/commit',mutation=name):
                data=copy.deepcopy(original); mutate(data); manifest.write_text(json.dumps(data))
                before=self.preserved()
                errors=';'.join(self.candidate()['commit_gate_errors'])
                self.assertRegex(errors,'scope|evidence')
                result=self.commit(); self.assertNotEqual(result.returncode,0)
                self.assertRegex(result.stderr,'scope|evidence')
                self.assertEqual(self.preserved(),before)
        manifest.write_text(json.dumps(original))
        self.assertEqual(self.commit().returncode,0)
        for name, mutate in mutations.items():
            with self.subTest(consumer='terminal/inspection',mutation=name):
                data=copy.deepcopy(original); mutate(data); manifest.write_text(json.dumps(data))
                before=self.preserved()
                result=self.cli('check_reviewed_change_set','--task',TASK)
                self.assertNotEqual(result.returncode,0); self.assertRegex(result.stderr,'scope|evidence')
                state=json.loads(self.cli('inspect_deepdone_state','--task',TASK).stdout)
                self.assertFalse(state['task_integration']['committed_clean'])
                self.assertRegex(';'.join(state['task_integration']['errors']),'scope|evidence')
                self.assertEqual(self.preserved(),before)
        manifest.write_text(json.dumps(original)); before=self.preserved()
        self.assertEqual(self.cli('check_reviewed_change_set','--task',TASK).returncode,0)
        self.assertEqual(self.preserved(),before)
        self.edit_task(goal='Changed after capture')
        self.assertIn('development evidence changed',self.cli('check_reviewed_change_set','--task',TASK).stderr)

    def test_manifest_scope_order_and_normalization(self):
        self.edit_task(scope={'include':['src','other'],'exclude':['src/generated','other/generated']})
        manifest=self.capture(); data=json.loads(manifest.read_text())
        data['scope']={'include':['other/','src/'],'exclude':['other/generated/','src/generated/']}
        manifest.write_text(json.dumps(data))
        self.assertEqual(self.candidate()['commit_gate_errors'],[])
        self.assertEqual(self.commit().returncode,0)
        self.assertEqual(self.cli('check_reviewed_change_set','--task',TASK).returncode,0)

    def test_current_epic_uses_shared_terminal_binding(self):
        self.fixture.setUp()
        (self.root/'notes/epics').mkdir(parents=True)
        ledger='notes/epics/demo.md'
        self.fixture.write_passing_ledger(self.root,self.base,['src/'])
        manifest=self.fixture.capture_ready(self.root)
        self.assertEqual(self.fixture.run_commit(self.root,manifest).returncode,0)
        self.assertEqual(self.cli('check_reviewed_change_set','--ledger',ledger).returncode,0)
        original=json.loads(manifest.read_text())
        for field,value in [('scope',{'include':['elsewhere'],'exclude':[]}),
                            ('evidence',[capture.filesystem_evidence(self.root,'ledger',TASK)])]:
            with self.subTest(field=field):
                data=copy.deepcopy(original);data[field]=value;manifest.write_text(json.dumps(data))
                before=self.preserved();result=self.cli('check_reviewed_change_set','--ledger',ledger)
                self.assertNotEqual(result.returncode,0);self.assertIn(field,result.stderr)
                self.assertEqual(self.preserved(),before)

    def test_broad_task_preserves_unrelated_lifecycle_records(self):
        (self.root/'.gitignore').write_text('.deepdone/\n')
        epic=self.root/'notes/epics/nested/other.md'; epic.parent.mkdir(parents=True)
        epic.write_text('malformed unrelated epic\n')
        roadmap=self.root/'notes/roadmap.md'; roadmap.write_text('malformed unrelated roadmap\n')
        git(self.root,'add','.gitignore','notes/roadmap.md');git(self.root,'commit','-qm','Track unrelated roadmap')
        self.base=git(self.root,'rev-parse','HEAD').stdout.strip()
        roadmap.write_text('unrelated dirty edit\n');roadmap.chmod(0o755)
        source=epic.with_name('source.py');source.write_text('VALUE = 3\n');source.chmod(0o755)
        self.edit_task(scope={'include':['.'],'exclude':[]})
        self.check['inputs']=[{'path':'.','role':'source'}]
        before={p:(p.read_bytes(),p.stat().st_mode) for p in (epic,roadmap)}
        manifest=self.capture(); data=json.loads(manifest.read_text())
        owned=capture.changed_paths(self.root,data['base_head'],data['review_commit'])
        self.assertEqual(owned,{'src/app.py','notes/epics/nested/source.py'})
        self.assertEqual([e['path'] for e in data['evidence']],[TASK])
        self.assertEqual(self.candidate()['commit_gate_errors'],[])
        self.assertEqual(self.commit().returncode,0)
        self.assertEqual(set(git(self.root,'diff-tree','--no-commit-id','--name-only','-r','HEAD').stdout.splitlines()),owned)
        self.assertEqual(git(self.root,'show','HEAD:notes/epics/nested/source.py').stdout,'VALUE = 3\n')
        self.assertTrue(git(self.root,'ls-tree','HEAD','notes/epics/nested/source.py').stdout.startswith('100755'))
        self.assertEqual({p:(p.read_bytes(),p.stat().st_mode) for p in before},before)
        self.assertEqual(git(self.root,'ls-files','--error-unmatch','notes/epics/nested/other.md',check=False).returncode,1)
        self.assertEqual(git(self.root,'show','HEAD:notes/roadmap.md').stdout,'malformed unrelated roadmap\n')
        self.assertEqual(self.cli('check_reviewed_change_set','--task',TASK).returncode,0)
        self.assertEqual(sorted(p.relative_to(self.root/'notes').as_posix() for p in (self.root/'notes').rglob('*') if p.is_file()),
                         ['epics/nested/other.md','epics/nested/source.py','roadmap.md'])

    def test_staged_unrelated_records_are_unowned(self):
        epic=self.root/'notes/epics/other.md';epic.parent.mkdir(parents=True)
        epic.write_text('unrelated epic\n');roadmap=self.root/'notes/roadmap.md';roadmap.write_text('unrelated roadmap\n')
        self.edit_task(scope={'include':['.'],'exclude':[]})
        self.capture()
        git(self.root,'add','-f','notes/epics/other.md','notes/roadmap.md')
        before=self.preserved();candidate=self.candidate()
        self.assertEqual(candidate['staged_unowned_files'],['notes/epics/other.md','notes/roadmap.md'])
        result=self.commit();self.assertNotEqual(result.returncode,0)
        self.assertIn('staged',result.stderr)
        self.assertEqual(self.preserved(),before)

    def test_task_lifecycle_projection_and_directory_boundaries(self):
        epic=self.root/'notes/epics/nested/other.md';epic.parent.mkdir(parents=True)
        epic.write_text('unrelated\n');roadmap=self.root/'notes/roadmap.md';roadmap.write_text('unrelated\n')
        self.check['inputs']=[{'path':'.','role':'source'}]
        task=v.fingerprint(self.root,TASK,self.check,None)
        self.assertNotIn('notes/epics/nested/other.md',[e['path'] for e in task['entries']])
        self.assertNotIn('notes/roadmap.md',[e['path'] for e in task['entries']])
        epic.chmod(0);roadmap.chmod(0)
        self.assertEqual(v.fingerprint(self.root,TASK,self.check,None),task)
        epic.chmod(0o644);roadmap.chmod(0o644)
        self.capture(); self.assertEqual(self.candidate()['commit_gate_errors'],[])
        for directory in ('notes/epics','notes/epics/ordinary'):
            with self.subTest(directory=directory):
                p=self.root/directory;p.mkdir(exist_ok=True)
                check={**self.check,'inputs':[{'path':'src','role':'source'},{'path':directory,'role':'source'}]}
                fp=v.fingerprint(self.root,TASK,check,None)
                with self.assertRaisesRegex(ValueError,'required source directory not materialized'):
                    v.source_tree(self.root,TASK,None,check,fp,'HEAD')
        with self.assertRaisesRegex(ValueError,'evidence path cannot be a declared input'):
            v.fingerprint(self.root,TASK,{**self.check,'inputs':[{'path':'notes/roadmap.md','role':'source'}]},None)
        original=v.fingerprint(self.root,'notes/epics/selected.md',self.check,None)
        self.assertIn('notes/roadmap.md',[e['path'] for e in original['entries']])

    def test_tracked_lifecycle_deletions_remain_unowned(self):
        epic=self.root/'notes/epics/other.md';epic.parent.mkdir(parents=True)
        epic.write_text('# Other\n\n## Status\n\ncomplete\n')
        self.assertEqual(w.select(self.root)[0]['path'],TASK)
        roadmap=self.root/'notes/roadmap.md';roadmap.write_text('# Roadmap\n')
        git(self.root,'add','-f','notes/epics/other.md','notes/roadmap.md')
        git(self.root,'commit','-qm','Track unrelated completed lifecycle')
        self.base=git(self.root,'rev-parse','HEAD').stdout.strip()
        self.edit_task(scope={'include':['.'],'exclude':[]})
        epic.unlink();roadmap.unlink();manifest=self.capture()
        data=json.loads(manifest.read_text())
        self.assertEqual(capture.changed_paths(self.root,data['base_head'],data['review_commit']),{'src/app.py'})
        self.assertEqual(self.commit().returncode,0)
        self.assertFalse(epic.exists());self.assertFalse(roadmap.exists())
        self.assertEqual(git(self.root,'show','HEAD:notes/roadmap.md').stdout,'# Roadmap\n')
        self.assertEqual(self.cli('check_reviewed_change_set','--task',TASK).returncode,0)

    def test_task_source_rename_cannot_cross_lifecycle_boundary(self):
        for old,new in [('notes/roadmap.md','notes/source.md'),('notes/source.md','notes/epics/renamed.md')]:
            with self.subTest(old=old,new=new):
                case=CompactTaskTests();case.setUp()
                try:
                    prior=case.root/old;prior.parent.mkdir(parents=True,exist_ok=True);prior.write_text('Unrelated bytes\n')
                    git(case.root,'add','-f',old);git(case.root,'commit','-qm','Track rename source')
                    case.base=git(case.root,'rev-parse','HEAD').stdout.strip()
                    (case.root/new).parent.mkdir(parents=True,exist_ok=True)
                    git(case.root,'mv',old,new)
                    case.edit_task(scope={'include':['.'],'exclude':[]});case.ready();case.review()
                    before=case.preserved()
                    with self.assertRaisesRegex(ValueError,'lifecycle record crosses a task source rename boundary'):
                        capture.capture(case.root,TASK)
                    self.assertEqual(case.preserved(),before)
                finally:
                    case.doCleanups()

    def test_full_lifecycle_and_readonly_terminal(self):
        self.assertEqual(w.load(self.root, TASK)['identity'], v.sha(TASK.encode()))
        self.assertEqual(w.select(self.root)[0]['path'], TASK)
        self.ready()
        self.assertEqual(w.load(self.root, TASK)['status'], 'active')
        self.review()
        manifest = capture.capture(self.root, TASK)
        before = self.preserved(); candidate = self.candidate()
        self.assertEqual(candidate['commit_gate_errors'], [])
        self.assertEqual(candidate['work_unit']['kind'], 'task')
        self.assertIsNone(candidate['epic']); self.assertIsNone(candidate['milestone'])
        self.assertIn('- Task: Demo task', candidate['message'])
        self.assertNotIn('- Milestone:', candidate['message'])
        self.assertEqual(self.preserved(), before)
        result = self.cli('check_reviewed_change_set', '--task', TASK)
        self.assertEqual(result.returncode, 2); self.assertIn('dirty', result.stderr)
        task_bytes = self.path.read_bytes()
        (self.root / 'scratch.txt').write_text('unrelated\n')
        result = self.commit(); self.assertEqual(result.returncode, 0, result.stderr)
        m = json.loads(manifest.read_text())
        self.assertEqual(git(self.root, 'rev-parse', 'HEAD^{tree}').stdout.strip(), m['review_tree'])
        self.assertEqual(git(self.root, 'show', 'HEAD:src/app.py').stdout, 'VALUE = 2\n')
        self.assertEqual(self.path.read_bytes(), task_bytes)
        self.assertTrue((self.root / 'scratch.txt').exists())
        before = self.preserved()
        result = self.cli('check_reviewed_change_set', '--task', TASK)
        self.assertEqual(result.returncode, 0, result.stderr)
        inspected = json.loads(self.cli('inspect_deepdone_state', '--task', TASK).stdout)
        self.assertTrue(inspected['task_review_complete'])
        self.assertTrue(inspected['task_integration']['committed_clean'])
        self.assertEqual(self.preserved(), before)
        self.assertFalse((self.root / 'notes').exists())
        with tempfile.TemporaryDirectory() as export:
            exported = Path(export) / 'app.py'
            exported.write_bytes(subprocess.check_output(['git', 'show', 'HEAD:src/app.py'], cwd=self.root))
            result = subprocess.run([sys.executable, '-I', '-B', '-c', "exec(open('app.py').read()); assert VALUE == 2"], cwd=export)
            self.assertEqual(result.returncode, 0)

    def test_strict_task_record_refusals(self):
        original = self.path.read_text()
        cases = [('goal', ''), ('scope', {'include': [], 'exclude': []}), ('acceptance', []),
                 ('schema', True), ('schema', 2), ('kind', 'epic'), ('id', 'different'), ('extra', 1),
                 ('constraints', [None]), ('acceptance', [{'check_id':'x','condition':''}]),
                 ('acceptance', [{'check_id':'x','condition':'x'}, {'check_id':'x','condition':'y'}]),
                 ('scope', {'include':['src', 'src/'],'exclude':[]})]
        for key,value in cases:
            with self.subTest(field=key,value=value):
                self.path.write_text(original); self.edit_task(**{key:value}); before=self.preserved()
                record, _, errors=w.select(self.root,task=TASK)
                self.assertIsNone(record); self.assertTrue(errors)
                self.assertTrue(self.candidate()['selection_errors'])
                self.assertEqual(self.preserved(), before)
        for heading in ('Task','Status','Review','Open Loops','Next Action','Verification Log'):
            with self.subTest(duplicate=heading):
                self.path.write_text(original+'\n## '+heading+'\n\nactive\n')
                self.assertRegex(w.select(self.root,task=TASK)[2][0]['reason'], 'exactly one')
        for text in (original.replace('"schema": 1', '"schema": 1, "schema": 1'),
                     original.replace('active\n','active\ncomplete\n'), original.replace('Implement and verify the task.', '')):
            self.path.write_text(text); self.assertTrue(w.select(self.root,task=TASK)[2])

    def test_acceptance_revision_preserves_history(self):
        self.ready()
        old = {p:p.read_bytes() for p in (self.root / v.namespace(TASK)).rglob('*.json')}
        for checks, reason in [([{**self.check,'id':'missing'}], 'requires current required'),
                               ([{**self.check,'required':False}, {**self.check,'id':'extra'}], 'requires current required'),
                               ([{**self.check,'acceptance':'different'}], 'condition mismatch')]:
            with self.subTest(reason=reason):
                before=self.preserved()
                with self.assertRaisesRegex(ValueError,reason): v.initialize(self.root,TASK,checks,'bad')
                self.assertEqual(before,self.preserved())
        self.edit_task(acceptance=[{'check_id':'app','condition':'Revised observable value'}])
        self.assertIn('condition mismatch', ';'.join(v.validate(self.root,TASK)))
        self.review()
        with self.assertRaisesRegex(ValueError,'condition mismatch'): capture.capture(self.root,TASK)
        self.assertIn('condition mismatch',';'.join(self.candidate()['commit_gate_errors']))
        self.check['acceptance']='Revised observable value'
        v.initialize(self.root,TASK,[self.check],'Explicit requirement revision')
        self.assertIn('missing readiness',';'.join(v.validate(self.root,TASK)))
        self.assertEqual(v.run_check(self.root,TASK,'app')['exit_code'],0)
        self.assertEqual(v.validate(self.root,TASK),[])
        self.assertTrue(all(p.read_bytes()==b for p,b in old.items()))
        capture.capture(self.root,TASK)
        self.assertEqual(self.candidate()['commit_gate_errors'],[])

    def test_scope_binding_and_unrelated_roadmap(self):
        epic=self.root/'notes/epics/other.md'; epic.parent.mkdir(parents=True)
        epic.write_text('# Other\n\n## Status\n\nactive\n')
        roadmap=self.root/'notes/roadmap.md'; roadmap.write_text('# Roadmap\n\n## Active Epic\n\n- ledger: notes/epics/other.md\n- state: active\n')
        prior=(epic.read_bytes(),roadmap.read_bytes())
        self.edit_task(scope={'include':['src/app.py','src/unused'],'exclude':[]})
        self.ready(); self.review()
        self.path.write_text(self.path.read_text().replace('      - src/app.py\n      - src/unused','      - src/unused\n      - src/app.py'))
        manifest=capture.capture(self.root,TASK)
        self.assertEqual([e['role'] for e in json.loads(manifest.read_text())['evidence']],['ledger'])
        self.assertEqual(self.candidate()['commit_gate_errors'],[])
        for replacement in ('src', 'src/app.py\n      - src/app.py'):
            text=self.path.read_text(); self.path.write_text(text.replace('      - src/unused', '      - '+replacement))
            self.assertRegex(';'.join(self.candidate()['commit_gate_errors']), 'task Review scope|duplicate task scope')
            self.path.write_text(text)
        self.assertEqual(self.commit().returncode,0)
        self.assertEqual(terminal.check(self.root,TASK)[0],[])
        self.assertEqual((epic.read_bytes(),roadmap.read_bytes()),prior)
        with self.assertRaisesRegex(ValueError,'roadmap association'): v.initialize(self.root,TASK,[self.check],'bad','notes/roadmap.md')

    def test_selection_ambiguity_explicit_errors_and_completed_history(self):
        other=self.path.with_name('other.md'); other.write_text(task_text('other'))
        selected,_,errors=w.select(self.root); self.assertIsNone(selected)
        self.assertEqual(errors[0]['paths'],[TASK,'.deepdone/tasks/other.md'])
        self.assertEqual(w.select(self.root,task=TASK)[0]['id'],'demo')
        other.write_text(other.read_text().replace('\nactive\n','\nblocked\n'))
        self.assertTrue(w.select(self.root)[2])
        other.write_text(other.read_text().replace('\nblocked\n','\ncomplete\n'))
        self.assertEqual(w.select(self.root)[0]['id'],'demo')
        self.path.write_text(self.path.read_text().replace('\nactive\n','\ncomplete\n'))
        self.assertEqual(w.select(self.root),(None,'none',[]))
        (self.root/'src/app.py').unlink()
        self.assertEqual(w.select(self.root),(None,'none',[]))
        self.assertEqual(w.select(self.root,task=TASK)[0]['id'],'demo')
        data=json.loads(self.cli('inspect_deepdone_state').stdout)
        self.assertIsNone(data['work_unit']); self.assertIsNone(data['task_integration'])
        self.assertIn('dirty_git_without_active_ledger',data['warnings'])
        for path in ('', '.deepdone/tasks/missing.md','../escape.md','notes/epics/demo.md','.deepdone/tasks/../tasks/demo.md'):
            self.assertTrue(w.select(self.root,task=path)[2])
        self.assertTrue(w.select(self.root,ledger=TASK)[2])
        self.path.unlink(); self.path.symlink_to(other)
        self.assertRegex(w.select(self.root,task=TASK)[2][0]['reason'],'symlink')

    def test_task_epic_conflict_and_broken_roadmap(self):
        epic=self.root/'notes/epics/other.md'; epic.parent.mkdir(parents=True)
        epic.write_text('# Other\n\n## Status\n\nactive\n')
        self.assertIn('ambiguous',w.select(self.root)[2][0]['reason'])
        self.assertEqual(w.select(self.root,ledger='notes/epics/other.md')[0]['kind'],'epic')
        roadmap=self.root/'notes/roadmap.md'; roadmap.write_text('## Active Epic\n\n- ledger: notes/epics/missing.md\n')
        self.assertTrue(w.select(self.root)[2])
        self.assertEqual(w.select(self.root,task=TASK)[0]['id'],'demo')
        roadmap.unlink(); epic.write_text('malformed')
        self.assertTrue(w.select(self.root)[2])
        self.assertEqual(w.select(self.root,task=TASK)[0]['path'],TASK)

    def test_cli_selectors_and_planning_readiness(self):
        data=json.loads(self.cli('inspect_deepdone_state',str(self.root),'--task',TASK).stdout)
        self.assertEqual(data['work_unit']['id'],'demo'); self.assertEqual(data['selection_errors'],[])
        self.assertIn('missing verification contract',';'.join(data['readiness_errors']))
        for script,prefix in [('verification',['check']),('capture_reviewed_change_set',[]),('commit_progress',[]),('check_reviewed_change_set',[]),('inspect_deepdone_state',[])]:
            with self.subTest(script=script):
                result=self.cli(script,*prefix,'--task',TASK,'--ledger','notes/epics/no.md')
                self.assertEqual(result.returncode,2)
                result=self.cli(script,*prefix,'--ledger',TASK)
                self.assertIn('selector cannot select task',result.stdout+result.stderr)
                result=self.cli(script,*prefix,'--task','')
                self.assertIn('invalid work-unit path',result.stdout+result.stderr)
        inventory=self.root/'.deepdone/inventory.json'; inventory.write_text(json.dumps([self.check]))
        result=self.cli('verification','init','--task',TASK,'--inventory',str(inventory),'--reason','initial')
        self.assertEqual(result.returncode,0,result.stdout)
        self.assertEqual(self.cli('verification','run','--task',TASK,'--check-id','app').returncode,0)
        self.review()
        self.assertEqual(self.cli('capture_reviewed_change_set','--task',TASK).returncode,0)
        self.assertEqual(self.candidate()['commit_gate_errors'],[])

    def test_identity_substitution_and_no_legacy_task_fallback(self):
        self.capture()
        original=self.path.read_text()
        other=self.path.with_name('other.md'); other.write_text(original.replace('"id": "demo"','"id": "other"'))
        self.assertIn('mismatch',';'.join(v.validate(self.root,'.deepdone/tasks/other.md')))
        for text in (re.sub(r'## Task\n.*?(?=## Verification Log)', '', original, flags=re.S),
                     re.sub(r'## Verification Contract\n.*', '', original, flags=re.S)):
            self.path.write_text(text)
            with self.assertRaisesRegex(ValueError,'Task|verification contract|development evidence changed'): terminal.check(self.root,TASK)
        self.path.write_text(original)
        manifest=self.root/'.deepdone/reviews/task-demo-0001.json'
        data=json.loads(manifest.read_text()); data['ledger_path']='.deepdone/tasks/other.md';manifest.write_text(json.dumps(data))
        self.assertIn('ledger does not match',';'.join(self.candidate()['commit_gate_errors']))
        self.assertEqual(v.unit('notes/epics/demo.md'),v.sha(b'notes/epics/demo.md'))

    def test_readiness_and_staleness_reach_consumers(self):
        self.capture()
        original=self.path.read_text()
        contract=v.read_contract(original,TASK)
        receipt_path=self.root/contract['attempts'][-1]['receipt']['path']
        raw=receipt_path.read_bytes()
        for variant in ('corrupt','pending','missing','diagnostic','failed','stale'):
            with self.subTest(variant=variant):
                self.path.write_text(original);receipt_path.write_bytes(raw)
                (self.root/'src/app.py').write_text('VALUE = 2\n')
                c=copy.deepcopy(contract)
                if variant=='corrupt': receipt_path.write_bytes(raw+b' ')
                if variant=='pending': c['attempts'][-1]['status']='pending';c['attempts'][-1]['receipt']=None
                if variant=='missing': c['attempts']=[]
                if variant=='diagnostic':
                    c['attempts']=[]
                    self.path.write_text(v.render_contract(original,c));v.run_check(self.root,TASK,'app','diagnostic')
                elif variant=='failed':
                    (self.root/'src/app.py').write_text('VALUE = 1\n');v.run_check(self.root,TASK,'app')
                elif variant=='stale': (self.root/'src/app.py').write_text('VALUE = 3\n')
                else: self.path.write_text(v.render_contract(original,c))
                before=self.preserved()
                self.assertTrue(v.validate(self.root,TASK))
                self.assertTrue(self.candidate()['commit_gate_errors'])
                self.assertEqual(self.commit().returncode,2)
                self.assertEqual(self.cli('check_reviewed_change_set','--task',TASK).returncode,2)
                self.assertEqual(self.preserved(),before)

    def test_staged_evidence_authority_stop_and_cleanup(self):
        manifest=self.capture();before=self.preserved()
        no_authority=self.cli('commit_progress','--task',TASK,'--commit')
        self.assertEqual(no_authority.returncode,2);self.assertIn('authorization',no_authority.stderr)
        self.assertEqual(self.preserved(),before)
        for path in (TASK,manifest.relative_to(self.root).as_posix()):
            git(self.root,'add','-f','--',path);before=self.preserved()
            self.assertIn(path,self.candidate()['staged_unowned_files'])
            self.assertEqual(self.commit().returncode,2);self.assertEqual(self.preserved(),before)
            git(self.root,'reset','-q','--',path)
        (self.root/'.deepdone/STOP').touch();before=self.preserved()
        self.assertEqual(self.commit().returncode,2)
        self.assertEqual(self.cli('verification','run','--task',TASK,'--check-id','app').returncode,2)
        self.assertEqual(self.preserved(),before);(self.root/'.deepdone/STOP').unlink()
        self.assertEqual(self.commit().returncode,0);before=self.preserved()
        result=self.cli('check_reviewed_change_set','--task',TASK,'--cleanup-after-advance')
        self.assertEqual(result.returncode,2);self.assertIn('unsupported',result.stderr)
        self.assertEqual(self.preserved(),before)

    def test_whole_repo_task_evidence_is_narrow(self):
        check={**self.check,'inputs':[{'path':'.','role':'source'}]}
        baseline=v.fingerprint(self.root,'notes/epics/old.md',check,None)
        self.path.unlink();self.path.parent.rmdir()
        self.assertEqual(v.fingerprint(self.root,'notes/epics/old.md',check,None),baseline)
        self.path.parent.mkdir();self.path.write_text(task_text())
        sibling=self.path.parent/'source.py';sibling.write_text('VALUE = 1\n')
        self.assertNotEqual(v.fingerprint(self.root,TASK,check,None),baseline)
        sibling.unlink()
        empty=self.path.parent/'ordinary';empty.mkdir()
        current=v.fingerprint(self.root,TASK,check,None)
        self.assertIn('.deepdone/tasks/ordinary',v.source_directories(self.root,TASK,None,check,current))
        empty.rmdir()
        designated={**check,'inputs':[{'path':'.deepdone/tasks','role':'source'},{'path':'src','role':'source'}]}
        current=v.fingerprint(self.root,TASK,designated,None)
        self.assertIn('.deepdone/tasks',v.source_directories(self.root,TASK,None,designated,current))
        self.check=check;self.capture()
        self.assertEqual(self.candidate()['commit_gate_errors'],[])

    def test_source_and_context_drift_after_exact_commit(self):
        work=self.root/'work';work.mkdir()
        self.check['cwd']='work';self.check['argv'][-1]="exec(open('../src/app.py').read()); assert VALUE == 2"
        self.capture();self.assertEqual(self.commit().returncode,0)
        original=self.path.read_bytes()
        for variant in ('record','source','cwd'):
            with self.subTest(variant=variant):
                self.path.write_bytes(original);(self.root/'src/app.py').write_text('VALUE = 2\n')
                work.mkdir(exist_ok=True)
                if variant=='record': self.edit_task(goal='Changed goal')
                if variant=='source': (self.root/'src/app.py').write_text('VALUE = 9\n')
                if variant=='cwd': work.rmdir()
                before=self.preserved()
                result=self.cli('check_reviewed_change_set','--task',TASK)
                self.assertEqual(result.returncode,2)
                self.assertRegex(result.stderr,'evidence changed|stale|invalid cwd')
                self.assertEqual(self.preserved(),before)

    def test_required_empty_directory_and_unowned_source(self):
        for variant in ('directory','ignored','mode'):
            with self.subTest(variant=variant):
                self.setUp()
                if variant=='directory': (self.root/'src/required').mkdir()
                if variant=='ignored':
                    (self.root/'.git/info/exclude').write_text('src/hidden.py\n');(self.root/'src/hidden.py').write_text('X=1\n')
                if variant=='mode':
                    git(self.root,'config','core.fileMode','false');(self.root/'src/app.py').chmod(0o755)
                self.ready();self.review();before=self.preserved()
                with self.assertRaisesRegex(ValueError,'source directory|outside reviewed ownership|source.*tree|ignored source input'):
                    capture.capture(self.root,TASK)
                self.assertEqual(self.preserved(),before)

    def test_unignored_task_and_sidecars_are_not_owned(self):
        # Removing ignores is fixture setup, committed before task execution.
        (self.root/'.gitignore').write_text('notes/epics/\nnotes/roadmap.md\n')
        git(self.root,'add','.gitignore');git(self.root,'commit','-qm','unignored evidence fixture')
        self.base=git(self.root,'rev-parse','HEAD').stdout.strip()
        self.edit_task(scope={'include':['.'],'exclude':[]})
        other=self.path.with_name('other.md');other.write_text(task_text('other'))
        self.check['inputs']=[{'path':'.','role':'source'}]
        manifest=self.capture();m=json.loads(manifest.read_text())
        self.assertEqual(capture.changed_paths(self.root,self.base,m['review_commit']),{'src/app.py'})
        candidate=self.candidate();self.assertEqual(candidate['commit_gate_errors'],[])
        self.assertTrue({TASK,'.deepdone/tasks/other.md'}.issubset({f['path'] for f in candidate['excluded_local_files']}))
        self.assertEqual(self.commit().returncode,0)
        self.assertEqual(terminal.check(self.root,TASK)[0],[])

    def test_new_task_does_not_reopen_completed_task(self):
        manifest=self.capture();self.assertEqual(self.commit().returncode,0)
        original=self.path.read_bytes();m=json.loads(manifest.read_text());receipt_files={p:p.read_bytes() for p in (self.root/v.namespace(TASK)).rglob('*.json')}
        # New work overlaps old source; discovery must not revalidate old receipts.
        (self.root/'src/app.py').write_text('VALUE = 3\n')
        other=self.path.with_name('other.md');other.write_text(task_text('other'))
        selected,_,errors=w.select(self.root)
        self.assertEqual(errors,[]);self.assertEqual(selected['id'],'other')
        check={**self.check,'argv':self.check['argv'][:-1]+["exec(open('src/app.py').read()); assert VALUE == 3"]}
        v.initialize(self.root,'.deepdone/tasks/other.md',[check],'new independent task')
        self.assertEqual(v.run_check(self.root,'.deepdone/tasks/other.md','app')['exit_code'],0)
        self.assertEqual(v.validate(self.root,'.deepdone/tasks/other.md'),[])
        inspected=json.loads(self.cli('inspect_deepdone_state').stdout)
        self.assertEqual(inspected['work_unit']['id'],'other');self.assertEqual(inspected['readiness_errors'],[])
        self.assertEqual(self.path.read_bytes(),original)
        self.assertTrue(all(p.read_bytes()==raw for p,raw in receipt_files.items()))
        self.assertEqual(capture.ref_oid(self.root,m['review_ref']),m['review_commit'])
        self.assertIn('stale',';'.join(v.validate(self.root,TASK)))

    def test_invalid_cwd_at_independent_task_consumers(self):
        work=self.root/'work';work.mkdir()
        self.check['cwd']='work';self.check['argv'][-1]="exec(open('../src/app.py').read()); assert VALUE == 2"
        self.capture();work.rmdir();before=self.preserved()
        self.assertIn('invalid cwd',';'.join(v.validate(self.root,TASK)))
        with self.assertRaisesRegex(ValueError,'invalid cwd'): capture.capture(self.root,TASK)
        self.assertIn('invalid cwd',';'.join(self.candidate()['commit_gate_errors']))
        result=self.commit();self.assertEqual(result.returncode,2);self.assertIn('invalid cwd',result.stderr)
        result=self.cli('check_reviewed_change_set','--task',TASK)
        self.assertEqual(result.returncode,2);self.assertIn('invalid cwd',result.stderr)
        self.assertEqual(self.preserved(),before)
        work.mkdir();self.assertEqual(self.commit().returncode,0)
        work.rmdir();before=self.preserved()
        self.assertIn('invalid cwd',self.cli('check_reviewed_change_set','--task',TASK).stderr)
        self.assertEqual(self.preserved(),before)

    def test_first_task_container_during_whole_repo_execution(self):
        self.path.unlink();self.path.parent.rmdir()
        (self.root/'notes/epics').mkdir(parents=True)
        self.fixture.write_passing_ledger(self.root,self.base,['src/'])
        check={**self.check,'inputs':[{'path':'.','role':'source'}],
               'argv':self.check['argv'][:-1]+["from pathlib import Path; exec(open('src/app.py').read()); assert VALUE == 2; Path('.deepdone/tasks').mkdir(); Path('.deepdone/tasks/new.md').write_text("+repr(task_text('new'))+")"]}
        ledger='notes/epics/demo.md'
        v.initialize(self.root,ledger,[check],'whole-repository evidence-container fixture')
        receipt=v.run_check(self.root,ledger,'app')
        self.assertEqual(receipt['exit_code'],0)
        self.assertEqual(receipt['before'],receipt['after'])
        self.assertEqual(v.validate(self.root,ledger),[])
        capture.capture(self.root,ledger)

    def test_explicit_task_container_needs_real_source_descendant(self):
        self.check['inputs']=[{'path':'src','role':'source'},{'path':'.deepdone/tasks','role':'source'}]
        self.ready();self.review()
        with self.assertRaisesRegex(ValueError,'source directory not materialized'): capture.capture(self.root,TASK)
        marker=self.path.parent/'.keep';marker.write_text('source marker\n')
        git(self.root,'add','-f',marker.relative_to(self.root).as_posix())
        git(self.root,'commit','-qm','unchanged source dependency fixture')
        self.base=git(self.root,'rev-parse','HEAD').stdout.strip()
        self.ready();self.review();capture.capture(self.root,TASK)
        self.assertEqual(self.candidate()['commit_gate_errors'],[])
        self.assertEqual(self.commit().returncode,0)
        self.assertEqual(terminal.check(self.root,TASK)[0],[])

    def test_legacy_epic_discovery_keeps_status_and_review_forms(self):
        self.path.write_text(self.path.read_text().replace('\nactive\n','\ncomplete\n'))
        epic=self.root/'notes/epics/other.md';epic.parent.mkdir(parents=True)
        for status in ('active','- [ ] active','- state: in progress'):
            epic.write_text('# Epic\n\n## Status\n\n'+status+'\n')
            self.assertEqual(w.select(self.root)[0]['status'],'active')
        for review in ('## Review\n\n- reviewed-at: now\n  result: pass',
                       '## Review\n\n- review-result: pass',
                       '## Decisions\n\n- review-result: pass'):
            epic.write_text('# Epic\n\n'+review+'\n\n## Status\n\ncomplete\n')
            self.assertEqual(w.select(self.root)[1],'reviewed-complete-fallback')
