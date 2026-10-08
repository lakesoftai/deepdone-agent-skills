#!/usr/bin/env python3
"""Run manual DeepDone behavioral evaluations in Codex and Claude Code."""

from __future__ import annotations

import argparse
import hashlib
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
import work_unit
import routing

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
    import verification
    check = {
        "id": "source-syntax", "acceptance": "Python source compiles", "required": True,
        "argv": [sys.executable, "-I", "-B", "-c", "from pathlib import Path; files=list(Path('src').rglob('*.py')); assert files; [compile(p.read_bytes(), str(p), 'exec') for p in files]"],
        "cwd": ".", "inputs": [{"path": "src", "role": "source"}],
        "exclusions": [], "env": {}, "context": "local-files", "timeout": 10,
    }
    verification.initialize(root, ledger, [check], "Migrate deterministic evaluator fixture")
    verification.run_check(root, ledger, check["id"])
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


def semantic_index(root: Path) -> str:
    return git(root, "ls-files", "--stage", "-z").stdout


def tracked_source(root: Path) -> dict[str, object]:
    result = {}
    for name in git(root, 'ls-files', '-z').stdout.split('\0'):
        if name and not commit_progress.is_local_only(name):
            path = root / name
            result[name] = [path.lstat().st_mode, hashlib.sha256(path.read_bytes()).hexdigest()] if path.is_file() else None
    return result


def seed_intake(root: Path, kind: str = 'epic') -> dict[str, object]:
    write(root / "README.md", "# Intake fixture\n")
    base = commit_all(root, "evaluation base")
    return {"base": base, "kind": kind, "index": semantic_index(root),
            "source": tracked_source(root), "milestones": 2 if kind == "epic" else None}


def grade_intake(root: Path, state: dict[str, object]) -> list[str]:
    errors = grade_no_commit(root, state)
    kind = state['kind']
    tasks = list((root / '.deepdone/tasks').glob('*.md'))
    epics = list((root / 'notes/epics').glob('*.md'))
    records = tasks if kind == 'task' else epics
    if len(records) != 1:
        errors.append(f"expected one {kind}, found {len(records)}")
    else:
        try:
            record = work_unit.load(root, records[0].relative_to(root).as_posix(), kind)
            if kind == 'epic':
                rows = routing.milestones(record['text'])
                if len(rows) != state['milestones'] or any(row['marker'] != ' ' for row in rows):
                    errors.append('intake requires the requested planned milestone count')
            review = commit_progress.latest_review_entry(record['text'])
            if record['status'] != 'active' or review.get('result') != 'pending' or review.get('reviewed-at') != 'not-run':
                errors.append('intake requires active status and initial pending Review')
        except (OSError, ValueError) as exc:
            errors.append(f'invalid intake metadata: {exc}')
    if (kind == 'task' and epics) or (kind == 'epic' and tasks) or (root / 'notes/roadmap.md').exists():
        errors.append('intake created extra hierarchy')
    if tracked_source(root) != state['source']:
        errors.append('planning-only intake changed tracked source')
    changes = commit_progress.parse_status_z(root)
    if any(not commit_progress.is_local_only(item.path) for item in changes):
        errors.append('planning-only intake changed source')
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
    return {"base": commit_all(root, "evaluation base"), "index": semantic_index(root)}


def grade_lifecycle(root: Path, state: dict[str, object]) -> list[str]:
    errors: list[str] = []
    is_task = state.get('kind') == 'task'
    record_path = '.deepdone/tasks/calculator.md' if is_task else 'notes/epics/current.md'
    try:
        ledger = read_or_empty(root / record_path)
        work_unit.load(root, record_path, "task" if is_task else "epic")
    except (OSError, UnicodeError, ValueError) as exc:
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

    errors.extend(grade_review_evidence(root, state, record_path, ledger, 'src/calc.py'))
    return errors


def grade_review_evidence(root, state, record_path, ledger, required_path=None):
    errors = grade_no_commit(root, state)
    # Use the evaluator's helper, not a potentially edited copy in the fixture.
    try:
        errors.extend(commit_progress.commit_gate_errors(
            record_path, None, ledger,
            commit_progress.latest_verification_lines(ledger),
            commit_progress.review_lines(ledger),
            section(ledger, "Open Loops").splitlines(), root=root,
        ))
        validation = commit_progress.validate_reviewed_change_set(
            root, record_path, ledger, None, commit_progress.parse_status_z(root),
        )
        errors.extend(validation[2])
        if required_path and required_path not in validation[7]:
            errors.append("calculator implementation is outside reviewed snapshot")
        if state.get("base") and git(root, "rev-parse", "HEAD").stdout.strip() != state["base"]:
            errors.append("lifecycle changed HEAD before authorized commit")
    except Exception as exc:
        # Malformed evidence is a grading failure, not a crashed evaluation run.
        errors.append(f"review evidence validation failed: {type(exc).__name__}: {exc}")
    if section(ledger, "Status").strip() != "complete":
        errors.append(f"{work_unit.kind(record_path)} not complete after review")
    return errors



def seed_task(root: Path) -> dict[str, object]:
    write(root / 'src/calc.py', 'def add(a, b):\n    return a + b\n')
    write(root / 'tests/test_calc.py', 'import unittest\n\nclass CalcTests(unittest.TestCase):\n    pass\n')
    task = {
        'schema': 1, 'kind': 'task', 'id': 'calculator',
        'goal': 'Add subtraction while preserving addition',
        'scope': {'include': ['src/', 'tests/'], 'exclude': []},
        'acceptance': [{'check_id': 'arithmetic', 'condition': 'Addition and subtraction return expected results'}],
        'constraints': ['No commit in candidate-only evaluation'],
    }
    write(root / '.deepdone/tasks/calculator.md',
          '# Calculator task\n\n## Task\n\n```json\n' + json.dumps(task, indent=2) + '\n```\n\n'
          '## Verification Log\n\nNo executions yet.\n\n## Review\n\n- reviewed-at: not-run\n  result: pending\n\n'
          '## Open Loops\n\nnone\n\n## Next Action\n\nImplement subtract and verify both operations.\n\n## Status\n\nactive\n')
    return {'base': commit_all(root, 'evaluation base'), 'kind': 'task', 'index': semantic_index(root)}

def seed_review_fix(root: Path) -> dict[str, object]:
    write(root / "src/auth.py", "def allowed(role):\n    return role == 'admin'\n")
    write(root / "tests/test_auth.py", "import unittest\nfrom src.auth import allowed\n\nclass AuthTests(unittest.TestCase):\n    def test_admin(self):\n        self.assertTrue(allowed('admin'))\n")
    write(root / "notes/epics/current.md", pending_ledger("Auth Epic", "preserve admin-only access"))
    base = commit_all(root, "evaluation base")
    write(root / "src/auth.py", "def allowed(role):\n    return True\n")
    ledger = pending_ledger("Auth Epic", "preserve admin-only access").replace("- [ ] preserve", "- [x] preserve")
    write(root / "notes/epics/current.md", ledger)
    verification = commit_progress.verification_evidence
    check = {
        'id': 'access', 'acceptance': 'Only admin is allowed', 'required': True,
        'argv': [sys.executable, '-I', '-B', '-c', "exec(open('src/auth.py').read()); assert allowed('admin') is True"],
        'cwd': '.', 'inputs': [{'path':'src','role':'source'}, {'path':'tests','role':'source'}],
        'exclusions': [], 'env': {}, 'context': 'local-files', 'timeout': 10,
    }
    verification.initialize(root, 'notes/epics/current.md', [check], 'Seed actual but incomplete happy-path coverage')
    receipt = verification.run_check(root, 'notes/epics/current.md', 'access')
    if not verification.execution_succeeded(receipt):
        raise RuntimeError('review-fix fixture readiness failed')
    path = root / 'notes/epics/current.md'
    path.write_text(path.read_text().replace('No checks yet.',
        f"- command: `{json.dumps(check['argv'])}`\n  result: pass\n  notes: actual readiness execution; only admin coverage, pending review"))
    return {"base": base, "index": semantic_index(root)}


def grade_review_fix(root: Path, state: dict[str, object]) -> list[str]:
    ledger_path = 'notes/epics/current.md'
    ledger = read_or_empty(root / ledger_path)
    errors = grade_review_evidence(root, state, ledger_path, ledger)
    results = [entry.get('result') for entry in commit_progress.review_snapshot.review_entries(ledger)]
    if 'fail' not in results or not results or results[-1] != 'pass':
        errors.append(f'expected review fail then pass, found {results}')
    # The evaluator owns this oracle; neither fixture tests nor Review prose can weaken it.
    script = ("import os,sys; sys.path.insert(0,os.getcwd()); from src.auth import allowed\n"
              "assert allowed('admin') is True, 'admin access lost'\n"
              "for role in ('viewer','guest','ADMIN','',None):\n"
              "    assert allowed(role) is False, ('non-admin access allowed', role)\n")
    try:
        result = run([sys.executable, '-I', '-B', '-c', script], root, timeout=10)
        if result.returncode:
            errors.append(f'access behavior check failed: {result.stderr.strip()[-2000:]}')
    except (OSError, subprocess.TimeoutExpired) as exc:
        errors.append(f'access behavior check could not complete: {exc}')
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
    return {"base": base, "manifest": manifest, "index": semantic_index(root), "roadmap": read_or_empty(root / "notes/roadmap.md")}


def grade_no_commit(root: Path, state: dict[str, object]) -> list[str]:
    errors = [] if git(root, 'rev-parse', 'HEAD').stdout.strip() == state['base'] else ['unexpected commit created']
    if 'index' in state and semantic_index(root) != state['index']:
        errors.append('unexpected semantic index change')
    return errors


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
    return {"base": commit_all(root, "evaluation base"), "index": semantic_index(root)}


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
            "epic-one-step-intake",
            "Use DeepDone. Requirements: plan an explicit single epic with two milestones for greeting behavior and regression coverage. Do not create a roadmap. Mode: one-step. Perform only this mode.",
            seed_intake,
            grade_intake,
        ),
        Scenario(
            "task-one-step-intake",
            "Use DeepDone. Requirements: create a compact task for src/greet.py with deterministic greet(name) and tests. Mode: one-step. Plan only, no epic or roadmap.",
            lambda root: seed_intake(root, 'task'),
            grade_intake,
        ),
        Scenario(
            "implement-verify-review",
            "Use $deepdone. Continue current epic in mode until-epic. Implement milestone, verify, review, and stop at mode boundary.",
            lambda root: seed_active(root),
            grade_lifecycle,
        ),
        Scenario(
            "compact-task-candidate",
            "Use $deepdone. Mode: until-commit-candidate. Selected task: .deepdone/tasks/calculator.md. "
            "Phase context: pin --task .deepdone/tasks/calculator.md through implement, verify, review and candidate. "
            "Add subtract, preserve add, run real checks, capture exact review and prepare candidate. Do not commit or change HEAD.",
            seed_task,
            grade_lifecycle,
        ),
        Scenario(
            "review-fail-fix-verify-review",
            "Use $deepdone. Continue current epic in mode until-epic. The authorized requirement is admin-only access: admin allowed, all other roles denied. Verify current receipt freshness, review the implementation and incomplete coverage, reproduce any defect for its intended symptom, restore this stated behavior and add denial regression coverage. Preserve diagnostic/feedback history, run actual readiness, review again and stop without staging or committing.",
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
    state["index"] = semantic_index(fixture)
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
