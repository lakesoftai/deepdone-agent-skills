#!/usr/bin/env python3
"""Self-test the DeepDone skills package."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PUBLIC_SKILLS = ["deepdone-advance", "deepdone-orchestrate"]
PHASES = {
    "phase-archive": "skills/deepdone-orchestrate/references/phase-archive.md",
    "phase-commit": "skills/deepdone-orchestrate/references/phase-commit.md",
    "phase-decide": "skills/deepdone-orchestrate/references/phase-decide.md",
    "phase-fixup": "skills/deepdone-orchestrate/references/phase-fixup.md",
    "phase-implement": "skills/deepdone-orchestrate/references/phase-implement.md",
    "phase-plan": "skills/deepdone-orchestrate/references/phase-plan.md",
    "phase-pr": "skills/deepdone-orchestrate/references/phase-pr.md",
    "phase-review": "skills/deepdone-orchestrate/references/phase-review.md",
    "phase-sync": "skills/deepdone-orchestrate/references/phase-sync.md",
    "phase-verify": "skills/deepdone-orchestrate/references/phase-verify.md",
}
CONTRACT_SUBJECTS = set(PUBLIC_SKILLS).union(PHASES)
IMPLICIT_ENTRY_SKILLS = set(PUBLIC_SKILLS)
ORCHESTRATOR_MAX_LINES = 250
REQUIRED_INVARIANT_IDS = {
    "DD-ADVANCE-001",
    "DD-AUTH-001",
    "DD-AUTH-002",
    "DD-COMMIT-001",
    "DD-COMMIT-002",
    "DD-DRIFT-001",
    "DD-MODE-001",
    "DD-MODE-002",
    "DD-OWN-001",
    "DD-REVIEW-001",
    "DD-STATE-001",
    "DD-STATE-002",
}
INVARIANT_ID_RE = re.compile(r"^DD-[A-Z]+-[0-9]{3}$")

HELPER_SCRIPTS = [
    "evals/run_cross_agent.py",
    "skills/deepdone-advance/scripts/check_reviewed_change_set.py",
    "skills/deepdone-orchestrate/scripts/commit_progress.py",
    "skills/deepdone-orchestrate/scripts/inspect_deepdone_state.py",
    "skills/deepdone-orchestrate/scripts/capture_reviewed_change_set.py",
]

MANIFEST_SCHEMA_SCRIPTS = [
    "skills/deepdone-advance/scripts/check_reviewed_change_set.py",
    "skills/deepdone-orchestrate/scripts/commit_progress.py",
    "skills/deepdone-orchestrate/scripts/capture_reviewed_change_set.py",
]

EXAMPLES = [
    "examples/roadmap.md",
    "examples/single-epic-ledger.md",
    "examples/multi-epic-active-ledger.md",
    "examples/commit-candidate.md",
    "examples/pr-body.md",
    "examples/archived-epic-ledger.md",
    "examples/post-merge-roadmap.md",
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
    discovered = {path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md")}
    expected_skills = set(PUBLIC_SKILLS)
    if discovered != expected_skills:
        errors.append(f"public skill set mismatch: expected {sorted(expected_skills)}, found {sorted(discovered)}")

    for skill in PUBLIC_SKILLS:
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
            prompt_match = re.search(r"^\s{2}default_prompt:\s*\|\s*$\n(?P<body>(?:^(?:\s{4,}.*|\s*)$\n?)+)", manifest, flags=re.MULTILINE)
            if not prompt_match or not prompt_match.group("body").strip():
                errors.append(f"{skill}: agents/openai.yaml has invalid or empty default_prompt block")
            match = re.search(r"^\s*allow_implicit_invocation:\s*(true|false)\s*$", manifest, flags=re.MULTILINE)
            if not match:
                errors.append(f"{skill}: agents/openai.yaml missing allow_implicit_invocation policy")
            else:
                actual = match.group(1) == "true"
                expected_policy = skill in IMPLICIT_ENTRY_SKILLS
                if actual != expected_policy:
                    errors.append(f"{skill}: allow_implicit_invocation must be {str(expected_policy).lower()}")


def check_phase_modules(errors: list[str]) -> None:
    for phase, rel in PHASES.items():
        text = read_text(ROOT / rel)
        if not text:
            errors.append(f"{phase}: missing phase reference {rel}")
            continue
        if text.startswith("---\n"):
            errors.append(f"{phase}: phase reference must not contain skill frontmatter")
        title = phase.removeprefix("phase-").replace("-", " ").title()
        title = "PR" if title == "Pr" else title
        expected_heading = f"# {title} Phase"
        if expected_heading not in text:
            errors.append(f"{phase}: missing heading {expected_heading}")


def check_skill_references(errors: list[str]) -> None:
    link_re = re.compile(r"\]\((references/[^)#]+)(?:#[^)]+)?\)")
    for skill in PUBLIC_SKILLS:
        skill_dir = ROOT / "skills" / skill
        text = read_text(skill_dir / "SKILL.md")
        linked = set(link_re.findall(text))
        for rel in linked:
            if not (skill_dir / rel).is_file():
                errors.append(f"{skill}: linked reference does not exist: {rel}")

        references_dir = skill_dir / "references"
        if references_dir.exists():
            for path in references_dir.glob("*.md"):
                rel = str(path.relative_to(skill_dir))
                if rel not in linked:
                    errors.append(f"{skill}: orphan reference not linked from SKILL.md: {rel}")


def check_orchestrator_budget(errors: list[str]) -> None:
    path = ROOT / "skills" / "deepdone-orchestrate" / "SKILL.md"
    line_count = len(read_text(path).splitlines())
    if line_count > ORCHESTRATOR_MAX_LINES:
        errors.append(f"deepdone-orchestrate: {line_count} lines exceeds {ORCHESTRATOR_MAX_LINES}")


def markdown_section(text: str, name: str) -> str:
    match = re.search(rf"^##\s+{re.escape(name)}\s*$", text, flags=re.MULTILINE)
    if not match:
        return ""
    start = match.end()
    next_match = re.search(r"^##\s+", text[start:], flags=re.MULTILINE)
    end = start + next_match.start() if next_match else len(text)
    return text[start:end].strip()


def parse_contract_invariants(errors: list[str]) -> tuple[dict[str, set[str]], set[str]]:
    active: dict[str, set[str]] = {}
    retired: set[str] = set()
    references = (
        ROOT / "skills" / "deepdone-orchestrate" / "references" / "state-machine.md",
        ROOT / "skills" / "deepdone-orchestrate" / "references" / "safety-and-modes.md",
    )
    for path in references:
        text = read_text(path)
        headings = list(re.finditer(r"^##\s+(Active|Retired) Invariants\s*$|^###\s+(DD-[A-Z]+-[0-9]{3}):\s+(.+?)\s*$", text, flags=re.MULTILINE))
        state: str | None = None
        for index, match in enumerate(headings):
            if match.group(1):
                state = match.group(1).lower()
                continue
            invariant_id = match.group(2)
            if state not in {"active", "retired"}:
                errors.append(f"{path.relative_to(ROOT)}: {invariant_id} is outside an invariant section")
                continue
            end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
            block = text[match.end() : end]
            if invariant_id in active or invariant_id in retired:
                errors.append(f"duplicate invariant ID: {invariant_id}")
                continue
            if not INVARIANT_ID_RE.fullmatch(invariant_id):
                errors.append(f"invalid invariant ID: {invariant_id}")
            if state == "retired":
                retired.add(invariant_id)
                continue
            for field in ("Rule", "Applies to", "Evidence"):
                if not re.search(rf"^-\s+{field}:\s+\S", block, flags=re.MULTILINE):
                    errors.append(f"{invariant_id}: missing {field}")
            applies_match = re.search(r"^-\s+Applies to:\s+(.+)$", block, flags=re.MULTILINE)
            applies = set(re.findall(r"`((?:deepdone|phase)-[a-z0-9-]+)`", applies_match.group(1))) if applies_match else set()
            if not applies:
                errors.append(f"{invariant_id}: has no affected contract subjects")
            unknown = applies.difference(CONTRACT_SUBJECTS)
            if unknown:
                errors.append(f"{invariant_id}: unknown affected contract subjects: {sorted(unknown)}")
            active[invariant_id] = applies
    return active, retired


def check_invariant_conformance(errors: list[str]) -> None:
    active, retired = parse_contract_invariants(errors)
    found = set(active).union(retired)
    missing = REQUIRED_INVARIANT_IDS.difference(found)
    if missing:
        errors.append(f"missing required invariant IDs: {sorted(missing)}")
    unexpected = found.difference(REQUIRED_INVARIANT_IDS)
    if unexpected:
        errors.append(f"unregistered invariant IDs: {sorted(unexpected)}")

    subject_paths = {
        **{skill: f"skills/{skill}/SKILL.md" for skill in PUBLIC_SKILLS},
        **PHASES,
    }
    subject_refs: dict[str, set[str]] = {}
    for subject, rel in subject_paths.items():
        text = read_text(ROOT / rel)
        refs = set(re.findall(r"`(DD-[A-Z]+-[0-9]{3})`", markdown_section(text, "Conforms To")))
        subject_refs[subject] = refs
        unknown = refs.difference(active).difference(retired)
        if unknown:
            errors.append(f"{subject}: references unknown invariants: {sorted(unknown)}")
        retired_refs = refs.intersection(retired)
        if retired_refs:
            errors.append(f"{subject}: references retired invariants: {sorted(retired_refs)}")

    for invariant_id, affected_subjects in active.items():
        for subject in affected_subjects:
            if invariant_id not in subject_refs.get(subject, set()):
                errors.append(f"{subject}: missing declared invariant {invariant_id}")
        for subject, refs in subject_refs.items():
            if invariant_id in refs and subject not in affected_subjects:
                errors.append(f"{subject}: references {invariant_id} but contract does not list it")


def check_manifest_schema_versions(errors: list[str]) -> None:
    versions: dict[str, int] = {}
    for rel in MANIFEST_SCHEMA_SCRIPTS:
        text = read_text(ROOT / rel)
        match = re.search(r"^MANIFEST_SCHEMA_VERSION\s*=\s*([0-9]+)\s*$", text, flags=re.MULTILINE)
        if not match:
            errors.append(f"{rel}: missing MANIFEST_SCHEMA_VERSION")
        else:
            versions[rel] = int(match.group(1))
    if versions and set(versions.values()) != {1}:
        errors.append(f"reviewed change-set schema mismatch: {versions}")


def check_logging_removed(errors: list[str]) -> None:
    removed_paths = (
        ROOT / "skills" / "deepdone-orchestrate" / "scripts" / "append_run_audit.py",
        ROOT / "tests" / "test_append_run_audit.py",
        ROOT / "examples" / "run-audit.jsonl",
    )
    for path in removed_paths:
        if path.exists():
            errors.append(f"run logging path must be removed: {path.relative_to(ROOT)}")

    forbidden = ("append_run_audit", "run-audit.jsonl", ".deepdone/runs")
    roots = [ROOT / "skills", ROOT / "scripts", ROOT / "tests", ROOT / "examples"]
    files = [ROOT / "README.md", ROOT / "AGENTS.md"]
    for root in roots:
        files.extend(path for path in root.rglob("*") if path.is_file() and "__pycache__" not in path.parts)
    for path in files:
        if path.resolve() == Path(__file__).resolve():
            continue
        text = read_text(path)
        for token in forbidden:
            if token in text:
                errors.append(f"logging integration remains in {path.relative_to(ROOT)}: {token}")


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

    commit_candidate = read_text(ROOT / "examples" / "commit-candidate.md")
    for required in ("## Reviewed Files", "## Excluded Unreviewed Files", "## Stale Reviewed Files", "## Staged Unowned Files", "review-id:", "manifest:", "paths:"):
        if commit_candidate and required not in commit_candidate:
            errors.append(f"examples/commit-candidate.md: missing {required}")

    archived_ledger = read_text(ROOT / "examples" / "archived-epic-ledger.md")
    for required in ("## Review", "result: pass", "## Status", "archived", "merge/ref:", "post-merge verification:"):
        if archived_ledger and required not in archived_ledger:
            errors.append(f"examples/archived-epic-ledger.md: missing {required}")

    post_merge = read_text(ROOT / "examples" / "post-merge-roadmap.md")
    if post_merge and "notes/archive/epics/" not in post_merge:
        errors.append("examples/post-merge-roadmap.md: missing archived ledger path")

    for rel in ("examples/single-epic-ledger.md", "examples/multi-epic-active-ledger.md"):
        text = read_text(ROOT / rel)
        for required in ("## Review", "reviewed-at: not-run", "result: pending"):
            if text and required not in text:
                errors.append(f"{rel}: missing {required}")


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
    check_phase_modules(errors)
    check_skill_references(errors)
    check_orchestrator_budget(errors)
    check_invariant_conformance(errors)
    check_manifest_schema_versions(errors)
    check_logging_removed(errors)
    check_examples(errors)
    check_helper_scripts(errors)
    run_unit_tests(errors)

    if errors:
        print("DeepDone doctor: fail")
        for error in errors:
            print(f"- {error}")
        return 1

    print("DeepDone doctor: pass")
    print(f"- public skills checked: {len(PUBLIC_SKILLS)}")
    print(f"- internal phases checked: {len(PHASES)}")
    print(f"- helper scripts checked: {len(HELPER_SCRIPTS)}")
    print(f"- invariants checked: {len(REQUIRED_INVARIANT_IDS)}")
    print(f"- examples checked: {len(EXAMPLES)}")
    print("- unit tests: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
