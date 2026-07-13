#!/usr/bin/env python3
"""Block DeepDone advance while reviewed paths remain dirty."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


MANIFEST_SCHEMA_VERSION = 1


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


def latest_review_entry(text: str) -> dict[str, object]:
    lines = section(text, "Review").splitlines()
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


def dirty_paths(root: Path) -> set[str]:
    proc = run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], root, binary=True)
    if proc.returncode != 0:
        raise ValueError(proc.stderr.decode(errors="replace").strip())
    chunks = proc.stdout.split(b"\0")
    paths: set[str] = set()
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
        paths.add(path)
        if "R" in status_text or "C" in status_text:
            if index >= len(chunks) or not chunks[index]:
                raise ValueError(f"missing rename source for {path}")
            paths.add(os.fsdecode(chunks[index]))
            index += 1
    return paths


def check(root: Path, ledger_value: str) -> tuple[list[str], list[str]]:
    root = root.resolve()
    ledger_rel = normalize_repo_path(root, ledger_value)
    ledger_path = root / ledger_rel
    try:
        entry = latest_review_entry(ledger_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"ledger does not exist: {ledger_rel}") from exc
    if entry.get("result") != "pass":
        raise ValueError("latest Review result is not pass")

    all_dirty = dirty_paths(root)
    raw_paths = entry.get("paths", [])
    reviewed = [normalize_repo_path(root, str(path)) for path in raw_paths] if isinstance(raw_paths, list) else []
    if not reviewed:
        if all_dirty:
            raise ValueError("legacy passing review has no exact paths while repository is dirty")
        return [], []

    manifest_value = str(entry.get("manifest", ""))
    if manifest_value:
        manifest_rel = normalize_repo_path(root, manifest_value)
        manifest_path = root / manifest_rel
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError("review manifest is malformed") from exc
            if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
                raise ValueError("review manifest schema version is unsupported")
            if manifest.get("ledger_path") != ledger_rel or manifest.get("review_id") != entry.get("review-id"):
                raise ValueError("review manifest does not match latest Review entry")

    dirty_reviewed = sorted(path for path in reviewed if path in all_dirty)
    return dirty_reviewed, reviewed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", required=True, help="repository-relative epic ledger path")
    args = parser.parse_args()
    try:
        root = git_root(Path.cwd())
        if (root / ".deepdone" / "STOP").exists():
            raise ValueError(".deepdone/STOP exists")
        dirty, reviewed = check(root, args.ledger)
    except (OSError, ValueError) as exc:
        print(f"Refusing advance: {exc}", file=sys.stderr)
        return 2
    if dirty:
        print("Refusing advance: reviewed paths remain dirty", file=sys.stderr)
        for path in dirty:
            print(f"- {path}", file=sys.stderr)
        return 2
    print(f"Reviewed change set is clean: {len(reviewed)} paths")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
