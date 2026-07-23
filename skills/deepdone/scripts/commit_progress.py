#!/usr/bin/env python3
"""Prepare or create a DeepDone Commit phase result from one reviewed change set."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import capture_reviewed_change_set as review_snapshot  # noqa: E402


MANIFEST_SCHEMA_VERSION = 2

DANGEROUS_PATTERNS = [
    re.compile(r"(^|/)\.env($|[./])", re.IGNORECASE),
    re.compile(r"(^|/)\.?secrets?($|/|\.(env|json|ya?ml|toml|ini|txt|key|pem))", re.IGNORECASE),
    re.compile(r"(^|/)\.?credentials?($|/|\.(env|json|ya?ml|toml|ini|txt|key|pem))", re.IGNORECASE),
    re.compile(r"(^|/)\.?private[_-]?key($|/|\.(env|json|ya?ml|toml|ini|txt|pem))", re.IGNORECASE),
    re.compile(r"(^|/)\.?tokens?($|/|\.(env|json|ya?ml|toml|ini|txt|key|pem))", re.IGNORECASE),
    re.compile(r"(^|/)id_rsa($|\.)", re.IGNORECASE),
    re.compile(r"\.pem$", re.IGNORECASE),
    re.compile(r"\.p12$", re.IGNORECASE),
    re.compile(r"\.sqlite$", re.IGNORECASE),
    re.compile(r"\.db$", re.IGNORECASE),
]

ALLOWLISTED_DANGEROUS_PATTERNS = [
    re.compile(r"(^|/)tests?/fixtures?/", re.IGNORECASE),
    re.compile(r"(^|/)fixtures?/", re.IGNORECASE),
    re.compile(r"(^|/)tests?/.*fixtures?\.[^.]+$", re.IGNORECASE),
    re.compile(r"(^|/)design[-_]tokens?($|/|\.)", re.IGNORECASE),
]

LOCAL_ONLY_PATTERNS = [
    re.compile(r"(^|/)\.deepdone/commit-candidate\.md$"),
    re.compile(r"(^|/)\.deepdone/reviews/[^/]+\.json$"),
]

VERIFICATION_RESULT_RE = re.compile(r"(^|\s|[-*`])result:\s*(pass|fail|blocked)\b", re.IGNORECASE)
REVIEW_RESULT_RE = re.compile(r"(^|\s|[-*`])review-result:\s*(pass|fail|blocked)\b", re.IGNORECASE)
REVIEW_SECTION_RESULT_RE = re.compile(r"(^|\s|[-*`])result:\s*(pending|pass|fail|blocked)\b", re.IGNORECASE)
REVIEW_BLOCKER_RE = re.compile(r"\b(blocked|blocking|unresolved|deferred|needs user|needs_user|failed|fail)\b", re.IGNORECASE)
REVIEW_CLEAR_RE = re.compile(r"\b(no blocking|no findings|clean|pass|passed)\b", re.IGNORECASE)


@dataclass(frozen=True)
class GitFile:
    status: str
    path: str
    old_path: str | None = None


def run(cmd: list[str], cwd: Path, check: bool = False) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if check and proc.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{proc.stderr.rstrip()}")
    return proc.returncode, proc.stdout.rstrip("\n"), proc.stderr.rstrip("\n")


def run_bytes(cmd: list[str], cwd: Path) -> tuple[int, bytes, bytes]:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True)
    return proc.returncode, proc.stdout, proc.stderr


def git_root(start: Path) -> Path:
    code, out, err = run(["git", "rev-parse", "--show-toplevel"], start)
    if code != 0 or not out:
        raise RuntimeError(f"Not a git repository: {err}")
    return Path(out).resolve()


def parse_status(lines: list[str]) -> list[GitFile]:
    """Parse human porcelain output for compatibility with callers and tests."""
    files: list[GitFile] = []
    for line in lines:
        if not line:
            continue
        status_text = line[:2].strip()
        path = line[3:]
        old_path = None
        if " -> " in path:
            old_path, path = path.split(" -> ", 1)
        files.append(GitFile(status=status_text, path=path, old_path=old_path))
    return files


def parse_status_z(root: Path) -> list[GitFile]:
    code, out, err = run_bytes(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], root)
    if code != 0:
        raise RuntimeError(err.decode(errors="replace").strip())
    chunks = out.split(b"\0")
    files: list[GitFile] = []
    index = 0
    while index < len(chunks):
        chunk = chunks[index]
        index += 1
        if not chunk:
            continue
        if len(chunk) < 4 or chunk[2:3] != b" ":
            raise RuntimeError("Malformed porcelain status record")
        status_text = chunk[:2].decode("ascii", errors="strict")
        path = os.fsdecode(chunk[3:])
        old_path = None
        if "R" in status_text or "C" in status_text:
            if index >= len(chunks) or not chunks[index]:
                raise RuntimeError(f"Missing rename source for {path}")
            old_path = os.fsdecode(chunks[index])
            index += 1
        files.append(GitFile(status=status_text, path=path, old_path=old_path))
    return files


def is_allowlisted_dangerous(path: str) -> bool:
    return any(pattern.search(path) for pattern in ALLOWLISTED_DANGEROUS_PATTERNS)


def is_dangerous(path: str) -> bool:
    return any(pattern.search(path) for pattern in DANGEROUS_PATTERNS) and not is_allowlisted_dangerous(path)


def is_local_only(path: str) -> bool:
    return any(pattern.search(path) for pattern in LOCAL_ONLY_PATTERNS)


def read_text(path: Path) -> str:
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


def status_is_active(status_text: str) -> bool:
    active_values = {"active", "in progress", "in-progress", "current"}
    for raw_line in status_text.splitlines() or [status_text]:
        line = raw_line.strip().lower()
        line = re.sub(r"^[-*]\s*", "", line)
        line = re.sub(r"^\[[ xX-]\]\s*", "", line)
        if ":" in line:
            key, value = [part.strip() for part in line.split(":", 1)]
            if key in {"status", "state"} and value in active_values:
                return True
        if line in active_values:
            return True
    return False


def status_is_complete(status_text: str) -> bool:
    for raw_line in status_text.splitlines() or [status_text]:
        line = re.sub(r"^[-*]\s*", "", raw_line.strip().lower())
        if ":" in line:
            key, value = [part.strip() for part in line.split(":", 1)]
            if key in {"status", "state"} and value == "complete":
                return True
        if line == "complete":
            return True
    return False


def ledger_title(text: str) -> str | None:
    match = re.search(r"^#\s+(.+?)\s*$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def ensure_repo_path(root: Path, rel: str) -> Path:
    if not rel or Path(rel).is_absolute():
        raise ValueError(f"Expected repository-relative path: {rel}")
    normalized = normalize_repo_path(root, rel)
    return root.resolve() / normalized


def normalize_repo_path(root: Path, value: str) -> str:
    root = root.resolve()
    raw = Path(value)
    if raw.is_absolute():
        raise ValueError(f"Absolute path is not allowed: {value}")
    relative = Path(os.path.normpath(os.fspath(raw)))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Path escapes repository: {value}")
    if not relative.parts:
        raise ValueError("Repository root is not a valid path")
    parent = (root / relative).parent.resolve()
    try:
        parent.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Path parent escapes repository: {value}") from exc
    return relative.as_posix()


def parse_active_ledger(root: Path, explicit_ledger: str | None = None) -> tuple[str | None, str | None, str | None, str]:
    if explicit_ledger:
        try:
            ledger_rel = normalize_repo_path(root, explicit_ledger)
            ledger_path = ensure_repo_path(root, ledger_rel)
        except ValueError:
            return None, explicit_ledger, None, ""
        text = read_text(ledger_path)
        return ledger_title(text), ledger_rel, None, text

    roadmap = read_text(root / "notes" / "roadmap.md")
    if roadmap:
        active = section(roadmap, "Active Epic")
        values: dict[str, str] = {}
        for key in ("name", "ledger", "state"):
            match = re.search(rf"^-\s*{key}:\s*(.+?)\s*$", active, flags=re.MULTILINE)
            if match:
                values[key] = match.group(1).strip()
        ledger = values.get("ledger")
        if ledger and ledger not in {"none", "null"}:
            try:
                ledger_rel = normalize_repo_path(root, ledger)
                text = read_text(ensure_repo_path(root, ledger_rel))
            except ValueError:
                return values.get("name"), ledger, values.get("state", "").lower() or None, ""
            return values.get("name"), ledger_rel, values.get("state", "").lower() or None, text

    epics = root / "notes" / "epics"
    if epics.exists():
        candidates: list[Path] = []
        completed: list[Path] = []
        for path in sorted(epics.glob("*.md"), key=lambda item: item.stat().st_mtime, reverse=True):
            text = read_text(path)
            if status_is_active(section(text, "Status")):
                candidates.append(path)
            elif status_is_complete(section(text, "Status")) and review_results(review_lines(text)) == ["pass"]:
                completed.append(path)
        selected = candidates[0] if len(candidates) == 1 else completed[0] if not candidates and len(completed) == 1 else None
        if selected:
            text = read_text(selected)
            return ledger_title(text), selected.relative_to(root).as_posix(), None, text
    return None, None, None, ""


def latest_lines(text: str, section_name: str, limit: int = 8) -> list[str]:
    lines = [line.strip() for line in section(text, section_name).splitlines() if line.strip()]
    return lines[-limit:]


def latest_verification_lines(text: str, limit: int = 3) -> list[str]:
    entries: list[list[str]] = []
    current: list[str] = []
    for raw_line in section(text, "Verification Log").splitlines():
        line = raw_line.strip()
        if line.startswith("- command:"):
            if current:
                entries.append(current)
            current = [line]
        elif line and current:
            current.append(line)
    if current:
        entries.append(current)
    return [line for entry in entries[-limit:] for line in entry]


def current_milestone(ledger_text: str) -> str | None:
    milestones = section(ledger_text, "Milestones")
    for line in milestones.splitlines():
        stripped = line.strip()
        if stripped.startswith("- [ ]") or stripped.startswith("- [-]"):
            return re.sub(r"^- \[[ xX-]\]\s*", "", stripped).strip()
    done = None
    for line in milestones.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("- [x]"):
            done = re.sub(r"^- \[[xX]\]\s*", "", stripped).strip()
    return done


def review_lines(ledger_text: str) -> list[str]:
    raw_lines = section(ledger_text, "Review").splitlines()
    starts = [index for index, line in enumerate(raw_lines) if re.match(r"^\s*-\s*reviewed-at:\s*", line)]
    if starts:
        return [line.strip() for line in raw_lines[starts[-1] :] if line.strip()]
    review_section = [line.strip() for line in raw_lines if line.strip()]
    if review_section:
        return review_section
    decisions = [line for line in latest_lines(ledger_text, "Decisions", limit=20) if "review" in line.lower()]
    return decisions[-12:]


def latest_review_entry(ledger_text: str) -> dict[str, object]:
    return review_snapshot.latest_review_entry(ledger_text)


def blocking_open_loops(open_loops: list[str]) -> list[str]:
    non_blocking = {"none", "- none", "none found", "- none found", "n/a", "- n/a"}
    return [line for line in open_loops if line.strip().lower() not in non_blocking]


def review_has_blocker(review: list[str]) -> bool:
    semantic_lines = []
    for line in review:
        normalized = re.sub(r"^-\s*", "", line.strip()).lower()
        if normalized.startswith(("notes:", "finding:", "findings:", "review:")):
            semantic_lines.append(line)
    return any(REVIEW_BLOCKER_RE.search(line) and not REVIEW_CLEAR_RE.search(line) for line in semantic_lines)


def review_results(review: list[str]) -> list[str]:
    results: list[str] = []
    for line in review:
        match = REVIEW_RESULT_RE.search(line) or REVIEW_SECTION_RESULT_RE.search(line)
        if match:
            results.append(match.group(2).lower())
    return results[-1:]


def latest_review_evidence(review: list[str]) -> list[str]:
    latest_index = 0
    for index, line in enumerate(review):
        if REVIEW_RESULT_RE.search(line) or REVIEW_SECTION_RESULT_RE.search(line):
            latest_index = index
    return review[latest_index:]


def verification_results(verification: list[str]) -> list[str]:
    results: list[str] = []
    for line in verification:
        match = VERIFICATION_RESULT_RE.search(line)
        if match:
            results.append(match.group(2).lower())
    return results


def commit_gate_errors(
    ledger_path: str | None,
    active_epic_state: str | None,
    ledger_text: str,
    verification: list[str],
    review: list[str],
    open_loops: list[str],
) -> list[str]:
    errors: list[str] = []
    if not ledger_path or not ledger_text:
        errors.append("missing active ledger")
    if active_epic_state == "blocked":
        errors.append("active epic state is blocked")
    if not verification:
        errors.append("missing verification log evidence")
    else:
        results = verification_results(verification)
        if not results:
            errors.append("verification log lacks structured result markers")
        elif any(result in {"fail", "blocked"} for result in results):
            errors.append("verification log contains failing or blocked check")
    if not review:
        errors.append("missing review evidence")
    else:
        results = review_results(review)
        if not results:
            errors.append("review evidence lacks structured result marker")
        elif any(result in {"pending", "fail", "blocked"} for result in results):
            errors.append("review evidence indicates blocking or unresolved findings")
        elif review_has_blocker(latest_review_evidence(review)):
            errors.append("review evidence indicates blocking or unresolved findings")
    if blocking_open_loops(open_loops):
        errors.append("open loops remain unresolved")
    return errors


def guess_area(files: list[GitFile]) -> str:
    paths = [item.path for item in files]
    if any(path.endswith(".py") for path in paths):
        return "python"
    if any(path.endswith((".ts", ".tsx", ".js", ".jsx")) for path in paths):
        return "app"
    if paths and all(path.startswith(("notes/", "docs/")) or path.endswith(".md") for path in paths):
        return "docs"
    if any(path.startswith("tests/") or "/tests/" in path for path in paths):
        return "test"
    return "deepdone"


def make_subject(area: str, milestone: str | None, files: list[GitFile]) -> str:
    if milestone:
        raw = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", milestone.lower())).strip()
        summary = " ".join(raw.split()[:8]) or "update workflow"
    else:
        summary = f"update {len(files)} files"
    subject = f"{area}: {summary}"
    return subject if len(subject) <= 72 else subject[:69].rstrip() + "..."


def format_evidence(lines: list[str], nested: bool = False) -> list[str]:
    item_indent = "  " if nested else ""
    detail_indent = "    " if nested else "  "
    formatted: list[str] = []
    for index, line in enumerate(lines):
        if line.startswith("- "):
            formatted.append(item_indent + line)
        elif index == 0:
            formatted.append(item_indent + "- " + line)
        else:
            formatted.append(detail_indent + line)
    return formatted


def build_message(epic: str | None, milestone: str | None, verification: list[str], review: list[str], files: list[GitFile]) -> str:
    lines = [
        make_subject(guess_area(files), milestone, files),
        "",
        "DeepDone:",
        f"- Epic: {epic or 'none'}",
        f"- Milestone: {milestone or 'none'}",
        "- Verification:",
    ]
    lines.extend(format_evidence(verification or ["not found in active ledger"], nested=True))
    lines.append("- Review:")
    lines.extend(format_evidence(review or ["not found in active ledger"], nested=True))
    if any(item.path == "notes/roadmap.md" or item.path.startswith("notes/epics/") for item in files):
        lines.append("- Workflow state: roadmap or epic ledger updates included")
    return "\n".join(lines).rstrip() + "\n"


def load_manifest(root: Path, manifest_value: str) -> tuple[str, Path, dict[str, object]]:
    manifest_rel = normalize_repo_path(root, manifest_value)
    manifest_path = ensure_repo_path(root, manifest_rel)
    if not manifest_path.exists():
        raise ValueError(f"Reviewed change-set manifest does not exist: {manifest_rel}")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Reviewed change-set manifest is malformed: {manifest_rel}") from exc
    if not isinstance(data, dict):
        raise ValueError("Reviewed change-set manifest root must be an object")
    return manifest_rel, manifest_path, data


def logical_paths(item: GitFile) -> set[str]:
    paths = {item.path}
    if item.old_path:
        paths.add(item.old_path)
    return paths


def tree_diff_paths(root: Path, left: str, right: str) -> set[str]:
    return diff_path_set(root, ["git", "diff", "--name-only", "-z", "--no-renames", left, right])


def validate_manifest_evidence(root: Path, manifest: dict[str, object]) -> list[str]:
    errors: list[str] = []
    raw_evidence = manifest.get("evidence")
    if not isinstance(raw_evidence, list) or not raw_evidence:
        return ["reviewed change set has no development evidence"]
    roles: set[str] = set()
    for raw in raw_evidence:
        if not isinstance(raw, dict):
            errors.append("reviewed change set has malformed development evidence")
            continue
        role = str(raw.get("role", ""))
        if role not in review_snapshot.ALLOWED_EVIDENCE_ROLES:
            errors.append(f"reviewed change set has unsupported evidence role: {role}")
            continue
        try:
            path = normalize_repo_path(root, str(raw.get("path", "")))
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if role in roles:
            errors.append(f"reviewed change set repeats evidence role: {role}")
            continue
        roles.add(role)
        try:
            current = review_snapshot.filesystem_evidence(root, role, path)
        except ValueError:
            errors.append(f"development evidence changed after review: {path}")
            continue
        if any(current.get(key) != raw.get(key) for key in ("role", "path", "kind", "mode", "sha256")):
            errors.append(f"development evidence changed after review: {path}")
    if "ledger" not in roles:
        errors.append("reviewed change set has no ledger evidence")
    return errors


def validate_reviewed_change_set(
    root: Path,
    ledger_path: str | None,
    ledger_text: str,
    manifest_value: str | None,
    all_files: list[GitFile],
) -> tuple[list[GitFile], list[GitFile], list[str], list[str], list[str], str | None, Path | None, set[str]]:
    errors: list[str] = []
    stale: list[str] = []
    entry = latest_review_entry(ledger_text) if ledger_text else {}
    entry_manifest = str(entry.get("manifest", ""))
    chosen_manifest = manifest_value or entry_manifest or None
    if entry.get("result") != "pass":
        errors.append("latest Review result is not pass")
    for field in ("review-id", "base-head", "manifest", "evidence"):
        if not entry.get(field):
            errors.append(f"latest passing Review lacks {field}")
    entry_scope = entry.get("scope")
    if (
        not isinstance(entry_scope, dict)
        or not isinstance(entry_scope.get("include"), list)
        or not entry_scope.get("include")
    ):
        errors.append("latest passing Review lacks scope")
    if not chosen_manifest:
        errors.append("latest passing review has no reviewed change-set manifest")
        excluded = [item for item in all_files if not is_local_only(item.path)]
        return [], excluded, errors, stale, staged_unowned, None, None, set()

    manifest_rel: str | None = None
    manifest_path: Path | None = None
    manifest: dict[str, object] = {}
    try:
        manifest_rel, manifest_path, manifest = load_manifest(root, chosen_manifest)
    except ValueError as exc:
        errors.append(str(exc))
        excluded = [item for item in all_files if not is_local_only(item.path)]
        return [], excluded, errors, stale, staged_unowned, manifest_rel, manifest_path, set()

    if entry_manifest:
        try:
            normalized_entry_manifest = normalize_repo_path(root, entry_manifest)
        except ValueError as exc:
            errors.append(str(exc))
        else:
            if manifest_rel != normalized_entry_manifest:
                errors.append("explicit manifest does not match latest Review entry")
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        errors.append("reviewed change-set schema version is unsupported")
    if ledger_path and manifest.get("ledger_path") != ledger_path:
        errors.append("reviewed change-set ledger does not match selected ledger")
    if manifest.get("review_id") != entry.get("review-id"):
        errors.append("reviewed change-set review ID does not match latest Review entry")
    if manifest.get("base_head") != entry.get("base-head"):
        errors.append("reviewed change-set base HEAD does not match latest Review entry")
    manifest_scope = manifest.get("scope")
    if isinstance(entry_scope, dict) and isinstance(manifest_scope, dict):
        try:
            normalized_entry_scope = {
                "include": [
                    review_snapshot.normalize_scope_root(root, str(value))
                    for value in entry_scope.get("include", [])
                ],
                "exclude": [
                    review_snapshot.normalize_scope_root(root, str(value))
                    for value in entry_scope.get("exclude", [])
                ],
            }
        except ValueError as exc:
            errors.append(str(exc))
        else:
            if manifest_scope != normalized_entry_scope:
                errors.append("reviewed change-set scope does not match latest Review entry")
    else:
        errors.append("reviewed change-set scope is malformed")

    entry_evidence = entry.get("evidence")
    raw_manifest_evidence = manifest.get("evidence")
    if isinstance(entry_evidence, dict) and isinstance(raw_manifest_evidence, list):
        try:
            expected_evidence = {
                role: normalize_repo_path(root, str(path))
                for role, path in entry_evidence.items()
            }
        except ValueError as exc:
            errors.append(str(exc))
            expected_evidence = {}
        actual_evidence = {
            str(item.get("role", "")): str(item.get("path", ""))
            for item in raw_manifest_evidence
            if isinstance(item, dict)
        }
        if expected_evidence != actual_evidence:
            errors.append("reviewed change-set evidence does not match latest Review entry")
    else:
        errors.append("reviewed change-set evidence is malformed")
    code, current_head, _ = run(["git", "rev-parse", "HEAD"], root)
    if code != 0 or manifest.get("base_head") != current_head:
        errors.append("repository HEAD changed after review")

    review_id = str(manifest.get("review_id", ""))
    base_head = str(manifest.get("base_head", ""))
    review_ref = str(manifest.get("review_ref", ""))
    review_commit = str(manifest.get("review_commit", ""))
    review_tree = str(manifest.get("review_tree", ""))
    expected_ref = f"{review_snapshot.REVIEW_REF_PREFIX}{review_id}"
    if review_ref != expected_ref:
        errors.append("reviewed change set has invalid private review ref")
    if review_snapshot.ref_oid(root, review_ref) != review_commit:
        errors.append("private review ref is missing or changed")
    commit_tree_code, commit_tree, _ = run(["git", "rev-parse", f"{review_commit}^{{tree}}"], root)
    if commit_tree_code != 0 or commit_tree != review_tree:
        errors.append("review commit tree does not match manifest")
    parent_code, parent, _ = run(["git", "rev-parse", f"{review_commit}^"], root)
    if parent_code != 0 or parent != base_head:
        errors.append("review commit parent does not match base HEAD")

    try:
        owned = review_snapshot.changed_paths(root, base_head, review_commit)
    except ValueError as exc:
        errors.append(str(exc))
        owned = set()
    if not owned:
        errors.append("reviewed change set has no Git paths")
    if manifest.get("commit_path_count") != len(owned):
        errors.append("reviewed change-set path count does not match Git snapshot")

    errors.extend(validate_manifest_evidence(root, manifest))
    if owned and base_head and review_tree:
        try:
            current_tree = review_snapshot.build_tree_from_worktree(root, base_head, owned)
        except ValueError as exc:
            errors.append(str(exc))
        else:
            if current_tree != review_tree:
                stale = sorted(tree_diff_paths(root, review_tree, current_tree))
                errors.append("reviewed Git snapshot changed after review")

    reviewed = [item for item in all_files if not logical_paths(item).isdisjoint(owned)]
    excluded = [
        item
        for item in all_files
        if logical_paths(item).isdisjoint(owned) and not is_local_only(item.path)
    ]
    try:
        staged_paths = diff_path_set(root, ["git", "diff", "--cached", "--name-only", "-z", "--no-renames"])
    except RuntimeError as exc:
        errors.append(str(exc))
        staged_paths = set()
    staged_unowned = sorted(staged_paths.difference(owned))
    if staged_unowned:
        errors.append("staged paths exist outside reviewed change set")
    dangerous = sorted(path for path in owned if is_dangerous(path))
    if dangerous:
        errors.append("reviewed change set contains dangerous paths")
    return reviewed, excluded, errors, sorted(set(stale)), sorted(set(staged_unowned)), manifest_rel, manifest_path, owned


def render_file(item: GitFile) -> str:
    path = f"{item.old_path} -> {item.path}" if item.old_path else item.path
    return f"- `{item.status.strip() or item.status}` `{path}`"


def render_candidate(candidate: dict[str, object], message: str) -> str:
    def files(name: str) -> str:
        values = candidate.get(name, [])
        return "\n".join(render_file(GitFile(**value)) for value in values) if values else "- none"

    gate_errors = candidate.get("commit_gate_errors", [])
    scope = candidate.get("reviewed_scope", {})
    include = scope.get("include", []) if isinstance(scope, dict) else []
    exclude = scope.get("exclude", []) if isinstance(scope, dict) else []
    scope_lines = [f"- include: `{value}`" for value in include]
    scope_lines.extend(f"- exclude: `{value}`" for value in exclude)
    return (
        "# DeepDone Commit Candidate\n\n"
        "## Message\n\n```text\n" + message + "```\n\n"
        "## Reviewed Git Snapshot\n\n"
        f"- ref: `{candidate.get('review_ref')}`\n"
        f"- tree: `{candidate.get('review_tree')}`\n"
        f"- changed paths: {candidate.get('reviewed_file_count', 0)}\n"
        + ("\n".join(scope_lines) if scope_lines else "- scope: unavailable")
        + "\n\n## Reviewed Status Sample\n\n"
        + files("reviewed_files")
        + "\n\n"
        "## Excluded Unreviewed Files\n\n" + files("excluded_unreviewed_files") + "\n\n"
        "## Stale Reviewed Path Sample\n\n"
        + ("\n".join(f"- `{path}`" for path in candidate.get("stale_reviewed_files", [])) or "- none")
        + "\n\n## Staged Unowned Files\n\n"
        + ("\n".join(f"- `{path}`" for path in candidate.get("staged_unowned_files", [])) or "- none")
        + "\n\n## Excluded Local Files\n\n" + files("excluded_local_files") + "\n\n"
        "## Commit Gate\n\n"
        + ("\n".join(f"- blocked: {error}" for error in gate_errors) if gate_errors else "- pass")
        + "\n\n## JSON\n\n```json\n"
        + json.dumps(candidate, indent=2)
        + "\n```\n"
    )


def commit_authorization_errors(commit: bool, yes: bool, authorized_by: str | None) -> list[str]:
    if not commit:
        return []
    errors: list[str] = []
    if not yes:
        errors.append("actual commit requires --yes")
    if authorized_by not in {"exact-user-request", "mode"}:
        errors.append("actual commit requires --authorized-by exact-user-request|mode")
    return errors


def diff_path_set(root: Path, args: list[str]) -> set[str]:
    code, out, err = run_bytes(args, root)
    if code != 0:
        raise RuntimeError(err.decode(errors="replace").strip())
    return {os.fsdecode(path) for path in out.split(b"\0") if path}


def serialize_files(files: list[GitFile]) -> list[dict[str, object]]:
    return [{"status": item.status, "path": item.path, "old_path": item.old_path} for item in files]


def bounded(values: list, limit: int = 20) -> list:
    return values[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare or create a DeepDone commit")
    parser.add_argument("--candidate", action="store_true", help="prepare candidate only, default")
    parser.add_argument("--commit", action="store_true", help="create commit")
    parser.add_argument("--yes", action="store_true", help="confirm actual commit")
    parser.add_argument("--authorized-by", choices=("exact-user-request", "mode"), help="current-run authority source")
    parser.add_argument("--include-untracked", action="store_true", help="deprecated; manifest owns exact untracked paths")
    parser.add_argument("--message-file", help="use an existing commit message file")
    parser.add_argument("--ledger", help="explicit active or reviewed-complete epic ledger path")
    parser.add_argument("--reviewed-change-set", help="explicit latest reviewed change-set manifest")
    parser.add_argument("--output", default="-", help="candidate output path, or '-' for stdout")
    args = parser.parse_args()

    root = git_root(Path.cwd())
    if (root / ".deepdone" / "STOP").exists():
        print("Refusing: .deepdone/STOP exists", file=sys.stderr)
        return 2

    all_files = parse_status_z(root)
    excluded_local = [item for item in all_files if is_local_only(item.path)]
    meaningful_files = [item for item in all_files if not is_local_only(item.path)]
    if not meaningful_files:
        print("No changes to commit.")
        return 0

    epic, ledger_path, active_epic_state, ledger_text = parse_active_ledger(root, args.ledger)
    milestone = current_milestone(ledger_text) if ledger_text else None
    verification = latest_verification_lines(ledger_text) if ledger_text else []
    review = review_lines(ledger_text) if ledger_text else []
    open_loops = latest_lines(ledger_text, "Open Loops") if ledger_text else []
    gate_errors = commit_gate_errors(ledger_path, active_epic_state, ledger_text, verification, review, open_loops)

    reviewed, excluded, manifest_errors, stale, staged_unowned, manifest_rel, manifest_path, owned = validate_reviewed_change_set(
        root, ledger_path, ledger_text, args.reviewed_change_set, all_files
    )
    gate_errors.extend(error for error in manifest_errors if error not in gate_errors)
    message = (
        read_text(ensure_repo_path(root, args.message_file))
        if args.message_file
        else build_message(epic, milestone, verification, review, reviewed)
    )
    manifest_data: dict[str, object] = {}
    if manifest_path and manifest_path.exists():
        try:
            loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            loaded = {}
        if isinstance(loaded, dict):
            manifest_data = loaded

    candidate: dict[str, object] = {
        "epic": epic,
        "ledger_path": ledger_path,
        "active_epic_state": active_epic_state,
        "milestone": milestone,
        "reviewed_change_set": manifest_rel,
        "review_ref": manifest_data.get("review_ref"),
        "review_tree": manifest_data.get("review_tree"),
        "reviewed_scope": manifest_data.get("scope", {}),
        "reviewed_file_count": len(owned),
        "reviewed_files": serialize_files(bounded(reviewed)),
        "reviewed_files_truncated": len(reviewed) > 20,
        "excluded_unreviewed_file_count": len(excluded),
        "excluded_unreviewed_files": serialize_files(bounded(excluded)),
        "excluded_unreviewed_files_truncated": len(excluded) > 20,
        "stale_reviewed_file_count": len(stale),
        "stale_reviewed_files": bounded(stale),
        "stale_reviewed_files_truncated": len(stale) > 20,
        "staged_unowned_file_count": len(staged_unowned),
        "staged_unowned_files": bounded(staged_unowned),
        "staged_unowned_files_truncated": len(staged_unowned) > 20,
        "excluded_local_file_count": len(excluded_local),
        "excluded_local_files": serialize_files(bounded(excluded_local)),
        "verification": verification,
        "review": review,
        "open_loops": open_loops,
        "commit_gate_errors": gate_errors,
        "message": message,
    }

    if not args.commit:
        rendered = render_candidate(candidate, message)
        if args.output == "-":
            print(rendered, end="")
        else:
            output_path = ensure_repo_path(root, args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered, encoding="utf-8")
            print(f"Wrote candidate: {output_path.relative_to(root)}")
        return 0

    authorization_errors = commit_authorization_errors(args.commit, args.yes, args.authorized_by)
    if not args.reviewed_change_set:
        authorization_errors.append("actual commit requires --reviewed-change-set")
    if authorization_errors:
        print("Refusing actual commit because authorization is incomplete:", file=sys.stderr)
        for error in authorization_errors:
            print(f"- {error}", file=sys.stderr)
        return 2
    if gate_errors:
        print("Refusing actual commit because commit gates failed:", file=sys.stderr)
        for error in gate_errors:
            print(f"- {error}", file=sys.stderr)
        return 2
    if not owned or manifest_path is None:
        print("Refusing actual commit because reviewed path set is empty", file=sys.stderr)
        return 2

    review_snapshot.stage_paths_from_commit(root, str(manifest_data.get("review_commit", "")), owned)
    cached = diff_path_set(root, ["git", "diff", "--cached", "--name-only", "-z", "--no-renames"])
    if cached != owned:
        print("Refusing actual commit because cached paths differ from reviewed change set:", file=sys.stderr)
        print(f"- reviewed count: {len(owned)}", file=sys.stderr)
        print(f"- cached count: {len(cached)}", file=sys.stderr)
        print(f"- differing sample: {sorted(owned.symmetric_difference(cached))[:20]}", file=sys.stderr)
        return 2

    tree_code, staged_tree, tree_error = run(["git", "write-tree"], root)
    expected_tree = str(manifest_data.get("review_tree", ""))
    if tree_code != 0 or staged_tree != expected_tree:
        print("Refusing actual commit because staged tree differs from reviewed tree:", file=sys.stderr)
        print(f"- reviewed tree: {expected_tree}", file=sys.stderr)
        print(f"- staged tree: {staged_tree or tree_error}", file=sys.stderr)
        return 2

    temporary_message: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write(message)
            temporary_message = Path(handle.name)
        run(["git", "commit", "-F", str(temporary_message)], root, check=True)
    finally:
        if temporary_message is not None:
            temporary_message.unlink(missing_ok=True)

    committed = diff_path_set(root, ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "-z", "--no-renames", "HEAD^", "HEAD"])
    if committed != owned:
        print("Commit created but postcondition failed: committed paths differ from reviewed set", file=sys.stderr)
        print(f"- reviewed count: {len(owned)}", file=sys.stderr)
        print(f"- committed count: {len(committed)}", file=sys.stderr)
        print(f"- differing sample: {sorted(owned.symmetric_difference(committed))[:20]}", file=sys.stderr)
        return 2

    post_tree_code, committed_tree, post_tree_error = run(["git", "rev-parse", "HEAD^{tree}"], root)
    if post_tree_code != 0 or committed_tree != expected_tree:
        print("Commit created but postcondition failed: committed tree differs from reviewed tree", file=sys.stderr)
        print(f"- reviewed tree: {expected_tree}", file=sys.stderr)
        print(f"- committed tree: {committed_tree or post_tree_error}", file=sys.stderr)
        return 2
    _, commit_hash, _ = run(["git", "rev-parse", "--short", "HEAD"], root)
    print(f"Committed reviewed Git tree: {commit_hash}")
    print(f"Retained review snapshot for advance: {manifest_data.get('review_ref')}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        logging.basicConfig(level=logging.ERROR, format="%(levelname)s: %(message)s")
        logging.exception("Unhandled error while preparing DeepDone commit")
        raise SystemExit(2)
