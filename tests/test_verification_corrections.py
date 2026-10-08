"""Regression counterexamples for the independently reviewed DD-004 contract."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_verification as fixtures
from test_verification import LEDGER, v, capture, advance
from test_reviewed_change_set import git, ROOT


class CorrectionTests(unittest.TestCase):
    setUp = fixtures.VerificationTests.setUp
    init = fixtures.VerificationTests.init
    ready = fixtures.VerificationTests.ready
    run_check = fixtures.VerificationTests.run_check
    contract = fixtures.VerificationTests.contract

    def preserved(self):
        return {
            'git': v.git_context(self.root),
            'flags': git(self.root, 'ls-files', '-v').stdout,
            'config': (self.root / '.git/config').read_bytes(),
            'refs': git(self.root, 'show-ref').stdout,
            'files': {str(p.relative_to(self.root)): (p.read_bytes(), p.stat().st_mode)
                      for p in self.root.rglob('*') if p.is_file() and '.git' not in p.parts},
        }

    def test_hidden_source_mismatches_reach_every_gate(self):
        # Each subcase uses a new repository; legacy capture below models c22fefd.
        for variant in ('assume-unchanged', 'skip-worktree', 'deleted', 'dependency-mode', 'owned-mode'):
            with self.subTest(variant=variant):
                self.setUp()
                dependency = self.root / 'src/dependency.py'
                dependency.write_text('EXPECTED = 1\n')
                git(self.root, 'add', 'src/dependency.py')
                git(self.root, 'commit', '-qm', 'dependency baseline')
                head = git(self.root, 'rev-parse', 'HEAD').stdout.strip()
                self.fixture.write_passing_ledger(self.root, head, ['src/app.py'])
                if variant in ('assume-unchanged', 'skip-worktree', 'deleted'):
                    flag = 'skip-worktree' if variant == 'deleted' else variant
                    git(self.root, 'update-index', '--' + flag, 'src/dependency.py')
                    if variant == 'deleted':
                        dependency.unlink()
                        program = "from pathlib import Path; assert not Path('src/dependency.py').exists()"
                    else:
                        dependency.write_text('EXPECTED = 2\n')
                        program = "exec(open('src/dependency.py').read()); assert EXPECTED == 2"
                else:
                    git(self.root, 'config', 'core.fileMode', 'false')
                    mode_path = 'src/app.py' if variant == 'owned-mode' else 'src/dependency.py'
                    (self.root / mode_path).chmod(0o755)
                    program = f"import os; assert os.access({mode_path!r}, os.X_OK)"
                self.check['argv'][-1] += '; ' + program
                self.ready()
                before = self.preserved()
                with self.assertRaisesRegex(ValueError, 'source.*tree|outside reviewed ownership'):
                    capture.capture(self.root, LEDGER)
                self.assertEqual(self.preserved(), before)
                # Explicit pre-correction snapshot fixture: real receipt, old tree
                # construction and exact ledger hash, only the new gate omitted.
                with patch.object(v, 'validate', return_value=[]):
                    manifest_path = capture.capture(self.root, LEDGER)
                manifest = json.loads(manifest_path.read_text())
                before = self.preserved()
                candidate = self.fixture.run_candidate(self.root, manifest_path)
                self.assertNotIn('"commit_gate_errors": []', candidate.stdout)
                self.assertRegex(candidate.stdout, 'source.*tree|outside reviewed ownership')
                result = self.fixture.run_commit(self.root, manifest_path)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertRegex(result.stderr, 'source.*tree|outside reviewed ownership')
                self.assertEqual(self.preserved(), before)
                capture.stage_paths_from_commit(self.root, manifest['review_commit'], {'src/app.py'})
                git(self.root, 'commit', '-qm', 'old reviewed snapshot fixture')
                before = self.preserved()
                with self.assertRaisesRegex(ValueError, 'source.*tree|outside reviewed ownership'):
                    advance.check(self.root, LEDGER)
                self.assertEqual(self.preserved(), before)

    def test_exact_source_commit_and_subsequent_review(self):
        dependency = self.root / 'src/dependency.py'
        dependency.write_text('EXPECTED = 1\n')
        stable = self.root / 'src/stable.py'
        stable.write_text('STABLE = 1\n')
        git(self.root, 'add', 'src/dependency.py', 'src/stable.py')
        git(self.root, 'commit', '-qm', 'base dependencies')
        head = git(self.root, 'rev-parse', 'HEAD').stdout.strip()
        self.fixture.write_passing_ledger(self.root, head, ['src/'])
        dependency.write_text('EXPECTED = 2\n')
        new = self.root / 'src/new.py'
        new.write_text('NEW = 2\n')
        new.chmod(0o755)
        self.check['argv'][-1] += "; exec(open('src/dependency.py').read()); exec(open('src/new.py').read()); assert EXPECTED == NEW == VALUE"
        self.ready()
        for iteration in range(2):
            manifest = capture.capture(self.root, LEDGER)
            self.assertIn('"commit_gate_errors": []', self.fixture.run_candidate(self.root, manifest).stdout)
            result = self.fixture.run_commit(self.root, manifest)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(advance.check(self.root, LEDGER)[0], [])
            for path in ('src/app.py', 'src/dependency.py', 'src/stable.py', 'src/new.py'):
                self.assertEqual(git(self.root, 'show', 'HEAD:' + path).stdout, (self.root / path).read_text())
                mode = '100755' if (self.root / path).stat().st_mode & 0o111 else '100644'
                self.assertTrue(git(self.root, 'ls-tree', 'HEAD', path).stdout.startswith(mode))
            if iteration == 0:
                (self.root / 'src/app.py').write_text('VALUE = 2\n# re-reviewed change\n')
                ledger = self.root / LEDGER
                text = ledger.read_text()
                review = capture.section(text, 'Review')
                old_id = capture.latest_review_entry(text)['review-id']
                review = review.replace(old_id, '20260712T120000Z-b1b2c3d4').replace(head, git(self.root, 'rev-parse', 'HEAD').stdout.strip())
                ledger.write_text(text.replace('## Open Loops', review + '\n\n## Open Loops'))
                self.run_check()

    def cli(self, cwd=None, purpose='readiness'):
        return subprocess.run([sys.executable, '-B', str(ROOT / 'skills/deepdone/scripts/verification.py'),
                               'run', '--ledger', LEDGER, '--check-id', 'app', '--purpose', purpose],
                              cwd=cwd or self.root, capture_output=True, text=True)

    def last_receipt(self):
        contract = self.contract()
        _, definitions = v.inventory(self.root, LEDGER, contract)
        receipts = v.validate_history(self.root, LEDGER, contract, definitions)
        return receipts[contract['attempts'][-1]['id']]

    def tool(self, path, name='cmp'):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('#!/bin/sh\n' + ('exec ' + shutil.which('cmp', path=os.defpath) + ' "$@"\n' if name == 'cmp' else 'exit 1\n'))
        path.chmod(0o755)
        return {'path': str(path.resolve()), 'sha256': v.file_digest(path)}

    def test_child_relative_path_and_cli_identity(self):
        work = self.root / 'work'
        work.mkdir()
        (self.root / 'src/expected.py').write_text('VALUE = 2\n')
        for search in ('.', ':/usr/bin', ''):
            with self.subTest(PATH=search):
                wrong = self.root / 'check-tool'
                actual = work / 'check-tool'
                self.tool(wrong, 'false')
                expected = self.tool(actual)
                self.check.update(argv=['check-tool', '../src/app.py', '../src/expected.py'], cwd='work',
                                  env={'PATH': search}, inputs=[{'path': 'src', 'role': 'source'},
                                  {'path': 'check-tool', 'role': 'source'}, {'path': 'work/check-tool', 'role': 'source'}])
                self.init()
                for caller in (self.root, work):
                    result = self.cli(caller)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(self.last_receipt()['tool'], expected)
                    self.assertEqual(v.validate(self.root, LEDGER), [])
        wrong.unlink()
        self.check['inputs'] = [{'path': 'src', 'role': 'source'}, {'path': 'work/check-tool', 'role': 'source'}]
        self.init()
        self.assertEqual(self.cli().returncode, 0)  # Original CLI emitted completed/tool=null.
        self.assertEqual(self.last_receipt()['tool'], expected)

    def test_ordinary_argv_and_path_contexts(self):
        work = self.root / 'work'
        work.mkdir()
        expected = self.tool(work / 'check-tool')
        (self.root / 'src/expected.py').write_text('VALUE = 2\n')
        for argv0, env in (('./check-tool', {}), (str(work / 'check-tool'), {}),
                           ('check-tool', {'PATH': str(work)}), ('cmp', {}),
                           (shutil.which('cmp', path=os.defpath), {})):
            with self.subTest(argv=argv0, env=env):
                self.check.update(argv=[argv0, '../src/app.py', '../src/expected.py'], cwd='work', env=env)
                self.init()
                for cwd in (self.root, work):
                    result = self.cli(cwd)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    receipt = self.last_receipt()
                    tool = expected if 'check-tool' in argv0 else {'path': str(Path(shutil.which('cmp', path=os.defpath)).resolve()), 'sha256': v.file_digest(Path(shutil.which('cmp', path=os.defpath)))}
                    self.assertEqual(receipt['tool'], tool)
                    self.assertEqual(v.validate(self.root, LEDGER), [])

    def test_external_executable_freshness_uses_child_not_parent(self):
        work = self.root / 'work'
        work.mkdir()
        # Absolute temp paths stay outside the declared source inputs.
        wrong = self.root.parent / (self.root.name + '-parent') / 'check-tool'
        actual = self.root.parent / (self.root.name + '-child') / 'check-tool'
        self.addCleanup(shutil.rmtree, wrong.parent)
        self.addCleanup(shutil.rmtree, actual.parent)
        self.tool(wrong)
        expected = self.tool(actual)
        # The same relative PATH from root vs work resolves different candidates.
        (self.root / 'tools').symlink_to(wrong.parent, target_is_directory=True)
        (work / 'tools').symlink_to(actual.parent, target_is_directory=True)
        (self.root / 'src/expected.py').write_text('VALUE = 2\n')
        self.check.update(argv=['check-tool', '../src/app.py', '../src/expected.py'], cwd='work', env={'PATH': 'tools'})
        self.init()
        previous = Path.cwd()
        try:
            os.chdir(self.root)
            receipt = self.run_check()
            self.assertEqual(receipt['tool'], expected)
            self.assertEqual(v.validate(self.root, LEDGER), [])
            self.tool(wrong, 'false')
            self.assertEqual(v.validate(self.root, LEDGER), [])
            self.tool(actual, 'false')
            self.assertIn('stale executable', ';'.join(v.validate(self.root, LEDGER)))
        finally:
            os.chdir(previous)

    def test_resolution_failure_never_launches_and_can_resume(self):
        self.init()
        with patch.object(v, 'executable', side_effect=OSError('cannot read executable')), \
                patch.object(v, 'stream_command', wraps=v.stream_command) as launch:
            receipt = self.run_check()
        launch.assert_not_called()
        self.assertNotEqual(receipt['outcome'], 'completed')
        self.assertIn('cannot read executable', receipt['error'])
        self.last_receipt()  # terminal history must be valid
        old = copy.deepcopy(self.contract()['attempts'])
        self.init()
        self.assertEqual(self.cli().returncode, 0)
        self.assertEqual(self.contract()['attempts'][:len(old)], old)
        self.assertEqual(v.validate(self.root, LEDGER), [])

    def test_cli_success_is_complete_per_execution_not_inventory(self):
        self.init([self.check, {**self.check, 'id': 'other'}])
        self.assertEqual(self.cli(purpose='diagnostic').returncode, 0)
        self.assertIn('missing readiness', ';'.join(v.validate(self.root, LEDGER)))
        self.assertEqual(self.cli().returncode, 0)
        self.assertIn('other: missing readiness', ';'.join(v.validate(self.root, LEDGER)))
        self.check['argv'][-1] = 'raise SystemExit(7)'
        self.init()
        self.assertNotEqual(self.cli(purpose='diagnostic').returncode, 0)

    def test_retained_stronger_review_blocks_legacy_variants(self):
        self.ready()
        manifest_path = capture.capture(self.root, LEDGER)
        self.assertEqual(self.fixture.run_commit(self.root, manifest_path).returncode, 0)
        self.assertEqual(advance.check(self.root, LEDGER)[0], [])
        ledger = self.root / LEDGER
        text = ledger.read_text()
        span = v.contract_span(text)
        text = text[:span[0]] + text[span[2]:]
        shutil.rmtree(self.root / v.namespace(LEDGER))
        for variant in ('no-manifest', 'missing', 'schema1', 'unreadable'):
            with self.subTest(variant=variant):
                extra = '' if variant == 'no-manifest' else '  review-id: recovery\n  manifest: .deepdone/reviews/recovery.json\n'
                ledger.write_text(text.replace('## Open Loops', '- reviewed-at: later\n  result: pass\n' + extra + '\n## Open Loops'))
                recovery = self.root / '.deepdone/reviews/recovery.json'
                recovery.unlink(missing_ok=True)
                if variant == 'schema1':
                    recovery.write_text(json.dumps({'schema_version': 1, 'ledger_path': LEDGER, 'review_id': 'recovery',
                                                    'evidence': [capture.filesystem_evidence(self.root, 'ledger', LEDGER)]}))
                if variant == 'unreadable':
                    manifest_path.write_text('{broken')
                before = self.preserved()
                with self.assertRaisesRegex(ValueError, 'downgrade|retained|historical|provenance'):
                    advance.check(self.root, LEDGER)
                self.assertEqual(self.preserved(), before)

    def test_pre_receipt_v2_and_ambiguous_historical_provenance(self):
        # Historical schema-v2 snapshot predating receipt enforcement.
        with patch.object(v, 'validate', return_value=[]):
            path = capture.capture(self.root, LEDGER)
        manifest = json.loads(path.read_text())
        capture.stage_paths_from_commit(self.root, manifest['review_commit'], {'src/app.py'})
        git(self.root, 'commit', '-qm', 'historical snapshot')
        self.assertEqual(advance.check(self.root, LEDGER)[0], [])
        ledger = self.root / LEDGER
        ledger.write_text('# Historical\n\n## Review\n\n- reviewed-at: old\n  result: pass\n  review-id: retained\n  manifest: .deepdone/reviews/retained.json\n\n- reviewed-at: later\n  result: pass\n')
        path.unlink()
        retained = self.root / '.deepdone/reviews/retained.json'
        for content in ('{broken', json.dumps({'schema_version': 1, 'ledger_path': 'notes/epics/other.md', 'review_id': 'retained'}),
                        json.dumps({'schema_version': 1, 'ledger_path': LEDGER, 'review_id': 'retained',
                                    'evidence': [{'role': 'ledger', 'path': 'notes/epics/other.md'}]})):
            retained.write_text(content)
            before = self.preserved()
            with self.assertRaisesRegex(ValueError, 'historical provenance'):
                advance.check(self.root, LEDGER)
            self.assertEqual(self.preserved(), before)

    def test_selected_manifest_provenance_and_cross_ledger_isolation(self):
        git(self.root, 'add', 'src/app.py')
        git(self.root, 'commit', '-qm', 'historical completed source')
        ledger = self.root / LEDGER
        ledger.write_text('# Historical\n\n## Review\n\n- reviewed-at: old\n  result: pass\n')
        directory = self.root / '.deepdone/reviews'
        directory.mkdir(parents=True)
        other = directory / 'other.json'
        other.write_text(json.dumps({'schema_version': 2, 'ledger_path': 'notes/epics/other.md'}))
        self.assertEqual(advance.check(self.root, LEDGER), ([], []))
        other.write_text(json.dumps({'schema_version': 2, 'ledger_path': LEDGER}))
        before = self.preserved()
        with self.assertRaisesRegex(ValueError, 'downgrade|retained|provenance'):
            advance.check(self.root, LEDGER)
        self.assertEqual(self.preserved(), before)


if __name__ == '__main__':
    unittest.main()
