from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "deepdone" / "scripts" / "inspect_deepdone_state.py"


def load_inspect_deepdone_state():
    spec = importlib.util.spec_from_file_location("inspect_deepdone_state", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class InspectDeepDoneStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.inspect = load_inspect_deepdone_state()

    def test_parse_active_epic_reads_state(self) -> None:
        roadmap = (
            "# Roadmap\n\n"
            "## Active Epic\n\n"
            "- name: demo\n"
            "- ledger: notes/epics/2026-05-18-demo.md\n"
            "- state: blocked\n"
        )

        self.assertEqual(
            self.inspect.parse_active_epic(roadmap),
            {
                "name": "demo",
                "ledger": "notes/epics/2026-05-18-demo.md",
                "state": "blocked",
            },
        )

    def test_safe_rel_rejects_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            self.assertIsNone(self.inspect.safe_rel(root, "../outside.md"))
            self.assertEqual(self.inspect.safe_rel(root, "notes/roadmap.md"), root / "notes" / "roadmap.md")

    def test_structured_verification_lines_are_returned(self) -> None:
        ledger = (
            "# Demo\n\n"
            "## Verification Log\n\n"
            "- command: `pytest`\n"
            "  result: pass\n"
            "  notes: ok\n"
        )

        self.assertEqual(
            self.inspect.latest_verification_lines(ledger),
            ["- command: `pytest`", "result: pass", "notes: ok"],
        )

    def test_verification_entries_are_not_truncated_mid_entry(self) -> None:
        ledger = "# Demo\n\n## Verification Log\n\n" + "\n".join(
            f"- command: `check-{index}`\n  result: pass\n  notes: result {index}" for index in range(5)
        )

        lines = self.inspect.latest_verification_lines(ledger)

        self.assertEqual(lines[0], "- command: `check-2`")
        self.assertEqual(lines[-1], "notes: result 4")
        self.assertEqual(len(lines), 9)

    def test_legacy_ledger_without_review_is_pending(self) -> None:
        ledger = "# Demo\n\n## Status\n\nactive\n"

        self.assertEqual(self.inspect.latest_review_lines(ledger), [])
        self.assertEqual(self.inspect.latest_review_result(ledger), "pending")

    def test_latest_review_result_wins(self) -> None:
        ledger = (
            "# Demo\n\n"
            "## Review\n\n"
            "- reviewed-at: 2026-07-11T10:00:00Z\n"
            "  result: fail\n"
            "  notes: one finding\n"
            "- reviewed-at: 2026-07-11T11:00:00Z\n"
            "  result: pass\n"
            "  notes: fixed\n"
        )

        self.assertEqual(self.inspect.latest_review_result(ledger), "pass")

    def test_finds_one_reviewed_complete_single_epic(self) -> None:
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

            found = self.inspect.find_obvious_active_ledger(root)

        self.assertEqual(found, ledger)

    def test_archive_only_dirty_state_is_not_unowned_work(self) -> None:
        self.assertTrue(
            self.inspect.only_lifecycle_state_changes(
                [
                    " M notes/roadmap.md",
                    " D notes/epics/2026-07-11-demo.md",
                    "?? notes/archive/epics/2026-07-11-demo.md",
                ]
            )
        )
        self.assertFalse(self.inspect.only_lifecycle_state_changes([" M src/app.py"]))

    def test_invalid_roadmap_ledger_is_not_hidden_by_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fallback = root / "notes" / "epics" / "fallback.md"
            fallback.parent.mkdir(parents=True)
            fallback.write_text("# Fallback\n\n## Status\n\nactive\n", encoding="utf-8")

            invalid = self.inspect.safe_rel(root, "notes/epics/missing.md")
            found = self.inspect.find_obvious_active_ledger(root)

        self.assertIsNotNone(invalid)
        self.assertFalse(invalid.exists())
        self.assertEqual(found, fallback)


if __name__ == "__main__":
    unittest.main()
