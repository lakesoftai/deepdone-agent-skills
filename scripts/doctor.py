#!/usr/bin/env python3
"""Self-test the DeepDone skills package."""

from __future__ import annotations

import os
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SKILLS = [
    "deepdone-advance",
    "deepdone-archive",
    "deepdone-commit",
    "deepdone-decide",
    "deepdone-fixup",
    "deepdone-implement",
    "deepdone-orchestrate",
    "deepdone-plan",
    "deepdone-pr",
    "deepdone-review",
    "deepdone-sync",
    "deepdone-verify",
]

HELPER_SCRIPTS = [
    "skills/deepdone-commit/scripts/commit_progress.py",
    "skills/deepdone-orchestrate/scripts/append_run_audit.py",
    "skills/deepdone-orchestrate/scripts/inspect_deepdone_state.py",
]

EXAMPLES = [
    "examples/roadmap.md",
    "examples/single-epic-ledger.md",
    "examples/multi-epic-active-ledger.md",
    "examples/commit-candidate.md",
    "examples/pr-body.md",
    "examples/archived-epic-ledger.md",
    "examples/post-merge-roadmap.md",
    "examples/run-audit.jsonl",
]


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"^---\n(.*?)\n---\n", text, flags=re.DOTALL)
    if not match:
        return {}
    data: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()
    return data


def check_skill_metadata(errors: list[str]) -> None:
    for skill in SKILLS:
        skill_dir = ROOT / "skills" / skill
        skill_md = skill_dir / "SKILL.md"
        text = read_text(skill_md)
        if not text:
            errors.append(f"{skill}: missing SKILL.md")
            continue

        meta = frontmatter(text)
        for field in ("name", "slug", "description"):
            if not meta.get(field):
                errors.append(f"{skill}: missing frontmatter field {field}")
        if meta.get("name") and meta["name"] != skill:
            errors.append(f"{skill}: name does not match directory name")
        if meta.get("slug") and meta["slug"] != skill:
            errors.append(f"{skill}: slug does not match directory name")

        agent_manifest = skill_dir / "agents" / "openai.yaml"
        manifest = read_text(agent_manifest)
        if not manifest:
            errors.append(f"{skill}: missing agents/openai.yaml")
        else:
            for required in ("interface:", "display_name:", "short_description:", "default_prompt:"):
                if required not in manifest:
                    errors.append(f"{skill}: agents/openai.yaml missing {required}")


def check_examples(errors: list[str]) -> None:
    if not read_text(ROOT / "README.md"):
        errors.append("missing README.md")
    if not read_text(ROOT / "LICENSE"):
        errors.append("missing LICENSE")
    for rel in EXAMPLES:
        if not read_text(ROOT / rel):
            errors.append(f"missing {rel}")

    roadmap = read_text(ROOT / "examples" / "roadmap.md")
    if roadmap and "## Cross-Cutting Decisions" not in roadmap:
        errors.append("examples/roadmap.md: missing Cross-Cutting Decisions section")

    pr_body = read_text(ROOT / "examples" / "pr-body.md")
    for required in ("## Summary", "## DeepDone", "## Verification", "## Open Loops"):
        if pr_body and required not in pr_body:
            errors.append(f"examples/pr-body.md: missing {required}")

    archived_ledger = read_text(ROOT / "examples" / "archived-epic-ledger.md")
    for required in ("## Status", "archived", "merge/ref:", "post-merge verification:"):
        if archived_ledger and required not in archived_ledger:
            errors.append(f"examples/archived-epic-ledger.md: missing {required}")

    post_merge = read_text(ROOT / "examples" / "post-merge-roadmap.md")
    if post_merge and "notes/archive/epics/" not in post_merge:
        errors.append("examples/post-merge-roadmap.md: missing archived ledger path")

    audit = read_text(ROOT / "examples" / "run-audit.jsonl")
    for index, line in enumerate(audit.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"examples/run-audit.jsonl:{index}: invalid JSON: {exc.msg}")
            continue
        for field in ("state_before", "skill_invoked", "state_after", "files_touched", "stop_reason"):
            if field not in row:
                errors.append(f"examples/run-audit.jsonl:{index}: missing {field}")


def check_helper_scripts(errors: list[str]) -> None:
    for rel in HELPER_SCRIPTS:
        path = ROOT / rel
        text = read_text(path)
        if not text:
            errors.append(f"missing {rel}")
            continue
        try:
            compile(text, str(path), "exec")
        except SyntaxError as exc:
            errors.append(f"{rel}: syntax error line {exc.lineno}: {exc.msg}")
        if not text.startswith("#!/usr/bin/env python3"):
            errors.append(f"{rel}: missing python3 shebang")
        if not os.access(path, os.X_OK):
            errors.append(f"{rel}: not executable")


def run_unit_tests(errors: list[str]) -> None:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        output = (proc.stdout + proc.stderr).strip()
        errors.append("unit tests failed:\n" + output)


def main() -> int:
    errors: list[str] = []
    check_skill_metadata(errors)
    check_examples(errors)
    check_helper_scripts(errors)
    run_unit_tests(errors)

    if errors:
        print("DeepDone doctor: fail")
        for error in errors:
            print(f"- {error}")
        return 1

    print("DeepDone doctor: pass")
    print(f"- skills checked: {len(SKILLS)}")
    print(f"- helper scripts checked: {len(HELPER_SCRIPTS)}")
    print(f"- examples checked: {len(EXAMPLES)}")
    print("- unit tests: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
