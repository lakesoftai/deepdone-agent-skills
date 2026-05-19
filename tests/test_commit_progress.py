from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deepdone-commit" / "scripts" / "commit_progress.py"


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


if __name__ == "__main__":
    unittest.main()
