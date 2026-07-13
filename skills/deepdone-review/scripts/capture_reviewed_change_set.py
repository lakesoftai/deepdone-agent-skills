#!/usr/bin/env python3
"""Capture exact Git evidence for the latest passing DeepDone review."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


MANIFEST_SCHEMA_VERSION = 1
REVIEW_ID_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{7,127}$")


@dataclass(frozen=True)
class StatusRecord:
    status: str
    path: str
    old_path: str | None = None


def literal_pathspec(path: str) -> str:
    return f":(literal){path}"


def run(cmd: list[str], cwd: Path, *, binary: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=not binary, check=False)


def git_root(start: Path) -> Path:
    proc = run(["git", "rev-parse", "--show-toplevel"], start)
    if proc.returncode != 0 or not proc.stdout.strip():
        raise ValueError(f"not a git repository: {proc.stderr.strip()}")
    return Path(proc.stdout.strip()).resolve()


def normalize_repo_path(root: Path, value: str) -> str:
    root = root.resolve()
    raw = Path(value)
    if raw.is_absolute():
        raise ValueError(f"absolute path is not allowed: {value}")
    relative = Path(os.path.normpath(os.fspath(raw)))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"path escapes repository: {value}")
    if not relative.parts:
        raise ValueError("repository root is not a valid reviewed path")
    parent = (root / relative).parent.resolve()
    try:
        parent.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"path parent escapes repository: {value}") from exc
    return relative.as_posix()


def section(text: str, name: str) -> str:
    match = re.search(rf"^##\s+{re.escape(name)}\s*$", text, flags=re.MULTILINE)
    if not match:
        return ""
    start = match.end()
    next_match = re.search(r"^##\s+", text[start:], flags=re.MULTILINE)
    end = start + next_match.start() if next_match else len(text)
    return text[start:end].strip("\n")


def latest_review_entry(ledger_text: str) -> dict[str, object]:
    lines = section(ledger_text, "Review").splitlines()
    starts = [index for index, line in enumerate(lines) if re.match(r"^\s*-\s*reviewed-at:\s*", line)]
    if not starts:
        return {}
    block = lines[starts[-1] :]
    entry: dict[str, object] = {}
    paths: list[str] = []
    reading_paths = False
    for raw in block:
        stripped = raw.strip()
        if re.match(r"^-\s*reviewed-at:\s*", stripped):
            entry["reviewed-at"] = stripped.split(":", 1)[1].strip()
            reading_paths = False
            continue
        if stripped == "paths:":
            reading_paths = True
            continue
        if reading_paths and re.match(r"^-\s+", stripped):
            paths.append(re.sub(r"^-\s+", "", stripped).strip().strip("`"))
            continue
        field = re.match(r"^([a-z][a-z0-9-]*):\s*(.*)$", stripped)
        if field:
            reading_paths = False
            entry[field.group(1)] = field.group(2).strip().strip("`")
    entry["paths"] = paths
    return entry


def parse_status(root: Path) -> list[StatusRecord]:
    proc = run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], root, binary=True)
    if proc.returncode != 0:
        raise ValueError(proc.stderr.decode(errors="replace").strip())
    chunks = proc.stdout.split(b"\0")
    records: list[StatusRecord] = []
    index = 0
    while index < len(chunks):
        chunk = chunks[index]
        index += 1
        if not chunk:
            continue
        if len(chunk) < 4 or chunk[2:3] != b" ":
            raise ValueError("malformed porcelain status record")
        status_text = chunk[:2].decode("ascii", errors="strict")
        path = os.fsdecode(chunk[3:])
        old_path = None
        if "R" in status_text or "C" in status_text:
            if index >= len(chunks) or not chunks[index]:
                raise ValueError(f"missing rename source for {path}")
            old_path = os.fsdecode(chunks[index])
            index += 1
        records.append(StatusRecord(status=status_text, path=path, old_path=old_path))
    return records


def gitlink_evidence(root: Path, path: str) -> tuple[str, str] | None:
    proc = run(["git", "ls-files", "-s", "--", literal_pathspec(path)], root)
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    first = proc.stdout.splitlines()[0].split()
    if len(first) >= 2 and first[0] == "160000":
        return "gitlink", first[1]
    return None


def path_evidence(root: Path, record: StatusRecord) -> dict[str, object]:
    absolute = root / normalize_repo_path(root, record.path)

    kind: str
    mode: str | None
    digest: str | None
    if absolute.is_symlink():
        kind = "symlink"
        mode = "symlink"
        digest = hashlib.sha256(b"symlink\0" + os.fsencode(os.readlink(absolute))).hexdigest()
    elif absolute.is_file():
        info = absolute.stat()
        kind = "file"
        mode = format(stat.S_IMODE(info.st_mode), "04o")
        hasher = hashlib.sha256()
        with absolute.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
        digest = hasher.hexdigest()
    elif absolute.is_dir() and (gitlink := gitlink_evidence(root, record.path)):
        kind, digest = gitlink
        mode = "160000"
    elif not absolute.exists():
        kind = "deleted"
        mode = None
        digest = None
    else:
        raise ValueError(f"unsupported reviewed path type: {record.path}")

    return {
        "path": record.path,
        "old_path": record.old_path,
        "status": record.status,
        "index_status": record.status[0],
        "worktree_status": record.status[1],
        "kind": kind,
        "mode": mode,
        "sha256": digest,
    }


def validate_entry(root: Path, ledger_rel: str, entry: dict[str, object]) -> tuple[str, str, str, list[str]]:
    if entry.get("result") != "pass":
        raise ValueError("latest Review result is not pass")
    review_id = str(entry.get("review-id", ""))
    if not REVIEW_ID_RE.fullmatch(review_id):
        raise ValueError("latest Review has invalid or missing review-id")
    base_head = str(entry.get("base-head", ""))
    head = run(["git", "rev-parse", "HEAD"], root)
    if head.returncode != 0 or base_head != head.stdout.strip():
        raise ValueError("latest Review base-head does not match current HEAD")
    manifest_rel = normalize_repo_path(root, str(entry.get("manifest", "")))
    expected_manifest = f".deepdone/reviews/{review_id}.json"
    if manifest_rel != expected_manifest:
        raise ValueError(f"manifest must be {expected_manifest}")
    raw_paths = entry.get("paths", [])
    if not isinstance(raw_paths, list) or not raw_paths:
        raise ValueError("latest Review has no reviewed paths")
    paths = [normalize_repo_path(root, str(path)) for path in raw_paths]
    if len(paths) != len(set(paths)):
        raise ValueError("latest Review contains duplicate paths")
    if ledger_rel not in paths:
        raise ValueError("reviewed paths must include the epic ledger")
    if manifest_rel in paths or any(path.startswith(".deepdone/reviews/") for path in paths):
        raise ValueError("review manifest cannot review itself")
    return review_id, base_head, manifest_rel, paths


def capture(root: Path, ledger_value: str) -> Path:
    root = root.resolve()
    ledger_rel = normalize_repo_path(root, ledger_value)
    ledger_path = root / ledger_rel
    try:
        ledger_text = ledger_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValueError(f"ledger does not exist: {ledger_rel}") from exc
    entry = latest_review_entry(ledger_text)
    review_id, base_head, manifest_rel, reviewed_paths = validate_entry(root, ledger_rel, entry)

    records = parse_status(root)
    by_path = {record.path: record for record in records}
    rename_sources = {record.old_path for record in records if record.old_path}
    evidence: list[dict[str, object]] = []
    for path in reviewed_paths:
        if path in rename_sources and path not in by_path:
            raise ValueError(f"list rename destination, not source, in Review paths: {path}")
        record = by_path.get(path)
        if record is None:
            raise ValueError(f"reviewed path is not dirty: {path}")
        evidence.append(path_evidence(root, record))

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "review_id": review_id,
        "ledger_path": ledger_rel,
        "base_head": base_head,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "paths": sorted(evidence, key=lambda item: str(item["path"])),
    }
    manifest_path = root / manifest_rel
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=manifest_path.parent, delete=False) as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(manifest_path)

    for candidate in manifest_path.parent.glob("*.json"):
        if candidate == manifest_path:
            continue
        try:
            prior = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if prior.get("ledger_path") == ledger_rel:
            candidate.unlink(missing_ok=True)
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", required=True, help="repository-relative epic ledger path")
    args = parser.parse_args()
    try:
        root = git_root(Path.cwd())
        if (root / ".deepdone" / "STOP").exists():
            raise ValueError(".deepdone/STOP exists")
        manifest = capture(root, args.ledger)
    except (OSError, ValueError) as exc:
        print(f"Refusing review capture: {exc}", file=sys.stderr)
        return 2
    print(manifest.relative_to(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
