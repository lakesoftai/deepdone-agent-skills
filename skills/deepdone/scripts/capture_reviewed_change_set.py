#!/usr/bin/env python3
"""Capture reviewed code as a private Git snapshot plus local evidence hashes."""

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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


import work_unit

MANIFEST_SCHEMA_VERSION = 2
REVIEW_ID_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{7,127}$")
REVIEW_REF_PREFIX = "refs/deepdone/reviews/"
ALLOWED_EVIDENCE_ROLES = {"ledger", "roadmap"}


@dataclass(frozen=True)
class StatusRecord:
    status: str
    path: str
    old_path: str | None = None


def literal_pathspec(path: str) -> str:
    return f":(literal){path}"


def run(
    cmd: list[str],
    cwd: Path,
    *,
    binary: bool = False,
    env: dict[str, str] | None = None,
    input_data: str | bytes | None = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=not binary,
        check=False,
        env=env,
        input=input_data,
    )


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
        raise ValueError("repository root is not a valid path")
    parent = (root / relative).parent.resolve()
    try:
        parent.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"path parent escapes repository: {value}") from exc
    return relative.as_posix()


def normalize_scope_root(root: Path, value: str) -> str:
    value = value.strip().strip("`").rstrip("/")
    if value in {"", "."}:
        return "."
    return normalize_repo_path(root, value)


def section(text: str, name: str) -> str:
    match = re.search(rf"^##\s+{re.escape(name)}\s*$", text, flags=re.MULTILINE)
    if not match:
        return ""
    start = match.end()
    next_match = re.search(r"^##\s+", text[start:], flags=re.MULTILINE)
    end = start + next_match.start() if next_match else len(text)
    return text[start:end].strip("\n")


def review_entries(ledger_text: str) -> list[dict[str, object]]:
    lines = section(ledger_text, "Review").splitlines()
    starts = [index for index, line in enumerate(lines) if re.match(r"^\s*-\s*reviewed-at:\s*", line)]
    return [parse_review_entry(lines[start:end]) for start, end in zip(starts, starts[1:] + [len(lines)])]


def latest_review_entry(ledger_text: str) -> dict[str, object]:
    entries = review_entries(ledger_text)
    return entries[-1] if entries else {}


def parse_review_entry(lines: list[str]) -> dict[str, object]:
    entry: dict[str, object] = {"scope": {"include": [], "exclude": []}, "evidence": {}, "paths": []}
    context: str | None = None
    for raw in lines:
        stripped = raw.strip()
        indent = len(raw) - len(raw.lstrip())
        if re.match(r"^-\s*reviewed-at:\s*", stripped):
            entry["reviewed-at"] = stripped.split(":", 1)[1].strip()
            context = None
            continue
        if indent <= 2 and stripped == "scope:":
            context = "scope"
            continue
        if indent <= 2 and stripped == "evidence:":
            context = "evidence"
            continue
        if indent <= 2 and stripped == "paths:":
            context = "paths"
            continue
        if context in {"scope", "scope-include", "scope-exclude"} and indent >= 4 and stripped in {"include:", "exclude:"}:
            context = f"scope-{stripped[:-1]}"
            continue
        if context in {"scope-include", "scope-exclude"} and indent >= 4 and re.match(r"^-\s+", stripped):
            scope = entry["scope"]
            assert isinstance(scope, dict)
            key = context.removeprefix("scope-")
            values = scope[key]
            assert isinstance(values, list)
            values.append(re.sub(r"^-\s+", "", stripped).strip().strip("`"))
            continue
        if context == "paths" and indent >= 2 and re.match(r"^-\s+", stripped):
            paths = entry["paths"]
            assert isinstance(paths, list)
            paths.append(re.sub(r"^-\s+", "", stripped).strip().strip("`"))
            continue
        field = re.match(r"^([a-z][a-z0-9-]*):\s*(.*)$", stripped)
        if not field:
            continue
        if context == "evidence" and indent >= 4:
            evidence = entry["evidence"]
            assert isinstance(evidence, dict)
            evidence[field.group(1)] = field.group(2).strip().strip("`")
        elif indent <= 2:
            entry[field.group(1)] = field.group(2).strip().strip("`")
            context = None
    return entry


def parse_status(root: Path) -> list[StatusRecord]:
    proc = run(["git", "--no-optional-locks", "status", "--porcelain=v1", "-z", "--untracked-files=all"], root, binary=True)
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


def path_is_within(path: str, scope_root: str) -> bool:
    return scope_root == "." or path == scope_root or path.startswith(scope_root + "/")


def select_reviewed_records(
    records: list[StatusRecord],
    include: list[str],
    exclude: list[str],
    evidence_paths: set[str],
    ledger: str | None = None,
) -> list[StatusRecord]:
    from verification import local_artifact

    selected: list[StatusRecord] = []
    for record in records:
        if local_artifact(record.path) or (record.old_path and local_artifact(record.old_path)):
            continue
        logical_paths = {record.path}
        if record.old_path:
            logical_paths.add(record.old_path)
        unrelated = {path for path in logical_paths if work_unit.task_unowned_path(ledger, path)}
        if unrelated:
            if unrelated != logical_paths:
                raise ValueError(f'unrelated lifecycle record crosses a task source rename boundary: {sorted(logical_paths)}')
            continue
        included_paths = {
            path
            for path in logical_paths
            if any(path_is_within(path, root) for root in include)
        }
        excluded_paths = {
            path
            for path in logical_paths
            if any(path_is_within(path, root) for root in exclude)
        }
        if record.old_path and included_paths and included_paths != logical_paths:
            raise ValueError(f"rename crosses review include boundary: {sorted(logical_paths)}")
        if record.old_path and excluded_paths and excluded_paths != logical_paths:
            raise ValueError(f"rename crosses review exclude boundary: {sorted(logical_paths)}")
        if included_paths:
            if excluded_paths:
                continue
            evidence_overlap = logical_paths.intersection(evidence_paths)
            if evidence_overlap:
                if logical_paths.issubset(evidence_paths):
                    continue
                raise ValueError(f"development evidence crosses a code rename boundary: {sorted(evidence_overlap)}")
            selected.append(record)
    return selected


def pathspec_file(directory: Path, paths: set[str]) -> Path:
    target = directory / "pathspecs"
    target.write_bytes(b"".join(os.fsencode(literal_pathspec(path)) + b"\0" for path in sorted(paths)))
    return target


def stage_paths(root: Path, paths: set[str], *, env: dict[str, str] | None = None) -> None:
    if not paths:
        raise ValueError("cannot stage an empty reviewed path set")
    with tempfile.TemporaryDirectory(prefix="deepdone-pathspec-") as tmp:
        specs = pathspec_file(Path(tmp), paths)
        add = run(
            [
                "git",
                "add",
                "-A",
                f"--pathspec-from-file={specs}",
                "--pathspec-file-nul",
            ],
            root,
            env=env,
        )
        if add.returncode != 0:
            raise ValueError(f"cannot stage reviewed paths: {add.stderr.strip()}")


def stage_paths_from_commit(root: Path, source: str, paths: set[str]) -> None:
    if not paths:
        raise ValueError("cannot stage an empty reviewed path set")
    with tempfile.TemporaryDirectory(prefix="deepdone-pathspec-") as tmp:
        specs = pathspec_file(Path(tmp), paths)
        reset = run(
            [
                "git",
                "reset",
                "-q",
                source,
                f"--pathspec-from-file={specs}",
                "--pathspec-file-nul",
            ],
            root,
        )
        if reset.returncode != 0:
            raise ValueError(f"cannot stage reviewed snapshot: {reset.stderr.strip()}")


def build_tree_from_worktree(root: Path, base_head: str, paths: set[str]) -> str:
    if not paths:
        raise ValueError("review scope contains no dirty version-controlled paths")
    with tempfile.TemporaryDirectory(prefix="deepdone-review-index-") as tmp:
        tmp_path = Path(tmp)
        index_path = tmp_path / "index"
        env = os.environ.copy()
        env["GIT_INDEX_FILE"] = str(index_path)
        read = run(["git", "read-tree", base_head], root, env=env)
        if read.returncode != 0:
            raise ValueError(f"cannot seed temporary review index: {read.stderr.strip()}")
        stage_paths(root, paths, env=env)
        tree = run(["git", "write-tree"], root, env=env)
        if tree.returncode != 0 or not tree.stdout.strip():
            raise ValueError(f"cannot write review tree: {tree.stderr.strip()}")
        return tree.stdout.strip()


def build_tree_from_commit(root: Path, base_head: str, source: str, paths: set[str]) -> str:
    if not paths:
        raise ValueError("review snapshot contains no changed paths")
    with tempfile.TemporaryDirectory(prefix="deepdone-review-index-") as tmp:
        tmp_path = Path(tmp)
        index_path = tmp_path / "index"
        specs = pathspec_file(tmp_path, paths)
        env = os.environ.copy()
        env["GIT_INDEX_FILE"] = str(index_path)
        read = run(["git", "read-tree", base_head], root, env=env)
        if read.returncode != 0:
            raise ValueError(f"cannot seed temporary comparison index: {read.stderr.strip()}")
        reset = run(
            [
                "git",
                "reset",
                "-q",
                source,
                f"--pathspec-from-file={specs}",
                "--pathspec-file-nul",
            ],
            root,
            env=env,
        )
        if reset.returncode != 0:
            raise ValueError(f"cannot project committed review paths: {reset.stderr.strip()}")
        tree = run(["git", "write-tree"], root, env=env)
        if tree.returncode != 0 or not tree.stdout.strip():
            raise ValueError(f"cannot write comparison tree: {tree.stderr.strip()}")
        return tree.stdout.strip()


def create_review_commit(root: Path, tree: str, base_head: str, review_id: str, created_at: str) -> str:
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "DeepDone Review",
            "GIT_AUTHOR_EMAIL": "deepdone@local.invalid",
            "GIT_COMMITTER_NAME": "DeepDone Review",
            "GIT_COMMITTER_EMAIL": "deepdone@local.invalid",
            "GIT_AUTHOR_DATE": created_at,
            "GIT_COMMITTER_DATE": created_at,
        }
    )
    commit = run(
        ["git", "commit-tree", tree, "-p", base_head],
        root,
        env=env,
        input_data=f"DeepDone review snapshot {review_id}\n",
    )
    if commit.returncode != 0 or not commit.stdout.strip():
        raise ValueError(f"cannot create review commit: {commit.stderr.strip()}")
    return commit.stdout.strip()


def review_ref(root: Path, review_id: str) -> str:
    ref = f"{REVIEW_REF_PREFIX}{review_id}"
    check = run(["git", "check-ref-format", ref], root)
    if check.returncode != 0:
        raise ValueError("review ID does not produce a valid private review ref")
    return ref


def ref_oid(root: Path, ref: str) -> str | None:
    proc = run(["git", "rev-parse", "--verify", "--quiet", ref], root)
    return proc.stdout.strip() if proc.returncode == 0 and proc.stdout.strip() else None


def update_ref(root: Path, ref: str, new_oid: str, old_oid: str | None) -> None:
    expected = old_oid or ("0" * len(new_oid))
    proc = run(["git", "update-ref", ref, new_oid, expected], root)
    if proc.returncode != 0:
        raise ValueError(f"cannot update private review ref: {proc.stderr.strip()}")


def delete_ref(root: Path, ref: str, expected_oid: str) -> None:
    proc = run(["git", "update-ref", "-d", ref, expected_oid], root)
    if proc.returncode != 0:
        raise ValueError(f"cannot delete private review ref: {proc.stderr.strip()}")


def changed_paths(root: Path, base_head: str, review_commit: str) -> set[str]:
    proc = run(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "-z", "--no-renames", base_head, review_commit],
        root,
        binary=True,
    )
    if proc.returncode != 0:
        raise ValueError(proc.stderr.decode(errors="replace").strip())
    return {os.fsdecode(path) for path in proc.stdout.split(b"\0") if path}


def filesystem_evidence(root: Path, role: str, path: str) -> dict[str, object]:
    absolute = root / path
    if absolute.is_symlink():
        return {
            "role": role,
            "path": path,
            "kind": "symlink",
            "mode": "120000",
            "sha256": hashlib.sha256(b"symlink\0" + os.fsencode(os.readlink(absolute))).hexdigest(),
        }
    if not absolute.is_file():
        raise ValueError(f"{role} evidence does not exist as a file: {path}")
    mode = "100755" if absolute.stat().st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH) else "100644"
    hasher = hashlib.sha256()
    with absolute.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return {"role": role, "path": path, "kind": "file", "mode": mode, "sha256": hasher.hexdigest()}


def validate_entry(
    root: Path,
    ledger_rel: str,
    entry: dict[str, object],
) -> tuple[str, str, str, list[str], list[str], dict[str, str]]:
    record = work_unit.load(root, ledger_rel)
    work_unit.bind_review(record, entry)
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

    raw_scope = entry.get("scope")
    if not isinstance(raw_scope, dict):
        raise ValueError("latest Review has no scope")
    raw_include = raw_scope.get("include")
    raw_exclude = raw_scope.get("exclude", [])
    if not isinstance(raw_include, list) or not raw_include:
        raise ValueError("latest Review scope has no include roots")
    if not isinstance(raw_exclude, list):
        raise ValueError("latest Review scope exclude roots are malformed")
    include = [normalize_scope_root(root, str(value)) for value in raw_include]
    exclude = [normalize_scope_root(root, str(value)) for value in raw_exclude]
    if len(include) != len(set(include)) or len(exclude) != len(set(exclude)):
        raise ValueError("latest Review scope contains duplicate roots")

    raw_evidence = entry.get("evidence")
    if not isinstance(raw_evidence, dict):
        raise ValueError("latest Review evidence is malformed")
    unknown_roles = set(raw_evidence).difference(ALLOWED_EVIDENCE_ROLES)
    if unknown_roles:
        raise ValueError(f"latest Review has unsupported evidence roles: {sorted(unknown_roles)}")
    evidence = {role: normalize_repo_path(root, str(path)) for role, path in raw_evidence.items()}
    if evidence.get("ledger") != ledger_rel:
        raise ValueError("latest Review ledger evidence must match selected epic ledger")
    roadmap_path = root / "notes" / "roadmap.md"
    if record["roadmap"] and roadmap_path.is_file() and evidence.get("roadmap") != "notes/roadmap.md":
        raise ValueError("latest Review must include active roadmap evidence")
    return review_id, base_head, manifest_rel, include, exclude, evidence


def validate_manifest_binding(root: Path, ledger_rel: str, entry: dict, manifest: dict) -> None:
    scopes = []
    for value in (entry.get('scope'), manifest.get('scope')):
        if not isinstance(value, dict) or set(value) != {'include', 'exclude'}:
            raise ValueError('reviewed change-set scope is malformed')
        normalized = {}
        for key in ('include', 'exclude'):
            roots = value[key]
            if not isinstance(roots, list) or (key == 'include' and not roots) or not all(isinstance(p, str) and p for p in roots):
                raise ValueError('reviewed change-set scope is malformed')
            paths = [normalize_scope_root(root, path) for path in roots]
            if len(paths) != len(set(paths)):
                raise ValueError('reviewed change-set scope contains duplicate roots')
            normalized[key] = sorted(paths)
        scopes.append(normalized)
    if scopes[0] != scopes[1]:
        raise ValueError('reviewed change-set scope does not match latest Review entry')
    expected = entry.get('evidence')
    raw = manifest.get('evidence')
    if not isinstance(expected, dict) or not isinstance(raw, list) or not all(isinstance(path, str) and path for path in expected.values()):
        raise ValueError('reviewed change-set evidence is malformed')
    if set(expected) - ALLOWED_EVIDENCE_ROLES:
        raise ValueError('latest Review has unsupported evidence roles')
    expected = {role: normalize_repo_path(root, path) for role, path in expected.items()}
    if expected.get('ledger') != ledger_rel:
        raise ValueError('latest Review ledger evidence must match selected work unit')
    actual = {}
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get('role'), str) or item['role'] not in ALLOWED_EVIDENCE_ROLES:
            raise ValueError('reviewed change set has unsupported or malformed evidence role')
        role = item['role']
        if role in actual:
            raise ValueError(f'reviewed change set repeats evidence role: {role}')
        path = item.get('path')
        if not isinstance(path, str) or not path:
            raise ValueError('reviewed change-set evidence path is malformed')
        actual[role] = normalize_repo_path(root, path)
    if expected != actual:
        raise ValueError('reviewed change-set evidence does not match latest Review entry')


def prior_manifest_owns_ref(path: Path, ledger_rel: str, ref: str, ref_commit: str) -> bool:
    try:
        prior = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        prior.get("schema_version") == MANIFEST_SCHEMA_VERSION
        and prior.get("ledger_path") == ledger_rel
        and prior.get("review_ref") == ref
        and prior.get("review_commit") == ref_commit
    )


def write_manifest_atomic(path: Path, manifest: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def capture(root: Path, ledger_value: str) -> Path:
    import verification

    root = root.resolve()
    if (root / ".deepdone/STOP").exists():
        raise ValueError(".deepdone/STOP exists")
    ledger_rel = normalize_repo_path(root, ledger_value)
    ledger_path = root / ledger_rel
    try:
        ledger_text = ledger_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValueError(f"ledger does not exist: {ledger_rel}") from exc

    entry = latest_review_entry(ledger_text)
    review_id, base_head, manifest_rel, include, exclude, evidence_roles = validate_entry(root, ledger_rel, entry)
    evidence_paths = set(evidence_roles.values())
    records = parse_status(root)
    selected = select_reviewed_records(records, include, exclude, evidence_paths, ledger_rel)
    selected_paths = {record.path for record in selected}
    selected_paths.update(record.old_path for record in selected if record.old_path)

    errors = verification.validate(root, ledger_rel, text=ledger_text, owned=selected_paths)
    if errors:
        raise ValueError("; ".join(errors))

    tree = build_tree_from_worktree(root, base_head, selected_paths)
    errors = verification.validate(root, ledger_rel, text=ledger_text, owned=selected_paths, tree=tree)
    if errors:
        raise ValueError("; ".join(errors))
    created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    review_commit = create_review_commit(root, tree, base_head, review_id, created_at)
    ref = review_ref(root, review_id)
    manifest_path = root / manifest_rel
    existing_oid = ref_oid(root, ref)
    if existing_oid and not prior_manifest_owns_ref(manifest_path, ledger_rel, ref, existing_oid):
        raise ValueError(f"private review ref already exists without matching manifest: {ref}")

    update_ref(root, ref, review_commit, existing_oid)
    try:
        reviewed_paths = changed_paths(root, base_head, review_commit)
        if not reviewed_paths:
            raise ValueError("review snapshot contains no changes")
        evidence = [
            filesystem_evidence(root, role, path)
            for role, path in sorted(evidence_roles.items())
        ]
        manifest: dict[str, object] = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "review_id": review_id,
            "ledger_path": ledger_rel,
            "base_head": base_head,
            "review_ref": ref,
            "review_commit": review_commit,
            "review_tree": tree,
            "commit_path_count": len(reviewed_paths),
            "scope": {"include": include, "exclude": exclude},
            "evidence": evidence,
            "created_at": created_at,
        }
        write_manifest_atomic(manifest_path, manifest)
    except Exception:
        if existing_oid:
            update_ref(root, ref, existing_oid, review_commit)
        else:
            delete_ref(root, ref, review_commit)
        raise

    for candidate in manifest_path.parent.glob("*.json"):
        if candidate == manifest_path:
            continue
        try:
            prior = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if prior.get("ledger_path") != ledger_rel:
            continue
        prior_ref = prior.get("review_ref")
        prior_commit = prior.get("review_commit")
        if (
            isinstance(prior_ref, str)
            and prior_ref.startswith(REVIEW_REF_PREFIX)
            and isinstance(prior_commit, str)
            and ref_oid(root, prior_ref) == prior_commit
        ):
            delete_ref(root, prior_ref, prior_commit)
        candidate.unlink(missing_ok=True)
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    work_unit.add_selectors(parser, required=True)
    args = parser.parse_args()
    try:
        root = git_root(Path.cwd())
        if (root / ".deepdone" / "STOP").exists():
            raise ValueError(".deepdone/STOP exists")
        manifest_path = capture(root, work_unit.explicit(root, args)["path"])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"Refusing review capture: {exc}", file=sys.stderr)
        return 2
    print(manifest_path.relative_to(root))
    print(
        f"Captured {manifest['commit_path_count']} Git paths as {manifest['review_ref']} "
        f"with {len(manifest['evidence'])} evidence files"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
