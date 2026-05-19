from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deepdone-orchestrate" / "scripts" / "inspect_deepdone_state.py"


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


if __name__ == "__main__":
    unittest.main()
