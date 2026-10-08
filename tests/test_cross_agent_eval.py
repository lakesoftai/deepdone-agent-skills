from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
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

    def prepare_lifecycle(self, root: Path, source: str, files: dict[str, str] | None = None) -> tuple[dict, Path]:
        self.runner.init_repo(root)
        state = self.runner.seed_active(root)
        self.runner.write(root / "src/calc.py", source)
        for name, content in (files or {}).items():
            self.runner.write(root / name, content)
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

    def test_lifecycle_accepts_project_and_relative_imports(self) -> None:
        for module in ("src.arithmetic", ".arithmetic"):
            with self.subTest(module=module), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                state, _ = self.prepare_lifecycle(
                    root,
                    f"from {module} import difference\n\ndef add(a, b):\n    return a + b\n"
                    "\ndef subtract(a, b):\n    return difference(a, b)\n",
                    {
                        "src/arithmetic.py": "def difference(a, b):\n    return a - b\n",
                        "tests/test_calc.py": "import unittest\nfrom src.calc import add, subtract\n\n"
                        "class CalcTests(unittest.TestCase):\n"
                        "    def test_arithmetic(self):\n"
                        "        self.assertEqual(add(2, 7), 9)\n"
                        "        self.assertEqual(subtract(2, 7), -5)\n",
                    },
                )
                native = self.runner.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests"], root)
                self.assertEqual(native.returncode, 0, native.stderr)
                self.assertEqual(self.runner.grade_lifecycle(root, state), [])

    def test_lifecycle_rejects_missing_function_or_dependency(self) -> None:
        for source in (
            "# subtract is missing\ndef add(a, b):\n    return a + b\n",
            "from src.missing_dependency import subtract\ndef add(a, b):\n    return a + b\n",
        ):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                state, _ = self.prepare_lifecycle(root, source)
                self.assertTrue(any("behavior check failed" in error for error in self.runner.grade_lifecycle(root, state)))

    def test_lifecycle_reports_behavior_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state, _ = self.prepare_lifecycle(root, "def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b\n")
            original_run = self.runner.run

            def timeout_behavior(command, cwd, **kwargs):
                if "-I" in command:
                    self.assertEqual(kwargs["timeout"], 10)
                    raise subprocess.TimeoutExpired(command, kwargs["timeout"])
                return original_run(command, cwd, **kwargs)

            with patch.object(self.runner, "run", side_effect=timeout_behavior):
                errors = self.runner.grade_lifecycle(root, state)
            self.assertTrue(any("behavior check could not complete" in error for error in errors), errors)

    def test_trial_records_malformed_ledger_as_failed_grade(self) -> None:
        scenario = next(item for item in self.runner.scenarios() if item.name == "implement-verify-review")
        original_run = self.runner.run
        with tempfile.TemporaryDirectory() as tmp:
            for trial, corruption in enumerate(("encoding", "directory", "missing"), 1):
                with self.subTest(corruption=corruption):
                    def fake_agent(command, cwd, **kwargs):
                        if command[0] == "codex":
                            ledger = cwd / "notes/epics/current.md"
                            if corruption == "encoding":
                                ledger.write_bytes(b"\xff")
                            else:
                                ledger.unlink()
                                if corruption == "directory":
                                    ledger.mkdir()
                            return subprocess.CompletedProcess(command, 0, "stub agent completed", "")
                        return original_run(command, cwd, **kwargs)

                    with patch.object(self.runner, "run", side_effect=fake_agent):
                        report = self.runner.run_trial("codex", scenario, trial, Path(tmp), None, 1.0, 30)
                    self.assertFalse(report["passed"])
                    self.assertTrue(any("ledger" in error for error in report["errors"]), report)
                    stored = json.loads((Path(report["artifact"]) / "grade.json").read_text())
                    self.assertEqual(stored, report)

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
        for mutation in ("code", "ledger", "ref", "ledger-path", "scope", "head", "staged"):
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
                elif mutation == "head":
                    self.runner.commit_all(root, "unexpected commit")
                elif mutation == "staged":
                    self.runner.write(root / "scratch.txt", "user-owned work\n")
                    self.runner.git(root, "add", "scratch.txt")
                else:
                    # A valid snapshot of another file cannot vouch for calc.py.
                    manifest_path.unlink()
                    self.runner.git(root, "update-ref", "-d", manifest["review_ref"])
                    self.runner.write(root / "tests/test_calc.py", "# unrelated change\n")
                    ledger = root / "notes/epics/current.md"
                    ledger.write_text(ledger.read_text().replace("      - src/\n", ""))
                    verification = self.runner.commit_progress.verification_evidence
                    contract = verification.read_contract(ledger.read_text(), "notes/epics/current.md")
                    current, _ = verification.inventory(root, "notes/epics/current.md", contract)
                    check = current["checks"][0]
                    check["inputs"] = [{"path": "tests", "role": "source"}]
                    check["argv"] = [sys.executable, "-I", "-B", "-c", "compile(open('tests/test_calc.py').read(), 'test_calc', 'exec')"]
                    verification.initialize(root, "notes/epics/current.md", [check], "Negative fixture reviews only tests")
                    verification.run_check(root, "notes/epics/current.md", check["id"])
                    script = root / ".agents/skills/deepdone/scripts/capture_reviewed_change_set.py"
                    self.runner.run([sys.executable, str(script), "--ledger", "notes/epics/current.md"], root, check=True)
                errors = self.runner.grade_lifecycle(root, state)
                self.assertTrue(errors)
                if mutation == "head":
                    self.assertIn("lifecycle changed HEAD before authorized commit", errors)
                elif mutation == "staged":
                    self.assertIn("staged paths exist outside reviewed change set", errors)
                    self.assertEqual(self.runner.git(root, "diff", "--cached", "--name-only").stdout.strip(), "scratch.txt")

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
