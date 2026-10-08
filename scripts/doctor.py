#!/usr/bin/env python3
"""Self-test the DeepDone skills package."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PLUGIN_SCHEMA_URI = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
PLUGIN_VERSION = "2.1.1"
PLUGIN_DESCRIPTION = "End-to-end development with your coding agent."
PLUGIN_AUTHOR = {"name": "lakesoftai"}
PLUGIN_ALLOWED_FIELDS = {
    "$schema",
    "name",
    "version",
    "description",
    "author",
    "homepage",
    "repository",
    "license",
    "keywords",
    "extensions",
}
SKILL_ALLOWED_FRONTMATTER_FIELDS = {
    "name",
    "description",
    "license",
    "compatibility",
    "metadata",
    "allowed-tools",
}

PUBLIC_SKILLS = ["deepdone"]
PHASES = {
    f"phase-{name}": f"skills/deepdone/references/phase-{name}.md"
    for name in ("advance", "archive", "commit", "decide", "fixup", "implement", "plan", "pr", "review", "sync", "verify")
}
CONTRACT_SUBJECTS = set(PUBLIC_SKILLS).union(PHASES)
IMPLICIT_ENTRY_SKILLS = set(PUBLIC_SKILLS)
SUPERVISOR_MAX_LINES = 250
REQUIRED_INVARIANT_IDS = {
    "DD-ADVANCE-001",
    "DD-AUTH-001",
    "DD-AUTH-002",
    "DD-COMMIT-001",
    "DD-COMMIT-002",
    "DD-DRIFT-001",
    "DD-EVIDENCE-001",
    "DD-MODE-001",
    "DD-MODE-002",
    "DD-OWN-001",
    "DD-REVIEW-001",
    "DD-STATE-001",
    "DD-STATE-002",
}
INVARIANT_ID_RE = re.compile(r"^DD-[A-Z]+-[0-9]{3}$")

HELPER_SCRIPTS = [
    "skills/deepdone/scripts/routing.py",
    "skills/deepdone/scripts/work_unit.py",
    "skills/deepdone/scripts/verification.py",
    "evals/run_cross_agent.py",
    "skills/deepdone/scripts/check_reviewed_change_set.py",
    "skills/deepdone/scripts/commit_progress.py",
    "skills/deepdone/scripts/inspect_deepdone_state.py",
    "skills/deepdone/scripts/capture_reviewed_change_set.py",
]

MANIFEST_SCHEMA_SCRIPTS = [
    "skills/deepdone/scripts/check_reviewed_change_set.py",
    "skills/deepdone/scripts/commit_progress.py",
    "skills/deepdone/scripts/capture_reviewed_change_set.py",
]

EXAMPLES = [
    "examples/compact-task.md",
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
        if not line or line[0].isspace():
            continue
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
        unknown_fields = set(meta).difference(SKILL_ALLOWED_FRONTMATTER_FIELDS)
        if unknown_fields:
            errors.append(f"{skill}: unsupported frontmatter fields: {sorted(unknown_fields)}")
        for field in ("name", "description", "license", "compatibility", "metadata"):
            if field == "metadata":
                if field not in meta:
                    errors.append(f"{skill}: missing frontmatter field {field}")
                continue
            if not meta.get(field):
                errors.append(f"{skill}: missing frontmatter field {field}")
        if meta.get("name") and meta["name"] != skill:
            errors.append(f"{skill}: name does not match directory name")
        if meta.get("license") and meta["license"] != "Apache-2.0":
            errors.append(f"{skill}: license must be Apache-2.0")
        if len(meta.get("description", "")) > 1024:
            errors.append(f"{skill}: description exceeds 1024 characters")
        if len(meta.get("compatibility", "")) > 500:
            errors.append(f"{skill}: compatibility exceeds 500 characters")
        metadata_match = re.search(
            r"^metadata:\s*$\n(?P<body>(?:^[ \t]+.*(?:\n|$))+)",
            text,
            flags=re.MULTILINE,
        )
        if not metadata_match or not re.search(
            r"^\s+author:\s+lakesoftai\s*$",
            metadata_match.group("body"),
            flags=re.MULTILINE,
        ):
            errors.append(f"{skill}: metadata.author must be lakesoftai")

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


def read_json_object(path: Path, errors: list[str]) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"missing {path.relative_to(ROOT)}")
        return {}
    except json.JSONDecodeError as exc:
        errors.append(f"{path.relative_to(ROOT)}: invalid JSON: {exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{path.relative_to(ROOT)}: root must be a JSON object")
        return {}
    return value


def package_path_is_contained(path: Path, root: Path) -> bool:
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        return False
    return resolved.is_relative_to(root.resolve())


def check_plugin_package(errors: list[str]) -> None:
    manifest = read_json_object(ROOT / "plugin.json", errors)
    if manifest:
        unknown = set(manifest).difference(PLUGIN_ALLOWED_FIELDS)
        if unknown:
            errors.append(f"plugin.json: unsupported fields: {sorted(unknown)}")
        for field in ("$schema", "name"):
            if not manifest.get(field):
                errors.append(f"plugin.json: missing required field {field}")
        if manifest.get("$schema") != PLUGIN_SCHEMA_URI:
            errors.append("plugin.json: unsupported Agent Plugins schema")
        name = manifest.get("name")
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", name):
            errors.append("plugin.json: invalid plugin name")
        elif "--" in name or ".." in name or len(name) > 64:
            errors.append("plugin.json: invalid plugin name")
        if manifest.get("description") != PLUGIN_DESCRIPTION:
            errors.append("plugin.json: canonical description mismatch")
        if manifest.get("version") != PLUGIN_VERSION:
            errors.append(f"plugin.json: version must be {PLUGIN_VERSION}")
        if manifest.get("author") != PLUGIN_AUTHOR:
            errors.append("plugin.json: author mismatch")
        if manifest.get("license") != "Apache-2.0":
            errors.append("plugin.json: license must be Apache-2.0")
        if manifest.get("homepage") != "https://deepdone.ai/":
            errors.append("plugin.json: homepage mismatch")
        if manifest.get("repository") != "https://github.com/lakesoftai/deepdone-agent-skills":
            errors.append("plugin.json: repository mismatch")
        extensions = manifest.get("extensions")
        if extensions is not None and not isinstance(extensions, dict):
            errors.append("plugin.json: extensions must be an object")

    skills_dir = ROOT / "skills"
    discovered = {
        path.parent.name
        for path in skills_dir.glob("*/SKILL.md")
        if path.is_file()
    }
    if discovered != set(PUBLIC_SKILLS):
        errors.append(f"plugin.json: fixed skill discovery mismatch: {sorted(discovered)}")
    if (ROOT / "mcp.json").exists():
        errors.append("mcp.json: DeepDone must remain a skills-only plugin")

    overlay = read_json_object(ROOT / ".codex-plugin" / "plugin.json", errors)
    if overlay:
        allowed_overlay = {"name", "version", "description", "author", "interface"}
        unknown = set(overlay).difference(allowed_overlay)
        if unknown:
            errors.append(f".codex-plugin/plugin.json: unsupported overlay fields: {sorted(unknown)}")
        if overlay.get("name") != manifest.get("name"):
            errors.append(".codex-plugin/plugin.json: name must match plugin.json")
        if overlay.get("description") != manifest.get("description"):
            errors.append(".codex-plugin/plugin.json: description must match plugin.json")
        if overlay.get("version") != manifest.get("version"):
            errors.append(".codex-plugin/plugin.json: version must match plugin.json")
        if overlay.get("author") != manifest.get("author"):
            errors.append(".codex-plugin/plugin.json: author must match plugin.json")
        interface = overlay.get("interface")
        if not isinstance(interface, dict):
            errors.append(".codex-plugin/plugin.json: interface must be an object")
        else:
            required = {
                "displayName",
                "shortDescription",
                "longDescription",
                "category",
                "capabilities",
                "websiteURL",
                "defaultPrompt",
            }
            missing = required.difference(interface)
            if missing:
                errors.append(f".codex-plugin/plugin.json: missing interface fields: {sorted(missing)}")
            if interface.get("displayName") != "DeepDone":
                errors.append(".codex-plugin/plugin.json: displayName mismatch")
            if interface.get("developerName") != "lakesoftai":
                errors.append(".codex-plugin/plugin.json: developerName mismatch")
            if interface.get("websiteURL") != manifest.get("homepage"):
                errors.append(".codex-plugin/plugin.json: websiteURL must match plugin homepage")
            prompts = interface.get("defaultPrompt")
            if not isinstance(prompts, list) or not 1 <= len(prompts) <= 3:
                errors.append(".codex-plugin/plugin.json: defaultPrompt must contain 1 to 3 entries")
            elif any(not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 128 for prompt in prompts):
                errors.append(".codex-plugin/plugin.json: defaultPrompt entries must be non-empty and at most 128 characters")

    marketplace = read_json_object(ROOT / ".agents" / "plugins" / "marketplace.json", errors)
    if marketplace:
        if marketplace.get("name") != "deepdone":
            errors.append(".agents/plugins/marketplace.json: marketplace name mismatch")
        plugins = marketplace.get("plugins")
        if not isinstance(plugins, list) or len(plugins) != 1 or not isinstance(plugins[0], dict):
            errors.append(".agents/plugins/marketplace.json: expected one plugin entry")
        else:
            entry = plugins[0]
            if entry.get("name") != manifest.get("name"):
                errors.append(".agents/plugins/marketplace.json: plugin name mismatch")
            source = entry.get("source")
            if source != {"source": "local", "path": "."}:
                errors.append(".agents/plugins/marketplace.json: local source must point at repository root")
            policy = entry.get("policy")
            if policy != {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}:
                errors.append(".agents/plugins/marketplace.json: policy mismatch")
            if not entry.get("category"):
                errors.append(".agents/plugins/marketplace.json: missing category")

    claude_manifest = read_json_object(ROOT / ".claude-plugin" / "plugin.json", errors)
    for field in ("name", "version", "description", "author", "homepage", "repository", "license"):
        if claude_manifest.get(field) != manifest.get(field):
            errors.append(f".claude-plugin/plugin.json: {field} must match plugin.json")

    claude_marketplace = read_json_object(ROOT / ".claude-plugin" / "marketplace.json", errors)
    if claude_marketplace.get("name") != manifest.get("name"):
        errors.append(".claude-plugin/marketplace.json: marketplace name mismatch")
    if claude_marketplace.get("owner") != manifest.get("author"):
        errors.append(".claude-plugin/marketplace.json: owner mismatch")
    if claude_marketplace.get("plugins") != [{
        "name": manifest.get("name"),
        "source": "./",
        "description": manifest.get("description"),
    }]:
        errors.append(".claude-plugin/marketplace.json: expected one plugin at repository root")

    root = ROOT.resolve()
    package_roots = (ROOT / "plugin.json", ROOT / "skills", ROOT / ".codex-plugin", ROOT / ".claude-plugin", ROOT / ".agents" / "plugins")
    for package_root in package_roots:
        if not package_root.exists() and not package_root.is_symlink():
            continue
        if not package_path_is_contained(package_root, root):
            errors.append(f"plugin package path escapes repository root: {package_root.relative_to(ROOT)}")
            continue
        paths: list[Path] = []
        if package_root.is_dir():
            paths.extend(package_root.rglob("*"))
        for path in paths:
            if not package_path_is_contained(path, root):
                errors.append(f"plugin package path escapes repository root: {path.relative_to(ROOT)}")


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
    path = ROOT / "skills" / "deepdone" / "SKILL.md"
    line_count = len(read_text(path).splitlines())
    if line_count > SUPERVISOR_MAX_LINES:
        errors.append(f"deepdone: {line_count} lines exceeds {SUPERVISOR_MAX_LINES}")


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
        ROOT / "skills" / "deepdone" / "references" / "state-machine.md",
        ROOT / "skills" / "deepdone" / "references" / "safety-and-modes.md",
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
            applies = set(re.findall(r"`(deepdone|phase-[a-z0-9-]+)`", applies_match.group(1))) if applies_match else set()
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
    if versions and set(versions.values()) != {2}:
        errors.append(f"reviewed change-set schema mismatch: {versions}")


def check_logging_removed(errors: list[str]) -> None:
    removed_paths = (
        ROOT / "skills" / "deepdone" / "scripts" / "append_run_audit.py",
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
    for required in (
        "## Reviewed Git Snapshot",
        "## Reviewed Status Sample",
        "## Excluded Unreviewed Files",
        "## Stale Reviewed Path Sample",
        "## Staged Unowned Files",
        "review-id:",
        "manifest:",
        "scope:",
        "evidence:",
    ):
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
    check_plugin_package(errors)
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
    print("- plugin package: pass")
    print(f"- internal phases checked: {len(PHASES)}")
    print(f"- helper scripts checked: {len(HELPER_SCRIPTS)}")
    print(f"- invariants checked: {len(REQUIRED_INVARIANT_IDS)}")
    print(f"- examples checked: {len(EXAMPLES)}")
    print("- unit tests: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
