#!/usr/bin/env python3
"""Gate advance on committed reviewed code and unchanged development evidence."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from capture_reviewed_change_set import (  # noqa: E402
    REVIEW_REF_PREFIX,
    build_tree_from_commit,
    changed_paths,
    delete_ref,
    filesystem_evidence,
    git_root,
    latest_review_entry,
    normalize_repo_path,
    ref_oid,
    run,
    section,
)


import verification  # noqa: E402

MANIFEST_SCHEMA_VERSION = 2
LEGACY_MANIFEST_SCHEMA_VERSION = 1


def dirty_paths(root: Path) -> set[str]:
    proc = run(["git", "--no-optional-locks", "status", "--porcelain=v1", "-z", "--untracked-files=all"], root, binary=True)
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
        paths.add(os.fsdecode(chunk[3:]))
        if "R" in status_text or "C" in status_text:
            if index >= len(chunks) or not chunks[index]:
                raise ValueError("missing rename source in Git status")
            paths.add(os.fsdecode(chunks[index]))
            index += 1
    return paths


def load_entry_and_manifest(root: Path, ledger_value: str) -> tuple[str, dict[str, object], Path | None, dict[str, object] | None]:
    ledger_rel = normalize_repo_path(root, ledger_value)
    ledger_path = root / ledger_rel
    try:
        entry = latest_review_entry(ledger_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"ledger does not exist: {ledger_rel}") from exc
    if entry.get("result") != "pass":
        raise ValueError("latest Review result is not pass")

    manifest_value = str(entry.get("manifest", ""))
    if not manifest_value:
        return ledger_rel, entry, None, None
    manifest_rel = normalize_repo_path(root, manifest_value)
    manifest_path = root / manifest_rel
    if not manifest_path.exists():
        return ledger_rel, entry, manifest_path, None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("review manifest is malformed") from exc
    if not isinstance(manifest, dict):
        raise ValueError("review manifest root must be an object")
    return ledger_rel, entry, manifest_path, manifest


def validate_manifest_identity(
    root: Path,
    ledger_rel: str,
    entry: dict[str, object],
    manifest: dict[str, object],
) -> tuple[str, str, str, str]:
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ValueError("review manifest schema version is unsupported")
    if manifest.get("ledger_path") != ledger_rel:
        raise ValueError("review manifest ledger does not match selected ledger")
    if manifest.get("review_id") != entry.get("review-id"):
        raise ValueError("review manifest does not match latest Review ID")
    if manifest.get("base_head") != entry.get("base-head"):
        raise ValueError("review manifest does not match latest Review base HEAD")

    review_id = str(manifest.get("review_id", ""))
    base_head = str(manifest.get("base_head", ""))
    ref = str(manifest.get("review_ref", ""))
    review_commit = str(manifest.get("review_commit", ""))
    review_tree = str(manifest.get("review_tree", ""))
    expected_ref = f"{REVIEW_REF_PREFIX}{review_id}"
    if ref != expected_ref:
        raise ValueError("review manifest has invalid private review ref")
    if ref_oid(root, ref) != review_commit:
        raise ValueError("private review ref is missing or changed")
    commit_tree = run(["git", "rev-parse", f"{review_commit}^{{tree}}"], root)
    if commit_tree.returncode != 0 or commit_tree.stdout.strip() != review_tree:
        raise ValueError("review commit tree does not match manifest")
    parent = run(["git", "rev-parse", f"{review_commit}^"], root)
    if parent.returncode != 0 or parent.stdout.strip() != base_head:
        raise ValueError("review commit parent does not match base HEAD")
    return base_head, ref, review_commit, review_tree


def validate_evidence(root: Path, manifest: dict[str, object]) -> None:
    raw_evidence = manifest.get("evidence")
    if not isinstance(raw_evidence, list) or not raw_evidence:
        raise ValueError("review manifest has no development evidence")
    seen_roles: set[str] = set()
    for raw in raw_evidence:
        if not isinstance(raw, dict):
            raise ValueError("review manifest has malformed development evidence")
        role = str(raw.get("role", ""))
        path = normalize_repo_path(root, str(raw.get("path", "")))
        if role in seen_roles:
            raise ValueError(f"review manifest repeats evidence role: {role}")
        seen_roles.add(role)
        try:
            current = filesystem_evidence(root, role, path)
        except ValueError as exc:
            raise ValueError(f"development evidence changed after review: {path}") from exc
        for key in ("role", "path", "kind", "mode", "sha256"):
            if current.get(key) != raw.get(key):
                raise ValueError(f"development evidence changed after review: {path}")
    if "ledger" not in seen_roles:
        raise ValueError("review manifest has no ledger evidence")


def validate_committed_snapshot(
    root: Path,
    base_head: str,
    review_commit: str,
    review_tree: str,
    reviewed: set[str],
    dirty: set[str],
) -> None:
    head = run(["git", "rev-parse", "HEAD"], root)
    if head.returncode != 0 or not head.stdout.strip():
        raise ValueError("cannot resolve current HEAD")
    projected = build_tree_from_commit(root, base_head, head.stdout.strip(), reviewed)
    if projected == review_tree:
        return
    if head.stdout.strip() == base_head and reviewed.intersection(dirty):
        return
    raise ValueError("committed reviewed code does not match review snapshot")


def check(root: Path, ledger_value: str) -> tuple[list[str], list[str]]:
    root = root.resolve()
    if (root / ".deepdone/STOP").exists():
        raise ValueError(".deepdone/STOP exists")
    ledger_rel, entry, manifest_path, manifest = load_entry_and_manifest(root, ledger_value)
    all_dirty = dirty_paths(root)
    ledger_text = (root / ledger_rel).read_text(encoding="utf-8")
    new_evidence = verification.contract_span(ledger_text) is not None or (root / verification.namespace(ledger_rel)).exists()

    entry_scope = entry.get("scope")
    schema_v2_entry = (
        isinstance(entry_scope, dict)
        and bool(entry_scope.get("include"))
        and bool(entry.get("evidence"))
    )
    if manifest is None:
        if new_evidence:
            raise ValueError("schema-v2 review manifest is missing; verification contract requires intact review manifest")
        if schema_v2_entry:
            raise ValueError("schema-v2 review manifest is missing")
        if all_dirty:
            raise ValueError("legacy passing review cannot advance while repository is dirty")
        return [], []
    if manifest.get("schema_version") == LEGACY_MANIFEST_SCHEMA_VERSION:
        if new_evidence:
            raise ValueError("verification contract cannot use legacy manifest compatibility")
        if schema_v2_entry:
            raise ValueError("schema-v2 review entry cannot downgrade to a legacy manifest")
        if manifest.get("ledger_path") != ledger_rel or manifest.get("review_id") != entry.get("review-id"):
            raise ValueError("ambiguous historical manifest identity")
        validate_evidence(root, manifest)
        if all_dirty:
            raise ValueError("legacy passing review cannot advance while repository is dirty")
        return [], []

    base_head, _, review_commit, review_tree = validate_manifest_identity(root, ledger_rel, entry, manifest)
    validate_evidence(root, manifest)
    reviewed = changed_paths(root, base_head, review_commit)
    if len(reviewed) != manifest.get("commit_path_count"):
        raise ValueError("review manifest path count does not match Git snapshot")
    errors = verification.validate(root, ledger_rel, text=ledger_text, owned=reviewed) if new_evidence else []
    if errors:
        raise ValueError("; ".join(errors))
    if not new_evidence and all_dirty:
        raise ValueError("legacy passing review cannot advance while repository is dirty")
    dirty_reviewed = sorted(reviewed.intersection(all_dirty))
    validate_committed_snapshot(root, base_head, review_commit, review_tree, reviewed, all_dirty)
    return dirty_reviewed, sorted(reviewed)


def roadmap_has_advanced(root: Path, completed_ledger: str) -> bool:
    roadmap_path = root / "notes" / "roadmap.md"
    if not roadmap_path.is_file():
        return False
    active = section(roadmap_path.read_text(encoding="utf-8"), "Active Epic")
    match = re.search(r"^-\s*ledger:\s*(.+?)\s*$", active, flags=re.MULTILINE)
    if not match:
        return False
    current = match.group(1).strip().strip("`")
    if current in {"none", "null"}:
        return True
    try:
        return normalize_repo_path(root, current) != completed_ledger
    except ValueError:
        return False


def cleanup(root: Path, ledger_value: str, *, require_advanced: bool = False) -> tuple[Path, str]:
    root = root.resolve()
    ledger_rel, entry, manifest_path, manifest = load_entry_and_manifest(root, ledger_value)
    if manifest_path is None or manifest is None:
        raise ValueError("schema-v2 review manifest is required for cleanup")
    if require_advanced and not roadmap_has_advanced(root, ledger_rel):
        raise ValueError("roadmap has not advanced beyond completed ledger")
    base_head, ref, review_commit, review_tree = validate_manifest_identity(root, ledger_rel, entry, manifest)
    reviewed = changed_paths(root, base_head, review_commit)
    all_dirty = dirty_paths(root)
    dirty_reviewed = reviewed.intersection(all_dirty)
    if dirty_reviewed:
        raise ValueError(f"reviewed code remains dirty: {len(dirty_reviewed)} paths")
    validate_committed_snapshot(root, base_head, review_commit, review_tree, reviewed, all_dirty)
    delete_ref(root, ref, review_commit)
    manifest_path.unlink()
    return manifest_path, ref


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", required=True, help="repository-relative epic ledger path")
    parser.add_argument(
        "--cleanup-after-advance",
        action="store_true",
        help="remove exact validated manifest and private ref after durable advance state is written",
    )
    args = parser.parse_args()
    try:
        root = git_root(Path.cwd())
        if (root / ".deepdone" / "STOP").exists():
            raise ValueError(".deepdone/STOP exists")
        if args.cleanup_after_advance:
            manifest_path, ref = cleanup(root, args.ledger, require_advanced=True)
            print(f"Removed advanced review snapshot: {manifest_path.relative_to(root)} and {ref}")
            return 0
        dirty, reviewed = check(root, args.ledger)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Refusing advance: {exc}", file=sys.stderr)
        return 2
    if dirty:
        print(f"Refusing advance: {len(dirty)} reviewed Git paths remain dirty", file=sys.stderr)
        for path in dirty[:20]:
            print(f"- {path}", file=sys.stderr)
        if len(dirty) > 20:
            print(f"- ... {len(dirty) - 20} more", file=sys.stderr)
        return 2
    print(f"Reviewed Git snapshot is committed and clean: {len(reviewed)} paths")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
