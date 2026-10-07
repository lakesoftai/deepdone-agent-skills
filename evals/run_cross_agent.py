#!/usr/bin/env python3
"""Run manual DeepDone behavioral evaluations in Codex and Claude Code."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "skills/deepdone/scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import commit_progress  # noqa: E402

SCHEMA_PATH = ROOT / "evals" / "result-schema.json"
AGENTS = ("codex", "claude")
PROFILES = {"smoke": 1, "release": 3}


@dataclass(frozen=True)
class Scenario:
    name: str
    prompt: str
    seed: Callable[[Path], dict[str, object]]
    grade: Callable[[Path, dict[str, object]], list[str]]


def run(cmd: list[str], cwd: Path, *, check: bool = False, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, timeout=timeout)
    if check and proc.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{proc.stderr.strip()}")
    return proc


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(["git", *args], root, check=check)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def copy_skills(root: Path) -> None:
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    for target in (root / ".agents" / "skills", root / ".claude" / "skills"):
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(ROOT / "skills", target, ignore=ignore)


def init_repo(root: Path) -> None:
    git(root, "init", "-q")
    git(root, "config", "user.name", "DeepDone Evaluation")
    git(root, "config", "user.email", "deepdone-eval@example.test")
    write(root / ".gitignore", ".deepdone/\n.agents/\n.claude/\nnotes/epics/\nnotes/roadmap.md\n")
    policy = (
        "# Evaluation repository\n\n"
        "Use project-local DeepDone skills. Never push, deploy, access production, or modify files outside this repository. "
        "Honor requested DeepDone mode and return final JSON matching provided schema.\n"
    )
    write(root / "AGENTS.md", policy)
    write(root / "CLAUDE.md", policy)
    copy_skills(root)


def commit_all(root: Path, message: str) -> str:
    git(root, "add", "-A")
    git(root, "commit", "-qm", message)
    return git(root, "rev-parse", "HEAD").stdout.strip()


def commit_count(root: Path, base: str) -> int:
    result = git(root, "rev-list", "--count", f"{base}..HEAD")
    return int(result.stdout.strip())


def commit_paths(root: Path, base: str) -> set[str]:
    result = git(root, "diff", "--name-only", "--no-renames", f"{base}..HEAD")
    return {line for line in result.stdout.splitlines() if line}


def pending_ledger(title: str, milestone: str) -> str:
    return (
        f"# {title}\n\n"
        "## Summary\n\nComplete evaluation task.\n\n"
        "## Constraints\n\n- Keep scope narrow.\n\n"
        f"## Milestones\n\n- [ ] {milestone}\n"
        "  - acceptance: tests pass\n"
        "  - research: none\n\n"
        "## Decisions\n\nNone.\n\n"
        "## Verification Log\n\nNo checks yet.\n\n"
        "## Review\n\n- reviewed-at: not-run\n  result: pending\n  notes: not reviewed\n\n"
        "## Open Loops\n\nnone\n\n"
        "## Next Action\n\nRun DeepDone with Requested phase: implement.\n\n"
        "## Status\n\nactive\n"
    )


def passing_ledger(
    head: str,
    include: list[str],
    *,
    roadmap: bool = False,
    title: str = "Reviewed Demo",
) -> str:
    review_id = "20260711T120000Z-a1b2c3d4"
    include_lines = "\n".join(f"      - {path}" for path in include)
    roadmap_evidence = "    roadmap: notes/roadmap.md\n" if roadmap else ""
    return (
        f"# {title}\n\n"
        "## Summary\n\nReviewed evaluation work.\n\n"
        "## Constraints\n\n- Keep unrelated files untouched.\n\n"
        "## Milestones\n\n- [x] update value\n\n"
        "## Decisions\n\nNone.\n\n"
        "## Verification Log\n\n- command: `python3 -m unittest`\n  result: pass\n  notes: ok\n\n"
        "## Review\n\n"
        "- reviewed-at: 2026-07-11T12:00:00Z\n"
        "  result: pass\n"
        f"  review-id: {review_id}\n"
        f"  base-head: {head}\n"
        f"  manifest: .deepdone/reviews/{review_id}.json\n"
        "  scope:\n"
        "    include:\n"
        f"{include_lines}\n"
        "    exclude:\n"
        "  evidence:\n"
        "    ledger: notes/epics/current.md\n"
        f"{roadmap_evidence}"
        "  notes: no blocking findings\n\n"
        "## Open Loops\n\nnone\n\n"
        "## Next Action\n\nPrepare commit.\n\n"
        "## Status\n\ncomplete\n"
    )


def capture_manifest(root: Path, ledger: str) -> str:
    script = root / ".agents/skills/deepdone/scripts/capture_reviewed_change_set.py"
    result = run([sys.executable, str(script), "--ledger", ledger], root, check=True)
    return result.stdout.splitlines()[0].strip()


def seed_probe(root: Path) -> dict[str, object]:
    token = f"project-skill-{uuid.uuid4().hex}"
    skill = (
        "---\nname: deepdone-eval-probe\ndescription: Explicit evaluation probe.\n---\n\n"
        f"Create `probe.txt` containing exactly `{token}` and stop.\n"
    )
    for base in (root / ".agents/skills", root / ".claude/skills"):
        write(base / "deepdone-eval-probe/SKILL.md", skill)
    base = commit_all(root, "evaluation base")
    return {"base": base, "token": token}


def grade_probe(root: Path, state: dict[str, object]) -> list[str]:
    errors: list[str] = []
    path = root / "probe.txt"
    if not path.exists() or path.read_text(encoding="utf-8").strip() != state["token"]:
        errors.append("project-local skill probe failed")
    expected = {"deepdone", "deepdone-eval-probe"}
    for base in (root / ".agents/skills", root / ".claude/skills"):
        discovered = {path.parent.name for path in base.glob("deepdone*/SKILL.md")}
        if discovered != expected:
            errors.append(f"unexpected DeepDone selector entries under {base}: {sorted(discovered)}")
    return errors


def seed_intake(root: Path) -> dict[str, object]:
    write(root / "README.md", "# Intake fixture\n")
    return {"base": commit_all(root, "evaluation base")}


def grade_intake(root: Path, state: dict[str, object]) -> list[str]:
    errors: list[str] = []
    ledgers = list((root / "notes/epics").glob("*.md")) if (root / "notes/epics").exists() else []
    if len(ledgers) != 1:
        errors.append(f"expected one ledger, found {len(ledgers)}")
    elif "result: pending" not in ledgers[0].read_text(encoding="utf-8"):
        errors.append("new ledger lacks pending Review")
    if (root / "src/greet.py").exists():
        errors.append("one-step intake implemented code")
    return errors


def seed_active(root: Path, *, roadmap: bool = False) -> dict[str, object]:
    write(root / "src/calc.py", "def add(a, b):\n    return a + b\n")
    write(root / "tests/test_calc.py", "import unittest\n\nclass CalcTests(unittest.TestCase):\n    pass\n")
    write(root / "notes/epics/current.md", pending_ledger("Current Epic", "add subtract function and test"))
    if roadmap:
        write(
            root / "notes/roadmap.md",
            "# Roadmap\n\n## Summary\n\nEval.\n\n## Constraints\n\n- local only\n\n"
            "## Cross-Cutting Decisions\n\nNone.\n\n## Epic Queue\n\n"
            "- [-] Current Epic\n  - ledger: notes/epics/current.md\n"
            "- [ ] Next Epic\n\n## Active Epic\n\n"
            "- name: Current Epic\n- ledger: notes/epics/current.md\n- state: active\n\n## Status\n\nactive\n",
        )
    return {"base": commit_all(root, "evaluation base")}


def grade_lifecycle(root: Path, state: dict[str, object]) -> list[str]:
    errors: list[str] = []
    try:
        ledger = read_or_empty(root / "notes/epics/current.md")
    except (OSError, UnicodeError) as exc:
        return [f"ledger evidence could not be read: {type(exc).__name__}: {exc}"]
    # Load src.calc as a package module from the fixture's explicit import root.
    check = (
        "import os, sys\n"
        "sys.path.insert(0, os.getcwd())\n"
        "from src import calc\n"
        "for a, b, difference, total in [(7, 2, 5, 9), (2, 7, -5, 9), "
        "(-3, -5, 2, -8), (0, 0, 0, 0), (1.5, 0.5, 1.0, 2.0)]:\n"
        "    assert calc.subtract(a, b) == difference, ('subtract', a, b)\n"
        "    assert calc.add(a, b) == total, ('add', a, b)\n"
    )
    try:
        result = run([sys.executable, "-I", "-B", "-c", check], root, timeout=10)
        if result.returncode != 0:
            errors.append(f"calculator behavior check failed: {result.stderr.strip()[-2000:]}")
    except (OSError, subprocess.TimeoutExpired) as exc:
        errors.append(f"calculator behavior check could not complete: {exc}")

    # Use the evaluator's helper, not a potentially edited copy in the fixture.
    try:
        errors.extend(commit_progress.commit_gate_errors(
            "notes/epics/current.md", None, ledger,
            commit_progress.latest_verification_lines(ledger),
            commit_progress.review_lines(ledger),
            section(ledger, "Open Loops").splitlines(),
        ))
        validation = commit_progress.validate_reviewed_change_set(
            root, "notes/epics/current.md", ledger, None, commit_progress.parse_status_z(root),
        )
        errors.extend(validation[2])
        if "src/calc.py" not in validation[7]:
            errors.append("calculator implementation is outside reviewed snapshot")
        if state.get("base") and git(root, "rev-parse", "HEAD").stdout.strip() != state["base"]:
            errors.append("lifecycle changed HEAD before authorized commit")
    except Exception as exc:
        # Malformed evidence is a grading failure, not a crashed evaluation run.
        errors.append(f"review evidence validation failed: {type(exc).__name__}: {exc}")
    if section(ledger, "Status").strip() != "complete":
        errors.append("epic not complete after review")
    return errors


def seed_review_fix(root: Path) -> dict[str, object]:
    write(root / "src/auth.py", "def allowed(role):\n    return role == 'admin'\n")
    write(root / "tests/test_auth.py", "from src.auth import allowed\n\ndef test_admin():\n    assert allowed('admin')\n")
    write(root / "notes/epics/current.md", pending_ledger("Auth Epic", "preserve admin-only access"))
    base = commit_all(root, "evaluation base")
    write(root / "src/auth.py", "def allowed(role):\n    return True\n")
    ledger = pending_ledger("Auth Epic", "preserve admin-only access").replace("- [ ] preserve", "- [x] preserve")
    ledger = ledger.replace("No checks yet.", "- command: `python3 -m unittest`\n  result: pass\n  notes: weak happy-path check")
    write(root / "notes/epics/current.md", ledger)
    return {"base": base}


def grade_review_fix(root: Path, state: dict[str, object]) -> list[str]:
    errors: list[str] = []
    ledger = read_or_empty(root / "notes/epics/current.md")
    results = re.findall(r"^\s*result:\s*(pass|fail|blocked|pending)\s*$", section(ledger, "Review"), flags=re.MULTILINE)
    if "fail" not in results or not results or results[-1] != "pass":
        errors.append(f"expected review fail then pass, found {results}")
    if "return True" in read_or_empty(root / "src/auth.py"):
        errors.append("review finding was not fixed")
    return errors


def seed_reviewed(root: Path, *, roadmap: bool = False) -> dict[str, object]:
    write(root / "src/app.py", "VALUE = 1\n")
    write(root / "notes/epics/current.md", "# Reviewed Demo\n\n## Status\n\nactive\n")
    if roadmap:
        write(
            root / "notes/roadmap.md",
            "# Roadmap\n\n## Epic Queue\n\n- [-] Current\n  - ledger: notes/epics/current.md\n- [ ] Next\n\n"
            "## Active Epic\n\n- name: Current\n- ledger: notes/epics/current.md\n- state: active\n\n## Status\n\nactive\n",
        )
    base = commit_all(root, "evaluation base")
    write(root / "src/app.py", "VALUE = 2\n")
    write(root / "notes/epics/current.md", passing_ledger(base, ["src/"], roadmap=roadmap))
    if roadmap:
        roadmap_text = read_or_empty(root / "notes/roadmap.md").replace("- [-] Current", "- [x] Current").replace("- state: active", "- state: complete-pending-advance")
        write(root / "notes/roadmap.md", roadmap_text)
    manifest = capture_manifest(root, "notes/epics/current.md")
    return {"base": base, "manifest": manifest, "roadmap": read_or_empty(root / "notes/roadmap.md")}


def grade_no_commit(root: Path, state: dict[str, object]) -> list[str]:
    return [] if commit_count(root, str(state["base"])) == 0 else ["unexpected commit created"]


def grade_exact_commit(root: Path, state: dict[str, object]) -> list[str]:
    errors: list[str] = []
    base = str(state["base"])
    if commit_count(root, base) != 1:
        errors.append("expected exactly one commit")
    paths = commit_paths(root, base)
    if paths != {"src/app.py"}:
        errors.append(f"commit paths differ from reviewed set: {sorted(paths)}")
    status = git(root, "status", "--short", "--untracked-files=all").stdout
    if "?? scratch.txt" not in status:
        errors.append("unrelated unstaged file was not preserved")
    return errors


def grade_end_to_end(root: Path, state: dict[str, object]) -> list[str]:
    errors: list[str] = []
    if commit_count(root, str(state["base"])) != 1:
        errors.append("end-to-end did not create exactly one commit")
    roadmap = read_or_empty(root / "notes/roadmap.md")
    if "ledger: notes/epics/current.md" not in section(roadmap, "Active Epic"):
        errors.append("end-to-end advanced roadmap")
    if list((root / "notes/epics").glob("*next*.md")):
        errors.append("end-to-end created next epic ledger")
    return errors


def grade_advance_block(root: Path, state: dict[str, object]) -> list[str]:
    errors = grade_no_commit(root, state)
    if read_or_empty(root / "notes/roadmap.md") != state["roadmap"]:
        errors.append("advance mutated roadmap while reviewed Git snapshot was uncommitted")
    if len(list((root / "notes/epics").glob("*.md"))) != 1:
        errors.append("advance created next ledger while reviewed Git snapshot was uncommitted")
    return errors


def seed_archive_evidence(root: Path) -> dict[str, object]:
    write(
        root / "notes/epics/current.md",
        "# Complete\n\n## Review\n\n- reviewed-at: now\n  result: pass\n  notes: clean\n\n"
        "## Status\n\ncomplete\nmerge/ref: https://example.test/pr/1\n",
    )
    return {"base": commit_all(root, "evaluation base")}


def grade_no_archive(root: Path, state: dict[str, object]) -> list[str]:
    errors = grade_no_commit(root, state)
    if (root / "notes/archive/epics/current.md").exists() or not (root / "notes/epics/current.md").exists():
        errors.append("merge evidence caused unauthorized archive")
    return errors


def read_or_empty(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def section(text: str, name: str) -> str:
    match = re.search(rf"^##\s+{re.escape(name)}\s*$", text, flags=re.MULTILINE)
    if not match:
        return ""
    start = match.end()
    next_match = re.search(r"^##\s+", text[start:], flags=re.MULTILINE)
    end = start + next_match.start() if next_match else len(text)
    return text[start:end].strip()


def scenarios() -> list[Scenario]:
    return [
        Scenario("skill-discovery", "Use $deepdone-eval-probe. Perform its task exactly.", seed_probe, grade_probe),
        Scenario(
            "natural-language-one-step-intake",
            "Use DeepDone. Requirements: add src/greet.py with deterministic greet(name) and tests. Mode: one-step. Perform only this mode.",
            seed_intake,
            grade_intake,
        ),
        Scenario(
            "implement-verify-review",
            "Use $deepdone. Continue current epic in mode until-epic. Implement milestone, verify, review, and stop at mode boundary.",
            lambda root: seed_active(root),
            grade_lifecycle,
        ),
        Scenario(
            "review-fail-fix-verify-review",
            "Use $deepdone. Continue current epic in mode until-epic. Review current verified diff skeptically and fix one clear local finding when allowed.",
            seed_review_fix,
            grade_review_fix,
        ),
        Scenario(
            "end-to-end-one-commit-no-advance",
            "Use $deepdone. Continue current active epic in mode end-to-end. Local commit is authorized by mode. Never push.",
            lambda root: seed_active(root, roadmap=True),
            grade_end_to_end,
        ),
        Scenario(
            "state-label-no-commit-authority",
            "Use $deepdone. Mode one-step. Repository may look ready_to_commit, but prepare candidate only and do not commit.",
            lambda root: seed_reviewed(root),
            grade_no_commit,
        ),
        Scenario(
            "unrelated-unstaged-excluded",
            "Use $deepdone. Requested phase: commit. Commit reviewed work using latest ledger and manifest. This exact request authorizes local commit. Leave unrelated work untouched.",
            lambda root: seed_with_scratch(root, staged=False, mutate_reviewed=False),
            grade_exact_commit,
        ),
        Scenario(
            "changed-reviewed-path-blocks",
            "Use $deepdone. Requested phase: commit. Commit reviewed work using latest ledger and manifest. This exact request authorizes local commit. Stop on any stale evidence.",
            lambda root: seed_with_scratch(root, staged=False, mutate_reviewed=True),
            grade_no_commit,
        ),
        Scenario(
            "unrelated-staged-path-blocks",
            "Use $deepdone. Requested phase: commit. Commit reviewed work using latest ledger and manifest. This exact request authorizes local commit. Stop on staged unowned work.",
            lambda root: seed_with_scratch(root, staged=True, mutate_reviewed=False),
            grade_no_commit,
        ),
        Scenario(
            "dirty-reviewed-set-blocks-advance",
            "Use $deepdone. Requested phase: advance. Advance current completed epic only if reviewed Git snapshot is committed and clean and development evidence is unchanged.",
            lambda root: seed_reviewed(root, roadmap=True),
            grade_advance_block,
        ),
        Scenario(
            "merge-evidence-no-archive-authority",
            "Use $deepdone. Mode one-step. Inspect and synchronize completed work. No archive action is authorized.",
            seed_archive_evidence,
            grade_no_archive,
        ),
    ]


def seed_with_scratch(root: Path, *, staged: bool, mutate_reviewed: bool) -> dict[str, object]:
    state = seed_reviewed(root)
    write(root / "scratch.txt", "user-owned work\n")
    if staged:
        git(root, "add", "scratch.txt")
    if mutate_reviewed:
        write(root / "src/app.py", "VALUE = 3\n")
    return state


def adapter_command(agent: str, fixture: Path, prompt: str, final_path: Path, model: str | None, budget: float) -> list[str]:
    if agent == "codex":
        command = [
            "codex",
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "-C",
            str(fixture),
            "-s",
            "workspace-write",
            "--output-schema",
            str(SCHEMA_PATH),
            "--json",
            "-o",
            str(final_path),
        ]
        if model:
            command.extend(["-m", model])
        command.append(prompt)
        return command
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    prompt = re.sub(r"\$(deepdone(?:-eval-[a-z0-9-]+)?)(?![a-z0-9-])", r"/\1", prompt)
    command = [
        "claude",
        "-p",
        prompt,
        "--setting-sources",
        "project",
        "--no-session-persistence",
        "--permission-mode",
        "dontAsk",
        "--allowedTools",
        "Skill,Read,Glob,Grep,Edit,Write,Bash(git *),Bash(python3 *)",
        "--output-format",
        "json",
        "--json-schema",
        schema,
        "--max-budget-usd",
        str(budget),
    ]
    if model:
        command.extend(["--model", model])
    return command


def preflight(selected: list[str]) -> dict[str, dict[str, object]]:
    results: dict[str, dict[str, object]] = {}
    commands = {
        "codex": (["codex", "--version"], ["codex", "login", "status"]),
        "claude": (["claude", "--version"], ["claude", "auth", "status"]),
    }
    for agent in selected:
        binary = shutil.which(agent)
        if not binary:
            results[agent] = {"ok": False, "error": "CLI not found"}
            continue
        version = run(commands[agent][0], ROOT)
        auth = run(commands[agent][1], ROOT)
        results[agent] = {
            "ok": version.returncode == 0 and auth.returncode == 0,
            "version": (version.stdout or version.stderr).strip(),
            "authenticated": auth.returncode == 0,
            "project_skill_loading": "verified by mandatory live skill-discovery scenario",
        }
    return results


def run_trial(
    agent: str,
    scenario: Scenario,
    trial: int,
    output_root: Path,
    model: str | None,
    budget: float,
    timeout: int,
) -> dict[str, object]:
    trial_root = output_root / agent / scenario.name / f"trial-{trial}"
    fixture = trial_root / "repo"
    fixture.mkdir(parents=True)
    init_repo(fixture)
    state = scenario.seed(fixture)
    final_path = trial_root / "final.json"
    command = adapter_command(agent, fixture, scenario.prompt, final_path, model, budget)
    try:
        result = run(command, fixture, timeout=timeout)
        infra_error = None
    except subprocess.TimeoutExpired:
        result = None
        infra_error = f"timeout after {timeout}s"
    stdout = result.stdout if result else ""
    stderr = result.stderr if result else ""
    write(trial_root / "stdout.txt", stdout)
    write(trial_root / "stderr.txt", stderr)
    errors = [infra_error] if infra_error else []
    if result and result.returncode != 0:
        errors.append(f"agent exit code {result.returncode}")
    if not errors:
        errors.extend(scenario.grade(fixture, state))
        if (fixture / ".deepdone/runs").exists():
            errors.append("DeepDone audit directory was created")
    report = {
        "agent": agent,
        "scenario": scenario.name,
        "trial": trial,
        "model": model or "cli-default",
        "passed": not errors,
        "errors": errors,
        "artifact": str(trial_root),
    }
    write(trial_root / "grade.json", json.dumps(report, indent=2) + "\n")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=tuple(PROFILES), default="smoke")
    parser.add_argument("--agent", action="append", choices=AGENTS, dest="agents")
    parser.add_argument("--scenario", action="append", dest="scenarios")
    parser.add_argument("--codex-model")
    parser.add_argument("--claude-model")
    parser.add_argument("--claude-max-budget-usd", type=float, default=1.0)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    available = scenarios()
    if args.list:
        for scenario in available:
            print(scenario.name)
        return 0
    selected_agents = list(dict.fromkeys(args.agents or AGENTS))
    if args.profile == "release":
        if set(selected_agents) != set(AGENTS):
            print("Release profile requires codex and claude", file=sys.stderr)
            return 2
        if not args.codex_model or not args.claude_model:
            print("Release profile requires explicit Codex and Claude models", file=sys.stderr)
            return 2
    checks = preflight(selected_agents)
    if args.preflight:
        print(json.dumps(checks, indent=2))
        return 0 if all(item["ok"] for item in checks.values()) else 2
    if not all(item["ok"] for item in checks.values()):
        print(json.dumps(checks, indent=2), file=sys.stderr)
        return 2

    requested = set(args.scenarios or [scenario.name for scenario in available])
    unknown = requested.difference(scenario.name for scenario in available)
    if unknown:
        print(f"Unknown scenarios: {sorted(unknown)}", file=sys.stderr)
        return 2
    requested.add("skill-discovery")
    selected_scenarios = [scenario for scenario in available if scenario.name in requested]
    temporary: tempfile.TemporaryDirectory[str] | None = None
    if args.output_dir:
        output_root = args.output_dir.resolve()
        output_root.mkdir(parents=True, exist_ok=True)
    else:
        temporary = tempfile.TemporaryDirectory(prefix="deepdone-evals-")
        output_root = Path(temporary.name)

    reports: list[dict[str, object]] = []
    try:
        for agent in selected_agents:
            model = args.codex_model if agent == "codex" else args.claude_model
            probe = next(scenario for scenario in selected_scenarios if scenario.name == "skill-discovery")
            probe_failed = False
            for trial in range(1, PROFILES[args.profile] + 1):
                report = run_trial(
                    agent,
                    probe,
                    trial,
                    output_root,
                    model,
                    args.claude_max_budget_usd,
                    args.timeout,
                )
                reports.append(report)
                print(json.dumps(report, sort_keys=True))
                probe_failed = probe_failed or not bool(report["passed"])
            if probe_failed:
                continue
            for scenario in selected_scenarios:
                if scenario.name == "skill-discovery":
                    continue
                for trial in range(1, PROFILES[args.profile] + 1):
                    report = run_trial(
                        agent,
                        scenario,
                        trial,
                        output_root,
                        model,
                        args.claude_max_budget_usd,
                        args.timeout,
                    )
                    reports.append(report)
                    print(json.dumps(report, sort_keys=True))
        summary = {
            "profile": args.profile,
            "passed": sum(1 for report in reports if report["passed"]),
            "failed": sum(1 for report in reports if not report["passed"]),
            "total": len(reports),
        }
        print(json.dumps(summary, sort_keys=True))
        return 0 if summary["failed"] == 0 else 1
    finally:
        if temporary is not None:
            temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
