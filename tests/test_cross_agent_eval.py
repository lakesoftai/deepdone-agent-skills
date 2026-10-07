from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "evals/run_cross_agent.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("deepdone_cross_agent_eval_test", RUNNER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class CrossAgentEvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = load_runner()

    def prepare_lifecycle(self, root: Path, source: str) -> tuple[dict, Path]:
        self.runner.init_repo(root)
        state = self.runner.seed_active(root)
        self.runner.write(root / "src/calc.py", source)
        self.runner.write(
            root / "notes/epics/current.md",
            self.runner.passing_ledger(state["base"], ["src/", "tests/"]),
        )
        manifest = self.runner.capture_manifest(root, "notes/epics/current.md")
        return state, root / manifest

    def test_lifecycle_accepts_valid_behavior_and_review_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state, _ = self.prepare_lifecycle(
                root, "def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b\n",
            )
            before = self.runner.git(root, "write-tree").stdout
            self.assertEqual(self.runner.grade_lifecycle(root, state), [])
            self.assertEqual(self.runner.git(root, "write-tree").stdout, before)
            self.assertEqual(self.runner.git(root, "rev-parse", "HEAD").stdout.strip(), state["base"])

    def test_lifecycle_rejects_incorrect_behavior_despite_valid_review(self) -> None:
        for add, subtract in (
            ("a + b", "a + b"),
            ("a - b", "a - b"),
            ("a + b", '(_ for _ in ()).throw(RuntimeError("broken implementation"))'),
        ):
            with self.subTest(add=add, subtract=subtract), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                state, _ = self.prepare_lifecycle(
                    root, f"def add(a, b):\n    return {add}\n\ndef subtract(a, b):\n    return {subtract}\n",
                )
                errors = self.runner.grade_lifecycle(root, state)
                self.assertTrue(any("behavior" in error for error in errors), errors)

    def test_lifecycle_rejects_invalid_manifest_with_working_code(self) -> None:
        for content in ("{}", "[]", "not json"):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                state, manifest = self.prepare_lifecycle(
                    root, "def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b\n",
                )
                manifest.write_text(content, encoding="utf-8")
                errors = self.runner.grade_lifecycle(root, state)
                self.assertTrue(any("review" in error.lower() for error in errors), errors)

    def test_lifecycle_rejects_stale_or_unrelated_review(self) -> None:
        for mutation in ("code", "ledger", "ref", "ledger-path", "scope"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = "def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b\n"
                state, manifest_path = self.prepare_lifecycle(root, source)
                manifest = json.loads(manifest_path.read_text())
                if mutation == "code":
                    self.runner.write(root / "src/calc.py", source + "\n# changed after review\n")
                elif mutation == "ledger":
                    ledger = root / "notes/epics/current.md"
                    ledger.write_text(ledger.read_text().replace("notes: ok", "notes: changed evidence"))
                elif mutation == "ref":
                    self.runner.git(root, "update-ref", "-d", manifest["review_ref"])
                elif mutation == "ledger-path":
                    manifest["ledger_path"] = "notes/epics/other.md"
                    manifest_path.write_text(json.dumps(manifest))
                else:
                    # A valid snapshot of another file cannot vouch for calc.py.
                    manifest_path.unlink()
                    self.runner.git(root, "update-ref", "-d", manifest["review_ref"])
                    self.runner.write(root / "tests/test_calc.py", "# unrelated change\n")
                    self.runner.write(root / "notes/epics/current.md", self.runner.passing_ledger(state["base"], ["tests/"]))
                    self.runner.capture_manifest(root, "notes/epics/current.md")
                self.assertTrue(self.runner.grade_lifecycle(root, state))

    def test_scenario_registry_covers_required_behaviors(self) -> None:
        names = {scenario.name for scenario in self.runner.scenarios()}
        self.assertEqual(
            names,
            {
                "skill-discovery",
                "natural-language-one-step-intake",
                "implement-verify-review",
                "review-fail-fix-verify-review",
                "end-to-end-one-commit-no-advance",
                "state-label-no-commit-authority",
                "unrelated-unstaged-excluded",
                "changed-reviewed-path-blocks",
                "unrelated-staged-path-blocks",
                "dirty-reviewed-set-blocks-advance",
                "merge-evidence-no-archive-authority",
            },
        )

    def test_every_scenario_builds_disposable_fixture(self) -> None:
        for scenario in self.runner.scenarios():
            with self.subTest(scenario=scenario.name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.runner.init_repo(root)
                state = scenario.seed(root)

                self.assertIn("base", state)
                self.assertTrue((root / ".git").is_dir())
                self.assertTrue((root / ".agents/skills/deepdone/SKILL.md").is_file())
                self.assertTrue((root / ".claude/skills/deepdone/SKILL.md").is_file())
                expected = {"deepdone"}
                if scenario.name == "skill-discovery":
                    expected.add("deepdone-eval-probe")
                for base in (root / ".agents/skills", root / ".claude/skills"):
                    discovered = {path.parent.name for path in base.glob("deepdone*/SKILL.md")}
                    self.assertEqual(discovered, expected)

    def test_codex_adapter_is_ephemeral_and_project_scoped(self) -> None:
        command = self.runner.adapter_command("codex", Path("/tmp/fixture"), "prompt", Path("/tmp/final.json"), "model-x", 1.0)
        self.assertIn("--ephemeral", command)
        self.assertIn("--ignore-user-config", command)
        self.assertIn("workspace-write", command)
        self.assertIn("--output-schema", command)
        self.assertIn("model-x", command)

    def test_claude_adapter_loads_project_settings_only(self) -> None:
        command = self.runner.adapter_command("claude", Path("/tmp/fixture"), "Use $deepdone.", Path("/tmp/final.json"), "model-y", 1.0)
        joined = " ".join(command)
        self.assertIn("--setting-sources project", joined)
        self.assertIn("--no-session-persistence", command)
        self.assertIn("--json-schema", command)
        self.assertIn("model-y", command)
        self.assertIn("Use /deepdone.", command)


if __name__ == "__main__":
    unittest.main()
