from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "deepdone-commit" / "scripts" / "commit_progress.py"


def load_commit_progress():
    spec = importlib.util.spec_from_file_location("commit_progress", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class CommitProgressTests(unittest.TestCase):
    def setUp(self) -> None:
        self.commit_progress = load_commit_progress()

    def test_dangerous_paths_are_anchored_and_allowlisted(self) -> None:
        is_dangerous = self.commit_progress.is_dangerous

        self.assertFalse(is_dangerous("src/auth/token.ts"))
        self.assertFalse(is_dangerous("tokenizer.py"))
        self.assertFalse(is_dangerous("design-tokens.json"))
        self.assertFalse(is_dangerous("docs/credential_helper_docs.md"))
        self.assertFalse(is_dangerous("tests/fixtures/app.db"))

        self.assertTrue(is_dangerous(".env"))
        self.assertTrue(is_dangerous("ops/secrets.json"))
        self.assertTrue(is_dangerous("credentials.yml"))
        self.assertTrue(is_dangerous("private_key.pem"))
        self.assertTrue(is_dangerous("local.sqlite"))

    def test_blocked_active_epic_fails_commit_gate(self) -> None:
        errors = self.commit_progress.commit_gate_errors(
            ledger_path="notes/epics/2026-05-18-demo.md",
            active_epic_state="blocked",
            ledger_text="ledger",
            verification=["- command: `pytest`\n  result: pass"],
            review=["- review-result: pass"],
            open_loops=["none"],
        )

        self.assertIn("active epic state is blocked", errors)

    def test_verification_requires_structured_result(self) -> None:
        errors = self.commit_progress.commit_gate_errors(
            ledger_path="notes/epics/2026-05-18-demo.md",
            active_epic_state="active",
            ledger_text="ledger",
            verification=["- `pytest`: no errors"],
            review=["- review-result: pass"],
            open_loops=["none"],
        )

        self.assertIn("verification log lacks structured result markers", errors)
        self.assertNotIn("verification log contains failing or blocked check", errors)

    def test_parse_active_ledger_returns_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = root / "notes" / "epics" / "2026-05-18-demo.md"
            ledger.parent.mkdir(parents=True)
            ledger.write_text("# Demo\n\n## Status\n\nactive\n", encoding="utf-8")
            roadmap = root / "notes" / "roadmap.md"
            roadmap.write_text(
                "# Roadmap\n\n"
                "## Active Epic\n\n"
                "- name: demo\n"
                "- ledger: notes/epics/2026-05-18-demo.md\n"
                "- state: blocked\n",
                encoding="utf-8",
            )

            name, ledger_path, state, ledger_text = self.commit_progress.parse_active_ledger(root)

        self.assertEqual(name, "demo")
        self.assertEqual(ledger_path, "notes/epics/2026-05-18-demo.md")
        self.assertEqual(state, "blocked")
        self.assertIn("# Demo", ledger_text)

    def test_parse_reviewed_complete_single_epic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = root / "notes" / "epics" / "2026-07-11-demo.md"
            ledger.parent.mkdir(parents=True)
            ledger.write_text(
                "# Demo\n\n"
                "## Review\n\n"
                "- reviewed-at: 2026-07-11T11:00:00Z\n"
                "  result: pass\n"
                "  notes: clean\n\n"
                "## Status\n\ncomplete\n",
                encoding="utf-8",
            )

            _, ledger_path, _, ledger_text = self.commit_progress.parse_active_ledger(root)

        self.assertEqual(ledger_path, "notes/epics/2026-07-11-demo.md")
        self.assertIn("result: pass", ledger_text)

    def test_explicit_ledger_resolves_completed_epic_among_many(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "notes" / "epics" / "first.md"
            second = root / "notes" / "epics" / "second.md"
            first.parent.mkdir(parents=True)
            first.write_text("# First\n", encoding="utf-8")
            second.write_text("# Second\n", encoding="utf-8")

            _, ledger_path, _, ledger_text = self.commit_progress.parse_active_ledger(root, "notes/epics/second.md")

        self.assertEqual(ledger_path, "notes/epics/second.md")
        self.assertIn("# Second", ledger_text)

    def test_explicit_ledger_supplies_epic_title(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = root / "notes" / "epics" / "old.md"
            ledger.parent.mkdir(parents=True)
            ledger.write_text("# Reviewed Predecessor\n", encoding="utf-8")

            epic, _, _, _ = self.commit_progress.parse_active_ledger(root, "notes/epics/old.md")

        self.assertEqual(epic, "Reviewed Predecessor")

    def test_mixed_code_and_ledger_changes_are_not_docs(self) -> None:
        GitFile = self.commit_progress.GitFile
        files = [GitFile("M", "notes/roadmap.md"), GitFile("M", "src/widget.py"), GitFile("A", "notes/epics/next.md")]

        self.assertEqual(self.commit_progress.guess_area(files), "python")

    def test_commit_message_evidence_has_single_list_markers(self) -> None:
        GitFile = self.commit_progress.GitFile
        message = self.commit_progress.build_message(
            "Demo",
            "ship widget",
            ["- command: `pytest`", "result: pass", "notes: ok"],
            ["- reviewed-at: now", "result: pass", "notes: clean"],
            [GitFile("M", "src/widget.py")],
        )

        self.assertNotIn("- - command", message)
        self.assertIn("  - command: `pytest`", message)
        self.assertIn("    result: pass", message)

    def test_commit_message_discloses_workflow_state_files(self) -> None:
        GitFile = self.commit_progress.GitFile
        message = self.commit_progress.build_message(
            "Widget Core",
            "ship widget",
            ["- command: `pytest`", "result: pass", "notes: ok"],
            ["- reviewed-at: now", "result: pass", "notes: clean"],
            [GitFile("M", "src/widget.py"), GitFile("M", "notes/roadmap.md"), GitFile("??", "notes/epics/next.md")],
        )

        self.assertIn("Workflow state: roadmap or epic ledger updates included", message)

    def test_review_section_result_satisfies_commit_gate(self) -> None:
        errors = self.commit_progress.commit_gate_errors(
            ledger_path="notes/epics/2026-05-18-demo.md",
            active_epic_state="complete-pending-advance",
            ledger_text="ledger",
            verification=["- command: `pytest`", "result: pass", "notes: ok"],
            review=["- reviewed-at: 2026-07-11T11:00:00Z", "result: pass", "notes: clean"],
            open_loops=["none"],
        )

        self.assertEqual(errors, [])

    def test_legacy_review_result_still_satisfies_commit_gate(self) -> None:
        errors = self.commit_progress.commit_gate_errors(
            ledger_path="notes/epics/2026-05-18-demo.md",
            active_epic_state="active",
            ledger_text="ledger",
            verification=["- command: `pytest`", "result: pass", "notes: ok"],
            review=["- review-result: pass"],
            open_loops=["none"],
        )

        self.assertEqual(errors, [])

    def test_latest_review_result_wins_commit_gate(self) -> None:
        errors = self.commit_progress.commit_gate_errors(
            ledger_path="notes/epics/2026-05-18-demo.md",
            active_epic_state="complete-pending-advance",
            ledger_text="ledger",
            verification=["- command: `pytest`", "result: pass", "notes: ok"],
            review=["result: fail", "notes: fixed later", "result: pass", "notes: clean"],
            open_loops=["none"],
        )

        self.assertEqual(errors, [])

    def test_pending_review_blocks_commit_gate(self) -> None:
        errors = self.commit_progress.commit_gate_errors(
            ledger_path="notes/epics/2026-05-18-demo.md",
            active_epic_state="active",
            ledger_text="ledger",
            verification=["- command: `pytest`", "result: pass", "notes: ok"],
            review=["reviewed-at: not-run", "result: pending", "notes: not reviewed"],
            open_loops=["none"],
        )

        self.assertIn("review evidence indicates blocking or unresolved findings", errors)

    def test_actual_commit_requires_authority_source(self) -> None:
        self.assertEqual(
            self.commit_progress.commit_authorization_errors(True, True, None),
            ["actual commit requires --authorized-by exact-user-request|mode"],
        )
        self.assertEqual(self.commit_progress.commit_authorization_errors(True, True, "mode"), [])
        self.assertEqual(self.commit_progress.commit_authorization_errors(False, False, None), [])

    def test_commit_verification_entries_are_not_truncated(self) -> None:
        ledger = "# Demo\n\n## Verification Log\n\n" + "\n".join(
            f"- command: `check-{index}`\n  result: pass\n  notes: result {index}" for index in range(5)
        )

        lines = self.commit_progress.latest_verification_lines(ledger)

        self.assertEqual(lines[0], "- command: `check-2`")
        self.assertEqual(lines[-1], "notes: result 4")
        self.assertEqual(len(lines), 9)

    def test_review_entry_with_many_paths_is_not_truncated(self) -> None:
        paths = "\n".join(f"    - src/path-{index}.py" for index in range(60))
        ledger = (
            "# Demo\n\n## Review\n\n"
            "- reviewed-at: now\n"
            "  result: pass\n"
            "  review-id: 20260711T120000Z-a1b2c3d4\n"
            "  base-head: deadbeef\n"
            "  manifest: .deepdone/reviews/demo.json\n"
            "  paths:\n"
            f"{paths}\n"
            "  notes: no blocking findings\n"
        )

        lines = self.commit_progress.review_lines(ledger)

        self.assertIn("result: pass", lines)
        self.assertEqual(sum(line.startswith("- src/path-") for line in lines), 60)

    def test_blocker_words_in_reviewed_path_do_not_block(self) -> None:
        review = [
            "- reviewed-at: now",
            "result: pass",
            "paths:",
            "- tests/test_failed_login.py",
            "notes: no blocking findings",
        ]

        self.assertFalse(self.commit_progress.review_has_blocker(review))


if __name__ == "__main__":
    unittest.main()
