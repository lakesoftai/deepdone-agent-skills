#!/usr/bin/env python3
"""Prepare or create a DeepDone commit from one reviewed change set."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


MANIFEST_SCHEMA_VERSION = 1

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


def literal_pathspec(path: str) -> str:
    return f":(literal){path}"


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
    lines = section(ledger_text, "Review").splitlines()
    starts = [index for index, line in enumerate(lines) if re.match(r"^\s*-\s*reviewed-at:\s*", line)]
    if not starts:
        return {}
    entry: dict[str, object] = {}
    paths: list[str] = []
    reading_paths = False
    for raw in lines[starts[-1] :]:
        stripped = raw.strip()
        if re.match(r"^-\s*reviewed-at:\s*", stripped):
            entry["reviewed-at"] = stripped.split(":", 1)[1].strip()
            reading_paths = False
        elif stripped == "paths:":
            reading_paths = True
        elif reading_paths and re.match(r"^-\s+", stripped):
            paths.append(re.sub(r"^-\s+", "", stripped).strip().strip("`"))
        else:
            field = re.match(r"^([a-z][a-z0-9-]*):\s*(.*)$", stripped)
            if field:
                reading_paths = False
                entry[field.group(1)] = field.group(2).strip().strip("`")
    entry["paths"] = paths
    return entry


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


def gitlink_evidence(root: Path, path: str) -> tuple[str, str] | None:
    code, out, _ = run(["git", "ls-files", "-s", "--", literal_pathspec(path)], root)
    if code != 0 or not out:
        return None
    first = out.splitlines()[0].split()
    if len(first) >= 2 and first[0] == "160000":
        return "gitlink", first[1]
    return None


def path_evidence(root: Path, item: GitFile) -> dict[str, object]:
    absolute = ensure_repo_path(root, item.path)
    if absolute.is_symlink():
        kind = "symlink"
        mode = "symlink"
        digest = hashlib.sha256(b"symlink\0" + os.fsencode(os.readlink(absolute))).hexdigest()
    elif absolute.is_file():
        kind = "file"
        mode = format(stat.S_IMODE(absolute.stat().st_mode), "04o")
        hasher = hashlib.sha256()
        with absolute.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
        digest = hasher.hexdigest()
    elif absolute.is_dir() and (gitlink := gitlink_evidence(root, item.path)):
        kind, digest = gitlink
        mode = "160000"
    elif not absolute.exists():
        kind = "deleted"
        mode = None
        digest = None
    else:
        raise ValueError(f"Unsupported reviewed path type: {item.path}")
    status_text = item.status if len(item.status) == 2 else item.status.ljust(2)
    return {
        "path": item.path,
        "old_path": item.old_path,
        "status": status_text,
        "index_status": status_text[0],
        "worktree_status": status_text[1],
        "kind": kind,
        "mode": mode,
        "sha256": digest,
    }


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


def effective_paths(records: list[dict[str, object]]) -> set[str]:
    paths: set[str] = set()
    for record in records:
        path = str(record.get("path", ""))
        if path:
            paths.add(path)
        old_path = record.get("old_path")
        status_text = str(record.get("status", ""))
        if old_path and "R" in status_text:
            paths.add(str(old_path))
    return paths


def current_record_map(files: list[GitFile]) -> dict[str, GitFile]:
    return {item.path: item for item in files}


def validate_reviewed_change_set(
    root: Path,
    ledger_path: str | None,
    ledger_text: str,
    manifest_value: str | None,
    all_files: list[GitFile],
) -> tuple[list[GitFile], list[GitFile], list[str], list[str], list[str], str | None, Path | None, set[str]]:
    errors: list[str] = []
    stale: list[str] = []
    staged_unowned: list[str] = []
    entry = latest_review_entry(ledger_text) if ledger_text else {}
    entry_manifest = str(entry.get("manifest", ""))
    chosen_manifest = manifest_value or entry_manifest or None
    if entry.get("result") != "pass":
        errors.append("latest Review result is not pass")
    for field in ("review-id", "base-head", "manifest", "paths"):
        if not entry.get(field):
            errors.append(f"latest passing Review lacks {field}")
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
    code, current_head, _ = run(["git", "rev-parse", "HEAD"], root)
    if code != 0 or manifest.get("base_head") != current_head:
        errors.append("repository HEAD changed after review")

    raw_records = manifest.get("paths")
    records = raw_records if isinstance(raw_records, list) else []
    if not records or not all(isinstance(record, dict) for record in records):
        errors.append("reviewed change-set has no valid path records")
        records = []

    primary_paths: list[str] = []
    normalized_records: list[dict[str, object]] = []
    for raw_record in records:
        record = dict(raw_record)
        try:
            record["path"] = normalize_repo_path(root, str(record.get("path", "")))
            if record.get("old_path"):
                record["old_path"] = normalize_repo_path(root, str(record["old_path"]))
        except ValueError as exc:
            errors.append(str(exc))
            continue
        primary_paths.append(str(record["path"]))
        normalized_records.append(record)
    if len(primary_paths) != len(set(primary_paths)):
        errors.append("reviewed change-set contains duplicate paths")

    raw_entry_paths = entry.get("paths", [])
    try:
        entry_paths = [normalize_repo_path(root, str(path)) for path in raw_entry_paths] if isinstance(raw_entry_paths, list) else []
    except ValueError as exc:
        errors.append(str(exc))
        entry_paths = []
    if set(entry_paths) != set(primary_paths):
        errors.append("manifest paths do not match latest Review path list")

    by_path = current_record_map(all_files)
    reviewed: list[GitFile] = []
    compared_keys = ("path", "old_path", "status", "index_status", "worktree_status", "kind", "mode", "sha256")
    for expected in normalized_records:
        path = str(expected["path"])
        current = by_path.get(path)
        if current is None:
            stale.append(path)
            continue
        reviewed.append(current)
        try:
            actual = path_evidence(root, current)
        except ValueError:
            stale.append(path)
            continue
        if any(actual.get(key) != expected.get(key) for key in compared_keys):
            stale.append(path)

    owned = effective_paths(normalized_records)
    excluded: list[GitFile] = []
    for item in all_files:
        item_paths = {item.path}
        if item.old_path and "R" in item.status:
            item_paths.add(item.old_path)
        if item_paths.isdisjoint(owned) and not is_local_only(item.path):
            excluded.append(item)
            status_text = item.status if len(item.status) == 2 else item.status.ljust(2)
            if status_text[0] not in {" ", "?"}:
                staged_unowned.append(item.path)

    if stale:
        errors.append("reviewed paths changed after review")
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
    return (
        "# DeepDone Commit Candidate\n\n"
        "## Message\n\n```text\n" + message + "```\n\n"
        "## Reviewed Files\n\n" + files("reviewed_files") + "\n\n"
        "## Excluded Unreviewed Files\n\n" + files("excluded_unreviewed_files") + "\n\n"
        "## Stale Reviewed Files\n\n"
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


def commit_tree_evidence(root: Path, path: str) -> dict[str, object]:
    code, tree_out, tree_err = run_bytes(["git", "ls-tree", "-z", "HEAD", "--", literal_pathspec(path)], root)
    if code != 0:
        raise RuntimeError(tree_err.decode(errors="replace").strip())
    if not tree_out:
        return {"kind": "deleted", "mode": None, "sha256": None}
    record = tree_out.split(b"\0", 1)[0]
    metadata, _, _ = record.partition(b"\t")
    parts = metadata.decode("ascii", errors="strict").split()
    if len(parts) != 3:
        raise RuntimeError(f"Malformed tree evidence for {path}")
    git_mode, object_type, object_id = parts
    if git_mode == "160000":
        return {"kind": "gitlink", "mode": "160000", "sha256": object_id}
    code, content, content_err = run_bytes(["git", "show", f"HEAD:{path}"], root)
    if code != 0:
        raise RuntimeError(content_err.decode(errors="replace").strip())
    if git_mode == "120000":
        return {
            "kind": "symlink",
            "mode": "symlink",
            "sha256": hashlib.sha256(b"symlink\0" + content).hexdigest(),
        }
    if object_type != "blob" or git_mode not in {"100644", "100755"}:
        raise RuntimeError(f"Unsupported committed path type for {path}: {git_mode} {object_type}")
    return {
        "kind": "file",
        "mode": "0" + git_mode[-3:],
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def commit_manifest_errors(root: Path, manifest_path: Path) -> list[str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_records = manifest.get("paths", [])
    records = raw_records if isinstance(raw_records, list) else []
    errors: list[str] = []
    for expected in records:
        if not isinstance(expected, dict):
            errors.append("manifest contains malformed path record")
            continue
        path = normalize_repo_path(root, str(expected.get("path", "")))
        actual = commit_tree_evidence(root, path)
        for key in ("kind", "mode", "sha256"):
            if actual.get(key) != expected.get(key):
                errors.append(f"committed evidence differs for {path}: {key}")
        old_path = expected.get("old_path")
        if old_path and "R" in str(expected.get("status", "")):
            old_rel = normalize_repo_path(root, str(old_path))
            if commit_tree_evidence(root, old_rel)["kind"] != "deleted":
                errors.append(f"rename source remains in commit tree: {old_rel}")
    return errors


def serialize_files(files: list[GitFile]) -> list[dict[str, object]]:
    return [{"status": item.status, "path": item.path, "old_path": item.old_path} for item in files]


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

    candidate: dict[str, object] = {
        "epic": epic,
        "ledger_path": ledger_path,
        "active_epic_state": active_epic_state,
        "milestone": milestone,
        "reviewed_change_set": manifest_rel,
        "reviewed_files": serialize_files(reviewed),
        "excluded_unreviewed_files": serialize_files(excluded),
        "stale_reviewed_files": stale,
        "staged_unowned_files": staged_unowned,
        "excluded_local_files": serialize_files(excluded_local),
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

    stage_paths = {item.path for item in reviewed}
    run(["git", "add", "-A", "--", *(literal_pathspec(path) for path in sorted(stage_paths))], root, check=True)
    cached = diff_path_set(root, ["git", "diff", "--cached", "--name-only", "-z", "--no-renames"])
    if cached != owned:
        print("Refusing actual commit because cached paths differ from reviewed change set:", file=sys.stderr)
        print(f"- reviewed: {sorted(owned)}", file=sys.stderr)
        print(f"- cached: {sorted(cached)}", file=sys.stderr)
        return 2

    temporary_message: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write(message)
            temporary_message = Path(handle.name)
        run(
            ["git", "commit", "--only", "-F", str(temporary_message), "--", *(literal_pathspec(path) for path in sorted(owned))],
            root,
            check=True,
        )
    finally:
        if temporary_message is not None:
            temporary_message.unlink(missing_ok=True)

    committed = diff_path_set(root, ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "-z", "--no-renames", "HEAD^", "HEAD"])
    if committed != owned:
        print("Commit created but postcondition failed: committed paths differ from reviewed set", file=sys.stderr)
        print(f"- reviewed: {sorted(owned)}", file=sys.stderr)
        print(f"- committed: {sorted(committed)}", file=sys.stderr)
        return 2
    evidence_errors = commit_manifest_errors(root, manifest_path)
    if evidence_errors:
        print("Commit created but postcondition failed: committed content differs from review evidence", file=sys.stderr)
        for error in evidence_errors:
            print(f"- {error}", file=sys.stderr)
        return 2
    manifest_path.unlink(missing_ok=True)
    _, commit_hash, _ = run(["git", "rev-parse", "--short", "HEAD"], root)
    print(f"Committed: {commit_hash}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        logging.basicConfig(level=logging.ERROR, format="%(levelname)s: %(message)s")
        logging.exception("Unhandled error while preparing DeepDone commit")
        raise SystemExit(2)
