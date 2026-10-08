from __future__ import annotations

import base64
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_reviewed_change_set as snapshot_tests
from test_reviewed_change_set import git, ROOT
sys.path.insert(0, str(ROOT / 'skills/deepdone/scripts'))
import verification as v
import capture_reviewed_change_set as capture
import check_reviewed_change_set as advance

LEDGER = 'notes/epics/demo.md'


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.fixture = snapshot_tests.ReviewedChangeSetTests()
        head = self.fixture.init_repo(self.root)
        (self.root / 'src/app.py').write_text('VALUE = 2\n')
        self.fixture.write_passing_ledger(self.root, head, ['src/'])
        self.check = {
            'id': 'app', 'acceptance': 'Application has expected value', 'required': True,
            'argv': [sys.executable, '-I', '-B', '-c', "exec(open('src/app.py').read()); assert VALUE == 2"],
            'cwd': '.', 'inputs': [{'path': 'src', 'role': 'source'}],
            'exclusions': [], 'env': {}, 'context': 'local-files', 'timeout': 5,
        }

    def init(self, checks=None):
        v.initialize(self.root, LEDGER, checks or [self.check], 'Explicit test migration/revision')

    def run_check(self, purpose='readiness', check_id='app'):
        return v.run_check(self.root, LEDGER, check_id, purpose)

    def ready(self):
        self.init()
        self.assertEqual(self.run_check()['exit_code'], 0)
        self.assertEqual(v.validate(self.root, LEDGER), [])

    def contract(self):
        return v.read_contract((self.root / LEDGER).read_text(), LEDGER)

    def save(self, contract):
        path = self.root / LEDGER
        path.write_text(v.render_contract(path.read_text(), contract))

    def errors(self, fragment, **kwargs):
        errors = v.validate(self.root, LEDGER, **kwargs)
        self.assertTrue(any(fragment in e for e in errors), errors)

    def test_current_inventory_purposes_and_latest_attempt(self):
        self.init()
        self.errors('missing readiness')
        self.run_check('feedback')
        self.run_check('diagnostic')
        self.errors('missing readiness')
        (self.root / 'src/app.py').write_text('VALUE = 1\n')
        self.assertEqual(self.run_check()['exit_code'], 1)
        self.errors('exit 1')
        (self.root / 'src/app.py').write_text('VALUE = 2\n')
        self.run_check()
        self.assertEqual(v.validate(self.root, LEDGER), [])
        (self.root / 'src/app.py').write_text('VALUE = 1\n')
        self.run_check()
        self.errors('exit 1')
        (self.root / 'src/app.py').write_text('VALUE = 2\n')
        self.errors('exit 1')
        self.assertEqual(len(self.contract()['attempts']), 5)
        other = {**self.check, 'id': 'syntax', 'argv': [sys.executable, '-c', "compile(open('src/app.py').read(), 'app', 'exec')"]}
        self.init([self.check, other])
        self.assertEqual(self.run_check(check_id='syntax')['exit_code'], 0)
        self.errors('app: latest readiness')

    def test_revisions_reuse_only_unchanged_definition(self):
        self.ready()
        other = {**self.check, 'id': 'other'}
        self.init([self.check, other])
        self.errors('other: missing readiness')
        self.run_check(check_id='other')
        self.assertEqual(v.validate(self.root, LEDGER), [])
        failed = {**other, 'argv': [sys.executable, '-I', '-c', 'raise SystemExit(4)'], 'required': False}
        self.init([self.check, failed])
        self.run_check(check_id='other')
        self.assertEqual(self.run_check('diagnostic', 'other')['exit_code'], 4)
        self.assertEqual(v.validate(self.root, LEDGER), [])
        (self.root / 'src/app.py').write_text('VALUE = 1\n')
        self.run_check()
        self.run_check('diagnostic', 'other')
        self.errors('app: latest readiness')
        for field, value in [('argv', ['true']), ('cwd', 'src'), ('env', {'X': '1'}),
                             ('inputs', [{'path': 'src/app.py', 'role': 'source'}]),
                             ('exclusions', [{'path': 'src/cache', 'reason': 'generated'}])]:
            with self.subTest(field=field):
                revised = {**self.check, field: value}
                self.assertNotEqual(v.definition(revised), v.definition(self.check))
                self.init([revised])
                self.errors('missing readiness')
        with self.assertRaisesRegex(ValueError, 'unsupported execution context'):
            v.definition({**self.check, 'context': 'remote'})
        for checks in ([], [{**self.check, 'required': False}], [self.check, self.check]):
            with self.assertRaises(ValueError):
                v.initialize(self.root, LEDGER, checks, 'invalid')

    def test_pending_conflict_abandon_and_competing_writer(self):
        self.ready()
        original = v.stream_command
        def conflict(root, check):
            self.assertEqual(self.contract()['attempts'][-1]['status'], 'pending')
            self.errors('pending')
            with self.assertRaisesRegex(ValueError, 'already active'):
                self.run_check()
            result = original(root, check)
            path = root / LEDGER
            path.write_text(path.read_text().replace('# Demo', '# Demo\nConcurrent user edit', 1))
            return result
        with patch.object(v, 'stream_command', side_effect=conflict):
            with self.assertRaisesRegex(ValueError, 'changed concurrently'):
                self.run_check()
        self.assertIn('Concurrent user edit', (self.root / LEDGER).read_text())
        self.errors('pending')
        pending = self.contract()['attempts'][-1]
        v.abandon(self.root, LEDGER, pending['id'], 'Runner lost finalization race')
        self.errors('abandoned')
        self.run_check()
        self.assertEqual(v.validate(self.root, LEDGER), [])
        self.assertGreater(len(list((self.root / v.namespace(LEDGER) / 'receipts').glob('*.json'))), len(self.contract()['attempts']))

    def test_interrupted_write_does_not_restore_older_pass(self):
        self.ready()
        with patch.object(v, 'immutable', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError, 'disk full'):
                self.run_check()
        self.errors('pending')
        pending = self.contract()['attempts'][-1]
        v.abandon(self.root, LEDGER, pending['id'], 'Incomplete receipt write')
        self.errors('abandoned')

    def test_raw_outcomes_and_binary_stream(self):
        cases = [
            ([sys.executable, '-c', 'raise SystemExit(7)'], 'completed', 7),
            ([sys.executable, '-c', 'import time; time.sleep(1)'], 'timeout', None),
            (['/nonexistent/deepdone-program'], 'spawn-error', None),
            ([sys.executable, '-c', "import os; os.write(1, b'\\xff'*20000)"], 'completed', 0),
            ([sys.executable, '-c', "import os; os.write(1, b'x'*10000000)"], 'output-limit', None),
        ]
        for argv, outcome, code in cases:
            with self.subTest(outcome=outcome, argv=argv):
                self.check['argv'] = argv
                self.check['timeout'] = .1 if outcome == 'timeout' else 5
                self.init()
                receipt = self.run_check()
                self.assertEqual(receipt['outcome'], outcome, receipt)
                if code is not None:
                    self.assertEqual(receipt['exit_code'], code)
                if outcome == 'completed' and code == 0:
                    stream = receipt['output']['stdout']
                    self.assertEqual(stream['bytes'], 20000)
                    self.assertEqual(stream['sha256'], v.sha(b'\xff'*20000))
                    self.assertTrue(stream['truncated'])
                    self.assertEqual(len(base64.b64decode(stream['excerpt'])), v.EXCERPT_LIMIT)
        self.check['inputs'] = [{'path': 'missing', 'role': 'source'}]
        self.init()
        receipt = self.run_check()
        self.assertEqual(receipt['outcome'], 'capture-error')
        self.errors('capture-error')

    def test_check_mutations_preserve_work_but_do_not_pass(self):
        for program, error in [
            ("open('src/app.py','w').write('VALUE = 3\\n')", 'inputs changed'),
            ("import subprocess; subprocess.run(['git','add','src/app.py'],check=True)", 'HEAD or real index'),
            ("import subprocess; subprocess.run(['git','commit','-qam','check mutation'],check=True)", 'HEAD or real index'),
        ]:
            with self.subTest(program=program):
                (self.root / 'src/app.py').write_text('VALUE = 2\n')
                self.check['argv'] = [sys.executable, '-c', program]
                self.init()
                self.run_check()
                self.errors(error)
        self.assertEqual(git(self.root, 'log', '-1', '--format=%s').stdout.strip(), 'check mutation')

    def test_reenumeration_modes_and_latest_stale_not_older_match(self):
        self.check['argv'] = [sys.executable, '-c', "compile(open('src/app.py').read(), 'app', 'exec')"]
        self.ready()
        app = self.root / 'src/app.py'
        for mutation, undo in [
            (lambda: app.write_text('VALUE = 3\n'), lambda: app.write_text('VALUE = 2\n')),
            (lambda: (self.root / 'src/new.py').write_text('X=1'), lambda: (self.root / 'src/new.py').unlink()),
            (lambda: app.chmod(0o755), lambda: app.chmod(0o644)),
            (lambda: app.rename(self.root / 'src/moved.py'), lambda: (self.root / 'src/moved.py').rename(app)),
            (lambda: app.unlink(), lambda: app.write_text('VALUE = 2\n')),
        ]:
            mutation()
            self.assertTrue(v.validate(self.root, LEDGER))
            undo()
            self.assertEqual(v.validate(self.root, LEDGER), [])
        app.write_text('VALUE = 3\n')
        self.run_check()
        app.write_text('VALUE = 2\n')
        self.errors('stale')

    def test_declared_test_fixture_wrapper_and_config_changes(self):
        paths = ['tests/case.py', 'fixtures/data.json', 'scripts/check.py', 'config/settings.json']
        for rel in paths:
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('initial')
            self.check['inputs'].append({'path': str(path.parent.relative_to(self.root)), 'role': 'source'})
        self.ready()
        for rel in paths:
            with self.subTest(path=rel):
                path = self.root / rel
                path.write_text('changed')
                self.errors('stale')
                path.write_text('initial')
                self.assertEqual(v.validate(self.root, LEDGER), [])

    def test_narrow_scope_ignored_data_and_ownership(self):
        self.ready()
        (self.root / 'scratch').write_text('unrelated')
        self.assertEqual(v.validate(self.root, LEDGER, owned={'src/app.py'}), [])
        self.errors('outside reviewed ownership', owned=set())
        (self.root / 'src/new.py').write_text('VALUE=3')
        self.run_check()
        self.errors('outside reviewed ownership', owned={'src/app.py'})
        with (self.root / '.gitignore').open('a') as stream:
            stream.write('src/data.json\n')
        (self.root / 'src/data.json').write_text('{}')
        self.run_check()
        self.errors('ignored source', owned={'src/app.py', 'src/new.py'})
        self.check['inputs'] = [{'path': 'src/app.py', 'role': 'source'}, {'path': 'src/data.json', 'role': 'local-data'}]
        self.init()
        self.run_check()
        self.assertEqual(v.validate(self.root, LEDGER, owned={'src/app.py'}), [])
        (self.root / 'src/data.json').write_text('{"changed":true}')
        self.errors('stale')

    def test_exclusions_evidence_and_ordinary_notes(self):
        (self.root / 'notes/context.md').write_text('context')
        (self.root / 'notes/roadmap.md').write_text('roadmap')
        (self.root / 'src/cache').mkdir()
        self.check['inputs'] = [{'path': '.', 'role': 'source'}, {'path': 'src/app.py', 'role': 'source'}]
        self.check['exclusions'] = [{'path': 'src/cache', 'reason': 'generated disposable cache'}]
        self.check['argv'] = [sys.executable, '-c', "open('src/cache/output','w').write('generated')"]
        v.initialize(self.root, LEDGER, [self.check], 'explicit scope', 'notes/roadmap.md')
        self.run_check()
        self.assertEqual(v.validate(self.root, LEDGER), [])
        (self.root / 'notes/roadmap.md').write_text('advanced')
        # Existing evidence directories remain stable; only recognized files are excluded.
        (self.root / '.deepdone/commit-candidate.md').write_text('candidate')
        self.assertEqual(v.validate(self.root, LEDGER), [])
        (self.root / '.deepdone/reviews').mkdir()
        (self.root / '.deepdone/reviews/example.json').write_text('{}')
        self.assertEqual(v.validate(self.root, LEDGER), [])
        (self.root / '.deepdone/context').write_text('ordinary input')
        self.errors('stale')
        (self.root / '.deepdone/context').unlink()
        (self.root / 'notes/context.md').write_text('changed')
        self.errors('stale')
        for path in ('src', 'src/app.py'):
            with self.assertRaisesRegex(ValueError, 'designated input'):
                v.definition({**self.check, 'exclusions': [{'path': path, 'reason': 'not allowed'}]})

    def test_unsupported_inputs_and_paths(self):
        self.init()
        app = self.root / 'src/app.py'
        app.unlink()
        os.symlink('../.gitignore', app)
        self.assertEqual(self.run_check()['outcome'], 'capture-error')
        self.errors('capture-error')
        app.unlink()
        os.mkfifo(app)
        self.assertEqual(self.run_check()['outcome'], 'capture-error')
        app.unlink()
        app.write_text('VALUE = 2\n')
        head = git(self.root, 'rev-parse', 'HEAD').stdout.strip()
        git(self.root, 'update-index', '--add', '--cacheinfo', f'160000,{head},src/module')
        (self.root / 'src/module').mkdir()
        self.assertIn('submodule', self.run_check()['error'])
        for path in ('../escape', '/absolute', './src', 'src/../src'):
            with self.assertRaises(ValueError):
                v.definition({**self.check, 'inputs': [{'path': path, 'role': 'source'}]})

    def test_contract_integrity_and_attempt_binding(self):
        self.ready()
        original = (self.root / LEDGER).read_text()
        for change in [
            lambda c: c.update(schema=2),
            lambda c: c.update(attempts={}),
            lambda c: c.update(inventories=[]),
            lambda c: c['inventories'][0].update(path='../escape'),
            lambda c: c['attempts'][0].update(sequence=2),
            lambda c: c['attempts'][0].update(id='0'*32),
            lambda c: c['attempts'][0].update(check='other'),
            lambda c: c['attempts'][0].update(definition='0'*64),
            lambda c: c['attempts'][0].update(purpose='feedback'),
            lambda c: c.update(ledger='notes/epics/other.md'),
            lambda c: c.update(work_unit='0'*64),
        ]:
            with self.subTest(change=change):
                (self.root / LEDGER).write_text(original)
                contract = self.contract()
                change(contract)
                self.save(contract)
                self.errors('verification contract')
        (self.root / LEDGER).write_text(original.replace('"schema": 1', '"schema": 1, "schema": 1', 1))
        self.errors('duplicate JSON key')
        (self.root / LEDGER).write_text(original)
        receipt = self.root / self.contract()['attempts'][0]['receipt']['path']
        receipt.unlink()
        self.errors('unreadable evidence')

    def test_artifact_shapes_diagnostic_integrity_and_interruption(self):
        self.ready()
        self.run_check('diagnostic')
        original = (self.root / LEDGER).read_text()
        original_contract = self.contract()
        reference = original_contract['attempts'][-1]['receipt']
        receipt = v.artifact(self.root, LEDGER, reference, 'receipts')
        malformed = [None, [], {**receipt, 'schema': True}, {**receipt, 'extra': 1},
                     {**receipt, 'output': {'stdout': None, 'stderr': None}},
                     {**receipt, 'before': {'entries': [], 'sha256': '0'*64}},
                     {**receipt, 'started': 'not a timestamp'},
                     {**receipt, 'exit_code': True}]
        for value in malformed:
            with self.subTest(value=value):
                contract = copy.deepcopy(original_contract)
                contract['attempts'][-1]['receipt'] = v.immutable(self.root, LEDGER, 'receipts', value)
                self.save(contract)
                self.errors('verification contract')
        (self.root / LEDGER).write_text(original)
        with patch.object(v.subprocess, 'Popen', side_effect=KeyboardInterrupt):
            outcome, code, output, _ = v.stream_command(self.root, self.check)
        self.assertEqual(outcome, 'interrupted')
        self.assertIsNone(code)
        self.assertFalse(output['stdout']['complete'])
        with patch.object(Path, 'read_bytes', side_effect=PermissionError('unreadable')):
            self.errors('unreadable')
        with patch.object(v.json, 'loads', side_effect=RecursionError), self.assertRaisesRegex(ValueError, 'nesting'):
            v.decode('[]')

    def test_inventory_conflict_preserves_pending_and_artifacts(self):
        self.ready()
        reference = self.contract()['inventories'][-1]
        path = self.root / reference['path']
        raw = path.read_bytes()
        original = v.stream_command
        def change_inventory(root, check):
            result = original(root, check)
            path.write_bytes(raw + b' ')
            return result
        with patch.object(v, 'stream_command', side_effect=change_inventory):
            with self.assertRaisesRegex(ValueError, 'artifact digest mismatch'):
                self.run_check()
        self.assertEqual(self.contract()['attempts'][-1]['status'], 'pending')
        self.assertEqual(path.read_bytes(), raw + b' ')
        path.write_bytes(raw)
        self.errors('pending')

    def test_capture_ownership_base_dependencies_and_legacy_advance(self):
        dependency = self.root / 'src/base.py'
        dependency.write_text('BASE=1')
        git(self.root, 'add', 'src/base.py')
        git(self.root, 'commit', '-qm', 'base dependency')
        head = git(self.root, 'rev-parse', 'HEAD').stdout.strip()
        self.fixture.write_passing_ledger(self.root, head, ['src/app.py'])
        self.ready()
        manifest = capture.capture(self.root, LEDGER)
        dependency.write_text('BASE=2')
        self.run_check()
        index = v.git_context(self.root)
        with self.assertRaisesRegex(ValueError, 'outside reviewed ownership'):
            capture.capture(self.root, LEDGER)
        result = self.fixture.run_commit(self.root, manifest)
        self.assertIn('outside reviewed ownership', result.stderr)
        self.assertEqual(v.git_context(self.root), index)
        dependency.write_text('BASE=1')
        self.run_check()
        manifest = capture.capture(self.root, LEDGER)
        result = self.fixture.run_commit(self.root, manifest)
        self.assertEqual(result.returncode, 0, result.stderr)
        # A historical pre-contract v2 snapshot still validates its exact ledger.
        legacy = '# Historical\n\n## Review\n\n' + (self.root / LEDGER).read_text().split('## Review\n\n')[1].split('## Open Loops')[0]
        (self.root / LEDGER).write_text(legacy)
        with self.assertRaisesRegex(ValueError, 'development evidence changed'):
            advance.check(self.root, LEDGER)

    def test_historical_manifest_compatibility_requires_identity_and_evidence(self):
        git(self.root, 'add', 'src/app.py')
        git(self.root, 'commit', '-qm', 'historical work')
        ledger = self.root / LEDGER
        ledger.write_text('# Historical\n\n## Review\n\n- reviewed-at: historical\n  result: pass\n  review-id: historical-review\n  manifest: .deepdone/reviews/historical-review.json\n')
        manifest = self.root / '.deepdone/reviews/historical-review.json'
        manifest.parent.mkdir(parents=True)
        data = {'schema_version': 1, 'ledger_path': LEDGER, 'review_id': 'historical-review',
                'evidence': [capture.filesystem_evidence(self.root, 'ledger', LEDGER)]}
        manifest.write_text(json.dumps(data))
        self.assertEqual(advance.check(self.root, LEDGER), ([], []))
        for field, value, message in [('ledger_path', 'notes/epics/other.md', 'identity'),
                                     ('evidence', [], 'no development evidence')]:
            manifest.write_text(json.dumps({**data, field: value}))
            with self.assertRaisesRegex(ValueError, message):
                advance.check(self.root, LEDGER)
        manifest.write_text(json.dumps(data))
        self.ready()
        with self.assertRaisesRegex(ValueError, 'cannot use legacy manifest'):
            advance.check(self.root, LEDGER)

    def test_candidate_mode_and_commit_authority_preserve_git(self):
        self.ready()
        manifest = capture.capture(self.root, LEDGER)
        before = v.git_context(self.root)
        candidate = self.fixture.run_candidate(self.root, manifest)
        self.assertIn('"commit_gate_errors": []', candidate.stdout)
        self.assertEqual(v.git_context(self.root), before)
        command = [sys.executable, str(snapshot_tests.COMMIT_SCRIPT), '--commit', '--ledger', LEDGER,
                   '--reviewed-change-set', manifest.relative_to(self.root).as_posix()]
        result = subprocess.run(command, cwd=self.root, text=True, capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('authorization is incomplete', result.stderr)
        self.assertEqual(v.git_context(self.root), before)

    def test_migration_preserves_old_text_and_no_downgrade(self):
        path = self.root / LEDGER
        path.write_text(path.read_text().replace('result: pass\n  notes: ok', 'result : fail\n    result: pass'))
        old = path.read_text()
        self.errors('missing verification contract')
        self.ready()
        self.assertTrue(path.read_text().startswith(old.rstrip()))
        path.write_text(old)
        self.errors('missing verification contract')
        with self.assertRaisesRegex(ValueError, 'removed'):
            self.init()

    def test_tampering_rejected_at_every_gate(self):
        self.ready()
        manifest = capture.capture(self.root, LEDGER)
        contract = self.contract()
        for reference in (contract['inventories'][0], contract['attempts'][0]['receipt']):
            path = self.root / reference['path']
            original = path.read_bytes()
            path.write_bytes(original + b' ')
            before = v.git_context(self.root)
            with self.assertRaisesRegex(ValueError, 'artifact digest mismatch'):
                capture.capture(self.root, LEDGER)
            candidate = self.fixture.run_candidate(self.root, manifest)
            self.assertIn('artifact digest mismatch', candidate.stdout)
            result = self.fixture.run_commit(self.root, manifest)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn('artifact digest mismatch', result.stderr)
            with self.assertRaisesRegex(ValueError, 'artifact digest mismatch'):
                advance.check(self.root, LEDGER)
            self.assertEqual(v.git_context(self.root), before)
            path.write_bytes(original)
        self.init([self.check, {**self.check, 'id': 'added'}])
        result = self.fixture.run_commit(self.root, manifest)
        self.assertIn('development evidence changed after review', result.stderr)

    def test_commit_and_advance_keep_untracked_content_fresh(self):
        (self.root / 'src/new.py').write_text('NEW=1\n')
        self.ready()
        (self.root / 'scratch').write_text('user work')
        manifest = capture.capture(self.root, LEDGER)
        result = self.fixture.run_candidate(self.root, manifest)
        self.assertIn('"commit_gate_errors": []', result.stdout)
        before = git(self.root, 'rev-parse', 'HEAD').stdout.strip()
        result = self.fixture.run_commit(self.root, manifest)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(git(self.root, 'diff', '--name-only', before, 'HEAD').stdout.splitlines()), {'src/app.py', 'src/new.py'})
        self.assertEqual(v.validate(self.root, LEDGER), [])
        self.assertEqual(advance.check(self.root, LEDGER)[0], [])
        self.assertEqual((self.root / 'scratch').read_text(), 'user work')

    def test_unignored_artifacts_not_owned_or_staged_and_stop(self):
        (self.root / '.gitignore').write_text('notes/epics/\n')
        git(self.root, 'add', '.gitignore')
        git(self.root, 'commit', '-qm', 'unignore evidence')
        head = git(self.root, 'rev-parse', 'HEAD').stdout.strip()
        self.fixture.write_passing_ledger(self.root, head, ['.'])
        self.ready()
        manifest = capture.capture(self.root, LEDGER)
        data = json.loads(manifest.read_text())
        owned = git(self.root, 'diff', '--name-only', data['base_head'], data['review_commit']).stdout.splitlines()
        self.assertEqual(owned, ['src/app.py'])
        receipt = self.contract()['attempts'][0]['receipt']['path']
        git(self.root, 'add', receipt)
        before = v.git_context(self.root)
        result = self.fixture.run_commit(self.root, manifest)
        self.assertIn('staged paths exist outside', result.stderr)
        self.assertEqual(v.git_context(self.root), before)
        (self.root / '.deepdone/STOP').touch()
        with self.assertRaisesRegex(ValueError, 'STOP'):
            self.run_check()
        with self.assertRaisesRegex(ValueError, 'STOP'):
            capture.capture(self.root, LEDGER)
        result = self.fixture.run_commit(self.root, manifest)
        self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
