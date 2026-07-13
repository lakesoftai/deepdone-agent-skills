from __future__ import annotations

import importlib.util
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
                self.assertTrue((root / ".agents/skills/deepdone-orchestrate/SKILL.md").is_file())
                self.assertTrue((root / ".claude/skills/deepdone-orchestrate/SKILL.md").is_file())
                expected = {"deepdone-orchestrate", "deepdone-advance"}
                if scenario.name == "skill-discovery":
                    expected.add("deepdone-eval-probe")
                for base in (root / ".agents/skills", root / ".claude/skills"):
                    discovered = {path.parent.name for path in base.glob("deepdone-*/SKILL.md")}
                    self.assertEqual(discovered, expected)

    def test_codex_adapter_is_ephemeral_and_project_scoped(self) -> None:
        command = self.runner.adapter_command("codex", Path("/tmp/fixture"), "prompt", Path("/tmp/final.json"), "model-x", 1.0)
        self.assertIn("--ephemeral", command)
        self.assertIn("--ignore-user-config", command)
        self.assertIn("workspace-write", command)
        self.assertIn("--output-schema", command)
        self.assertIn("model-x", command)

    def test_claude_adapter_loads_project_settings_only(self) -> None:
        command = self.runner.adapter_command("claude", Path("/tmp/fixture"), "Use $deepdone-orchestrate.", Path("/tmp/final.json"), "model-y", 1.0)
        joined = " ".join(command)
        self.assertIn("--setting-sources project", joined)
        self.assertIn("--no-session-persistence", command)
        self.assertIn("--json-schema", command)
        self.assertIn("model-y", command)
        self.assertIn("Use /deepdone-orchestrate.", command)


if __name__ == "__main__":
    unittest.main()
