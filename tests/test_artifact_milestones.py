"""Real local receipt/review lifecycles, including artifact-to-code handoff."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

import test_reviewed_change_set as reviewed
from test_reviewed_change_set import ROOT, git

sys.path.insert(0, str(ROOT / 'skills/deepdone/scripts'))
import capture_reviewed_change_set as capture
import check_reviewed_change_set as terminal
import routing
import verification as v

LEDGER = 'notes/epics/demo.md'
ACCEPTANCE = 'Two reviewed evidence files contain expected values'


class ArtifactMilestoneTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.helper = reviewed.ReviewedChangeSetTests()
        self.helper.setUp()
        self.head = self.helper.init_repo(self.root)
        (self.root / '.git/info/exclude').write_text('private/\n')
        (self.root / 'private').mkdir()
        (self.root / 'private/a.txt').write_text('private evidence A')
        (self.root / 'private/b.txt').write_text('private evidence B')
        self.path = self.helper.write_passing_ledger(self.root, self.head, ['src'])
        declaration = {'roots': ['private'], 'checks': ['evidence'],
                       'source_scope': {'include': ['src'], 'exclude': []}}
        text = self.path.read_text().replace('- [x] ship demo', '- [x] prepare evidence\n'
            '  - type: artifact-only\n'
            f'  - acceptance: {ACCEPTANCE}\n'
            f'  - artifacts: {json.dumps(declaration)}')
        text = text.replace('  result: pass\n  review-id:',
                            '  result: pass\n  type: artifact-only\n  milestone: prepare evidence\n'
                            '  disposition: accepted\n  review-id:')
        self.path.write_text(text)
        self.check = {'id': 'evidence', 'acceptance': ACCEPTANCE, 'required': True,
                      'argv': [sys.executable, '-I', '-B', '-c',
                               "from pathlib import Path; assert Path('private/a.txt').read_text() == 'private evidence A'; assert Path('private/b.txt').read_text() == 'private evidence B'"],
                      'cwd': '.', 'inputs': [{'path': 'private', 'role': 'local-data'}],
                      'exclusions': [], 'env': {}, 'context': 'local-files', 'timeout': 5}

    def ready(self):
        v.initialize(self.root, LEDGER, [self.check], 'Evidence acceptance')
        self.assertTrue(v.execution_succeeded(v.run_check(self.root, LEDGER, 'evidence')))

    def capture(self):
        self.ready()
        return capture.capture(self.root, LEDGER)

    def test_complete_without_git_objects_or_index_changes(self):
        (self.root / 'scratch.txt').write_bytes(b'unrelated staged bytes')
        git(self.root, 'add', 'scratch.txt')
        before = (git(self.root, 'count-objects', '-v').stdout,
                  (self.root / '.git/index').read_bytes(), git(self.root, 'status', '--porcelain').stdout)
        manifest = self.capture()
        self.assertEqual(terminal.check(self.root, LEDGER), ([], []))
        self.assertEqual(before, (git(self.root, 'count-objects', '-v').stdout,
                                 (self.root / '.git/index').read_bytes(), git(self.root, 'status', '--porcelain').stdout))
        self.assertEqual(git(self.root, 'rev-parse', 'HEAD').stdout.strip(), self.head)
        self.assertEqual(git(self.root, 'for-each-ref', 'refs/deepdone/reviews').stdout, '')
        self.assertNotIn('private evidence A', manifest.read_text())
        data = json.loads(manifest.read_text())
        self.assertEqual(len([e for e in data['artifacts']['entries'] if e['kind'] == 'file']), 2)
        facts = routing.observe(self.root, ledger=LEDGER)
        self.assertFalse(facts['errors'], facts)
        self.assertEqual(routing.route(facts, mode='end-to-end')['state'], 'complete', facts)
        self.assertEqual(routing.route(facts, requested='commit')['stop_reason'], 'artifact_only_no_commit')
        self.assertNotEqual(self.helper.run_commit(self.root, manifest).returncode, 0)

    def test_modified_missing_added_and_mode_changed_artifacts_block(self):
        self.capture()
        target = self.root / 'private/a.txt'
        original = target.read_bytes()
        changes = [lambda: target.write_text('changed'), lambda: target.unlink(),
                   lambda: (self.root / 'private/new.txt').write_text('new'), lambda: target.chmod(0o755)]
        for change in changes:
            with self.subTest(change=change):
                change()
                with self.assertRaises((ValueError, OSError)):
                    terminal.check(self.root, LEDGER)
                target.write_bytes(original)
                target.chmod(0o644)
                (self.root / 'private/new.txt').unlink(missing_ok=True)
        self.assertEqual(terminal.check(self.root, LEDGER), ([], []))

    def test_stale_readiness_cannot_be_recaptured(self):
        self.ready()
        (self.root / 'private/new.txt').write_text('new')
        with self.assertRaisesRegex(ValueError, 'stale verification inputs'):
            capture.capture(self.root, LEDGER)

    def test_source_changes_and_hidden_source_changes_cannot_bypass_commit(self):
        self.ready()
        source = self.root / 'src/app.py'
        for flag in (None, '--assume-unchanged', '--skip-worktree'):
            with self.subTest(flag=flag):
                if flag:
                    git(self.root, 'update-index', flag, 'src/app.py')
                source.write_text('VALUE = 2\n')
                with self.assertRaisesRegex(ValueError, 'artifact-only milestone has source changes'):
                    capture.capture(self.root, LEDGER)
                source.write_text('VALUE = 1\n')
                if flag:
                    git(self.root, 'update-index', flag.replace('--', '--no-', 1), 'src/app.py')

    def test_staged_only_code_blocks(self):
        self.ready()
        source = self.root / 'src/app.py'
        source.write_text('VALUE = 2\n')
        git(self.root, 'add', 'src/app.py')
        source.write_text('VALUE = 1\n')
        with self.assertRaisesRegex(ValueError, 'Git changes in source scope'):
            capture.capture(self.root, LEDGER)

    def test_code_change_after_review_blocks_completion(self):
        self.capture()
        (self.root / 'src/app.py').write_text('VALUE = 2\n')
        with self.assertRaisesRegex(ValueError, 'artifact-only milestone has source changes'):
            terminal.check(self.root, LEDGER)

    def test_no_deliverables_no_acceptance_and_wrong_review_binding_block(self):
        self.ready()
        original = self.path.read_text()
        for old, new in [('"roots": ["private"]', '"roots": []'),
                         ('  - acceptance: ' + ACCEPTANCE, '  - acceptance: invented acceptance'),
                         ('milestone: prepare evidence', 'milestone: wrong milestone'),
                         ('disposition: accepted', 'disposition: unresolved')]:
            with self.subTest(new=new):
                self.path.write_text(original.replace(old, new))
                with self.assertRaises(ValueError):
                    capture.capture(self.root, LEDGER)
        self.path.write_text(original)
        for file in (self.root / 'private').iterdir():
            file.unlink()
        with self.assertRaisesRegex(ValueError, 'no files'):
            capture.capture(self.root, LEDGER)

    def test_untracked_or_tracked_artifacts_and_public_storage_block(self):
        self.ready()
        git(self.root, 'add', '-f', 'private/a.txt')
        with self.assertRaisesRegex(ValueError, 'ignored and untracked'):
            capture.capture(self.root, LEDGER)
        git(self.root, 'reset', '-q', 'HEAD', '--', 'private/a.txt')
        git(self.root, 'add', '-f', LEDGER)
        with self.assertRaisesRegex(ValueError, 'ignored and untracked'):
            capture.capture(self.root, LEDGER)

    def test_missing_or_tampered_manifest_and_receipt_block(self):
        path = self.capture()
        raw = path.read_bytes()
        path.unlink()
        with self.assertRaisesRegex(ValueError, 'manifest is missing'):
            terminal.check(self.root, LEDGER)
        path.write_bytes(raw)
        data = json.loads(raw)
        data['milestone'] = 'other'
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            terminal.check(self.root, LEDGER)
        path.write_bytes(raw)
        receipt = next((self.root / v.namespace(LEDGER) / 'receipts').glob('*.json'))
        receipt.write_bytes(receipt.read_bytes() + b' ')
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            terminal.check(self.root, LEDGER)

    def test_mixed_epic_artifact_then_code_through_commit(self):
        self.path.write_text(self.path.read_text().replace('## Verification Log',
            '- [ ] implement app\n  - acceptance: Application source compiles\n'
            '  - depends on: prepare evidence\n\n## Verification Log').replace('## Status\n\ncomplete', '## Status\n\nactive'))
        self.capture()
        facts = routing.observe(self.root, ledger=LEDGER)
        self.assertEqual(routing.route(facts)['admitted_action'], 'implement', facts)
        (self.root / 'src/app.py').write_text('VALUE = 2\n')
        old = self.path.read_text()
        self.helper.write_passing_ledger(self.root, self.head, ['src'], review_id='20260711T130000Z-a1b2c3d4')
        fresh = self.path.read_text()
        # Preserve the full verification chain and declarations when progressing.
        old = old.replace(capture.section(old, 'Review'), capture.section(fresh, 'Review'))
        old = old.replace('- [ ] implement app', '- [x] implement app').replace('## Status\n\nactive', '## Status\n\ncomplete')
        self.path.write_text(old)
        code = dict(self.check, id='syntax', acceptance='Application source compiles',
                    argv=[sys.executable, '-I', '-B', '-c', "compile(open('src/app.py').read(), 'app.py', 'exec')"],
                    inputs=[{'path': 'src', 'role': 'source'}])
        with self.assertRaisesRegex(ValueError, 'must remain required'):
            v.initialize(self.root, LEDGER, [code], 'Cannot retire artifact acceptance')
        v.initialize(self.root, LEDGER, [self.check, code], 'Add code acceptance')
        self.assertTrue(v.execution_succeeded(v.run_check(self.root, LEDGER, 'syntax')))
        manifest = capture.capture(self.root, LEDGER)
        self.assertEqual(json.loads(manifest.read_text())['schema_version'], 2)
        self.assertEqual(terminal.check(self.root, LEDGER)[0], ['src/app.py'])
        result = self.helper.run_commit(self.root, manifest)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(terminal.check(self.root, LEDGER), ([], ['src/app.py']))
        (self.root / 'private/new.txt').write_text('late addition')
        with self.assertRaisesRegex(ValueError, 'stale verification inputs'):
            terminal.check(self.root, LEDGER)

    def test_empty_code_review_still_rejected_with_actionable_diagnostic(self):
        self.ready()
        self.path.write_text(self.path.read_text().replace('  type: artifact-only\n', ''))
        with self.assertRaisesRegex(ValueError, 'no dirty version-controlled paths; declare an artifact-only'):
            capture.capture(self.root, LEDGER)

    def test_artifact_declaration_cannot_use_legacy_completion(self):
        text = self.path.read_text()
        self.path.write_text(text.replace(capture.section(text, 'Review'),
                                         '- reviewed-at: now\n  result: pass\n  notes: legacy'))
        with self.assertRaisesRegex(ValueError, 'manifest is missing'):
            terminal.check(self.root, LEDGER)
        self.assertFalse(routing.observe(self.root, ledger=LEDGER)['integrated'])

    def test_acceptance_coverage_and_private_storage_required_before_execution(self):
        for check in (dict(self.check, id='unbound'),
                      dict(self.check, inputs=[{'path': 'private/a.txt', 'role': 'local-data'}]),
                      dict(self.check, exclusions=[{'path': 'private/b.txt', 'reason': 'Omitted deliverable'}])):
            with self.subTest(check=check['id']), self.assertRaises(ValueError):
                v.initialize(self.root, LEDGER, [check], 'Insufficient evidence')
        self.assertFalse((self.root / v.namespace(LEDGER)).exists())
        git(self.root, 'add', '-f', LEDGER)
        with self.assertRaisesRegex(ValueError, 'ignored and untracked'):
            self.ready()
        self.assertFalse((self.root / v.namespace(LEDGER)).exists())

    def test_existing_code_milestone_cannot_be_bypassed(self):
        self.ready()
        self.path.write_text(self.path.read_text().replace('## Verification Log',
            '- [x] implement app\n  - acceptance: Application source compiles\n\n## Verification Log'))
        with self.assertRaisesRegex(ValueError, 'retain the cumulative code snapshot'):
            capture.capture(self.root, LEDGER)

    def test_artifact_initial_routing_and_semantic_changes(self):
        text = self.path.read_text().replace('- [x] prepare evidence', '- [ ] prepare evidence')
        text = text.replace(capture.section(text, 'Review'), '- reviewed-at: not-run\n  result: pending')
        self.path.write_text(text.replace('## Status\n\ncomplete', '## Status\n\nactive'))
        facts = routing.observe(self.root, ledger=LEDGER)
        self.assertEqual(routing.route(facts)['admitted_action'], 'implement', facts)
        (self.root / 'private/new.txt').write_text('new deliverable')
        changed = routing.observe(self.root, ledger=LEDGER)
        self.assertNotEqual(changed['token'], facts['token'])

    def test_advance_gate_accepts_artifact_completion(self):
        roadmap = self.root / 'notes/roadmap.md'
        roadmap.write_text('# Roadmap\n\n## Active Epic\n\n- ledger: ' + LEDGER + '\n- state: complete-pending-advance\n')
        self.path.write_text(self.path.read_text().replace('    ledger: ' + LEDGER, '    ledger: ' + LEDGER + '\n    roadmap: notes/roadmap.md'))
        self.capture()
        facts = routing.observe(self.root, ledger=LEDGER)
        self.assertEqual(routing.route(facts, requested='advance')['admitted_action'], 'advance', facts)
        (self.root / 'private/new.txt').write_text('new')
        facts = routing.observe(self.root, ledger=LEDGER)
        self.assertIsNone(routing.route(facts, requested='advance')['admitted_action'])


if __name__ == '__main__':
    unittest.main()
