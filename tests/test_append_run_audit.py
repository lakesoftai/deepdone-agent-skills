from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deepdone-orchestrate" / "scripts" / "append_run_audit.py"


def load_append_run_audit():
    spec = importlib.util.spec_from_file_location("append_run_audit", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class AppendRunAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.audit = load_append_run_audit()

    def test_append_event_writes_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            event = {
                "state_before": "ready_to_implement",
                "skill_invoked": "deepdone-implement",
                "state_after": "needs_verification",
                "files_touched": ["src/auth.py"],
                "stop_reason": None,
            }

            path = self.audit.append_event(root, "20260518-143000", event)
            lines = path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0]), event)

    def test_rejects_bad_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                self.audit.append_event(Path(tmp), "../bad", {})

    def test_parse_files_requires_json_list(self) -> None:
        self.assertEqual(self.audit.parse_files('["a.py"]'), ["a.py"])
        with self.assertRaises(ValueError):
            self.audit.parse_files('"a.py"')


if __name__ == "__main__":
    unittest.main()
