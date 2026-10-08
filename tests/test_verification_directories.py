"""Directory applicability regressions using actual checks and Git consumers."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import test_verification_corrections as corrections
from test_verification import LEDGER, v, capture, advance
from test_reviewed_change_set import git


class DirectoryTests(unittest.TestCase):
    setUp = corrections.CorrectionTests.setUp
    init = corrections.CorrectionTests.init
    ready = corrections.CorrectionTests.ready
    run_check = corrections.CorrectionTests.run_check
    contract = corrections.CorrectionTests.contract
    cli = corrections.CorrectionTests.cli
    last_receipt = corrections.CorrectionTests.last_receipt

    def preserved(self):
        state = corrections.CorrectionTests.preserved(self)
        state['directories_and_links'] = {
            str(p.relative_to(self.root)): (p.lstat().st_mode, os.readlink(p) if p.is_symlink() else None)
            for p in self.root.rglob('*') if '.git' not in p.parts and (p.is_dir() or p.is_symlink())}
        return state

    def test_source_directory_refusal_at_independent_consumers(self):
        (self.root / 'src/required-dir').mkdir()
        self.check['argv'][-1] += "; from pathlib import Path; assert Path('src/required-dir').is_dir()"
        self.ready()
        receipt = self.last_receipt()
        self.assertIn({'path': 'src/required-dir', 'kind': 'directory', 'mode': '', 'sha256': '', 'role': 'source'}, receipt['after']['entries'])
        before = self.preserved()
        with self.subTest(gate='capture'):
            with self.assertRaisesRegex(ValueError, 'directory|materializ'):
                capture.capture(self.root, LEDGER)
            self.assertEqual(self.preserved(), before)
        # Setup only: reconstruct a genuine fa4cb8c capture with real receipt
        # and ledger hashes; no validator is bypassed at any consumer below.
        with patch.object(v, 'validate', return_value=[]):
            manifest = capture.capture(self.root, LEDGER)
        data = json.loads(manifest.read_text())
        before = self.preserved()
        with self.subTest(gate='candidate'):
            result = self.fixture.run_candidate(self.root, manifest)
            self.assertNotIn('"commit_gate_errors": []', result.stdout)
            self.assertRegex(result.stdout, 'directory|materializ')
            self.assertEqual(self.preserved(), before)
        with self.subTest(gate='commit'):
            result = self.fixture.run_commit(self.root, manifest)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertRegex(result.stderr, 'directory|materializ')
            self.assertEqual(self.preserved(), before)
        # Complete the old capture in this disposable fixture, independently of
        # current commit preflight, to test the real normal pre-Advance boundary.
        if git(self.root, 'rev-parse', 'HEAD').stdout.strip() == data['base_head']:
            capture.stage_paths_from_commit(self.root, data['review_commit'], {'src/app.py'})
            git(self.root, 'commit', '-qm', 'pre-correction directory snapshot')
        before = self.preserved()
        with self.subTest(gate='advance'):
            with self.assertRaisesRegex(ValueError, 'directory|materializ'):
                advance.check(self.root, LEDGER)
            self.assertEqual(self.preserved(), before)

    def commit_and_materialize(self):
        manifest = capture.capture(self.root, LEDGER)
        result = self.fixture.run_candidate(self.root, manifest)
        self.assertIn('"commit_gate_errors": []', result.stdout)
        result = self.fixture.run_commit(self.root, manifest)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(advance.check(self.root, LEDGER)[0], [])
        with tempfile.TemporaryDirectory() as t:
            target = Path(t).resolve()
            rows = subprocess.run(['git', 'ls-tree', '-rz', 'HEAD'], cwd=self.root, capture_output=True, check=True).stdout
            for row in rows.split(b'\0'):
                if not row:
                    continue
                metadata, raw_path = row.split(b'\t', 1)
                mode, kind, oid = metadata.decode().split()
                self.assertEqual(kind, 'blob')
                path = target / os.fsdecode(raw_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                raw = subprocess.run(['git', 'cat-file', 'blob', oid], cwd=self.root, capture_output=True, check=True).stdout
                path.write_bytes(raw)
                path.chmod(0o755 if mode == '100755' else 0o644)
                self.assertEqual(raw, (self.root / os.fsdecode(raw_path)).read_bytes())
                self.assertEqual(mode, '100755' if (self.root / os.fsdecode(raw_path)).stat().st_mode & 0o111 else '100644')
            result = subprocess.run(self.check['argv'], cwd=target, env=v.environment(self.check), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_owned_marker_and_unchanged_descendant_materialize_directories(self):
        for marker_owned in (True, False):
            with self.subTest(marker_owned=marker_owned):
                self.setUp()
                marker = self.root / 'src/required-dir/nested/.keep'
                marker.parent.mkdir(parents=True)
                marker.write_text('Required source directory\n')
                marker.chmod(0o755)
                if not marker_owned:
                    git(self.root, 'add', 'src/required-dir/nested/.keep')
                    git(self.root, 'commit', '-qm', 'base directory anchor')
                    self.fixture.write_passing_ledger(self.root, git(self.root, 'rev-parse', 'HEAD').stdout.strip(), ['src/app.py'])
                    self.check['exclusions'] = [{'path': 'src/required-dir/nested/.keep', 'reason': 'Only its ancestor presence is relevant to this command'}]
                self.check['argv'][-1] += "; from pathlib import Path; assert Path('src/required-dir/nested').is_dir()"
                self.ready()
                self.commit_and_materialize()

    def test_evidence_only_parents_do_not_hide_ordinary_empty_source(self):
        with (self.root / '.gitignore').open('a') as stream:
            stream.write('notes/roadmap.md\ncache/\n')
        git(self.root, 'add', '.gitignore')
        git(self.root, 'commit', '-qm', 'local evidence exclusions')
        self.fixture.write_passing_ledger(self.root, git(self.root, 'rev-parse', 'HEAD').stdout.strip(), ['src/'],
                                          evidence={'ledger': LEDGER, 'roadmap': 'notes/roadmap.md'})
        (self.root / 'notes/roadmap.md').write_text('Local roadmap')
        (self.root / 'cache/generated').mkdir(parents=True)
        self.check.update(inputs=[{'path': '.', 'role': 'source'}], exclusions=[{'path': 'cache/generated', 'reason': 'Generated runtime cache'}])
        v.initialize(self.root, LEDGER, [self.check], 'Whole-repository source and narrow evidence', 'notes/roadmap.md')
        self.assertTrue(v.execution_succeeded(self.run_check()))
        manifest = capture.capture(self.root, LEDGER)
        result = self.fixture.run_candidate(self.root, manifest)
        self.assertIn('"commit_gate_errors": []', result.stdout)
        for parent in ('notes/epics', '.deepdone/reviews'):
            with self.subTest(parent=parent):
                path = self.root / parent / 'ordinary-empty'
                path.mkdir()
                self.run_check()
                with self.assertRaisesRegex(ValueError, 'directory|materializ'):
                    capture.capture(self.root, LEDGER)
                path.rmdir()
        # Explicit designation prevents a directory being treated as incidental.
        for designated in ('notes/epics', '.deepdone', '.deepdone/reviews'):
            with self.subTest(designated=designated):
                self.check['inputs'].append({'path': designated, 'role': 'source'})
                v.initialize(self.root, LEDGER, [self.check], 'Explicit source directory', 'notes/roadmap.md')
                self.run_check()
                with self.assertRaisesRegex(ValueError, 'directory|materializ'):
                    capture.capture(self.root, LEDGER)
            self.check['inputs'].pop()
        v.initialize(self.root, LEDGER, [self.check], 'Restore genuine whole-repository declaration', 'notes/roadmap.md')
        self.run_check()
        self.commit_and_materialize()

    def cwd_fixture(self):
        work = self.root / 'local/work'
        work.mkdir(parents=True)
        self.check.update(cwd='local/work')
        self.check['argv'][-1] = "exec(open('../../src/app.py').read()); assert VALUE == 2"
        self.ready()
        return work

    def test_invalid_cwd_at_every_independent_consumer(self):
        for variant in ('missing', 'file', 'symlink', 'ancestor-symlink'):
            for stage in ('capture', 'candidate-commit', 'advance'):
                with self.subTest(variant=variant, stage=stage):
                    self.setUp()
                    work = self.cwd_fixture()
                    manifest = None if stage == 'capture' else capture.capture(self.root, LEDGER)
                    if stage == 'advance':
                        result = self.fixture.run_commit(self.root, manifest)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(advance.check(self.root, LEDGER)[0], [])
                    work.rmdir()
                    if variant == 'file':
                        work.write_text('not a directory')
                    elif variant == 'symlink':
                        work.symlink_to('../..', target_is_directory=True)
                    elif variant == 'ancestor-symlink':
                        (self.root / 'alternate/work').mkdir(parents=True)
                        work.parent.rmdir()
                        work.parent.symlink_to('alternate', target_is_directory=True)
                    before = self.preserved()
                    with self.subTest(gate='standalone'):
                        self.assertRegex(';'.join(v.validate(self.root, LEDGER)), 'cwd|working directory|symlink')
                        self.assertEqual(self.preserved(), before)
                    if stage == 'capture':
                        with self.assertRaisesRegex(ValueError, 'cwd|working directory|symlink'):
                            capture.capture(self.root, LEDGER)
                    elif stage == 'candidate-commit':
                        with self.subTest(gate='candidate'):
                            result = self.fixture.run_candidate(self.root, manifest)
                            self.assertNotIn('"commit_gate_errors": []', result.stdout)
                            self.assertRegex(result.stdout, 'cwd|working directory|symlink')
                        result = self.fixture.run_commit(self.root, manifest)
                        self.assertEqual(result.returncode, 2, result.stderr)
                        self.assertRegex(result.stderr, 'cwd|working directory|symlink')
                    else:
                        with self.assertRaisesRegex(ValueError, 'cwd|working directory|symlink'):
                            advance.check(self.root, LEDGER)
                    self.assertEqual(self.preserved(), before)

    def test_cwd_preflight_postflight_failures_and_recovery(self):
        work = self.cwd_fixture()
        work.rmdir()
        with patch.object(v, 'stream_command', wraps=v.stream_command) as launch:
            receipt = self.run_check()
        launch.assert_not_called()
        self.assertFalse(v.execution_succeeded(receipt))
        self.assertRegex(receipt['error'], 'cwd|working directory')
        self.last_receipt()
        self.assertNotEqual(self.cli().returncode, 0)
        work.mkdir()
        self.assertTrue(v.execution_succeeded(self.run_check()))
        self.check['argv'][-1] += '; from pathlib import Path; Path.cwd().rmdir()'
        self.init()
        result = self.cli()
        receipt = self.last_receipt()
        self.assertEqual(receipt['exit_code'], 0)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(v.execution_succeeded(receipt))
        self.assertRegex(receipt['error'], 'cwd|working directory')
        attempts = copy.deepcopy(self.contract()['attempts'])
        work.mkdir()
        self.check['argv'][-1] = "exec(open('../../src/app.py').read()); assert VALUE == 2"
        self.init()
        self.assertTrue(v.execution_succeeded(self.run_check()))
        self.assertEqual(self.contract()['attempts'][:len(attempts)], attempts)
        self.assertEqual(v.validate(self.root, LEDGER), [])

    def test_historical_cwd_is_not_revalidated_and_restoration_is_applicable(self):
        work = self.cwd_fixture()
        work.rmdir()
        with self.subTest(state='missing'):
            self.assertRegex(';'.join(v.validate(self.root, LEDGER)), 'cwd|working directory')
        work.mkdir()
        self.assertEqual(v.validate(self.root, LEDGER), [])
        old = copy.deepcopy(self.contract()['attempts'])
        self.check.update(cwd='.')
        self.check['argv'][-1] = "exec(open('src/app.py').read()); assert VALUE == 2"
        self.init()
        work.rmdir()
        self.assertTrue(v.execution_succeeded(self.run_check()))
        self.assertEqual(v.validate(self.root, LEDGER), [])
        self.last_receipt()
        self.assertEqual(self.contract()['attempts'][:len(old)], old)
        manifest = capture.capture(self.root, LEDGER)
        self.assertEqual(self.fixture.run_commit(self.root, manifest).returncode, 0)
        self.assertEqual(advance.check(self.root, LEDGER)[0], [])

    def test_unusable_cwd_fault_is_valid_nonpassing(self):
        self.cwd_fixture()
        access = os.access
        # Controlled permission observation: real chmod behavior varies for root.
        def unavailable(path, mode, *args, **kwargs):
            return False if Path(path) == self.root / 'local/work' else access(path, mode, *args, **kwargs)
        with patch.object(v.os, 'access', side_effect=unavailable), patch.object(v, 'stream_command', wraps=v.stream_command) as launch:
            self.assertRegex(';'.join(v.validate(self.root, LEDGER)), 'cwd|working directory')
            receipt = self.run_check()
        launch.assert_not_called()
        self.assertFalse(v.execution_succeeded(receipt))
        self.last_receipt()

    def test_local_data_directory_is_not_git_source(self):
        (self.root / '.deepdone/data').mkdir(parents=True)
        (self.root / '.deepdone/data/input').write_text('local value')
        # Ordinary ignored local data, outside the verification artifact namespace.
        self.check['inputs'].append({'path': '.deepdone/data', 'role': 'local-data'})
        self.check.update(cwd='.deepdone/data')
        self.check['argv'][-1] = "exec(open('../../src/app.py').read()); assert VALUE == 2; assert open('input').read() == 'local value'"
        self.ready()
        manifest = capture.capture(self.root, LEDGER)
        self.assertIn('"commit_gate_errors": []', self.fixture.run_candidate(self.root, manifest).stdout)
        self.assertEqual(self.fixture.run_commit(self.root, manifest).returncode, 0)
        self.assertEqual(advance.check(self.root, LEDGER)[0], [])
        self.assertNotIn('.deepdone/data', git(self.root, 'ls-tree', '-r', '--name-only', 'HEAD').stdout)


if __name__ == '__main__':
    unittest.main()
