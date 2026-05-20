#!/usr/bin/env python3
"""Inspect DeepDone repository state and print JSON.

This script intentionally does not decide the final next step. It gathers stable
signals for the smart agent UI supervisor skill.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


def run(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    return proc.returncode, proc.stdout.rstrip("\n"), proc.stderr.rstrip("\n")


def git_root(start: Path) -> Path:
    code, out, _ = run(["git", "rev-parse", "--show-toplevel"], start)
    if code == 0 and out:
        return Path(out)
    return start.resolve()


def section(text: str, name: str) -> str:
    pattern = rf"^##\s+{re.escape(name)}\s*$"
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        return ""
    start = match.end()
    next_match = re.search(r"^##\s+", text[start:], flags=re.MULTILINE)
    end = start + next_match.start() if next_match else len(text)
    return text[start:end].strip()


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def parse_active_epic(roadmap: str) -> dict[str, str | None]:
    active = section(roadmap, "Active Epic")
    result: dict[str, str | None] = {"name": None, "ledger": None, "state": None}
    for key in result:
        m = re.search(rf"^-\s*{key}:\s*(.+?)\s*$", active, flags=re.MULTILINE)
        if m:
            value = m.group(1).strip()
            result[key] = None if value in {"none", "null", ""} else value
    return result


def status_is_active(status: str) -> bool:
    active_values = {"active", "in progress", "in-progress", "current"}
    for raw_line in status.splitlines() or [status]:
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


def find_obvious_active_ledger(root: Path) -> Path | None:
    epics = root / "notes" / "epics"
    if not epics.exists():
        return None
    candidates: list[Path] = []
    for path in sorted(epics.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        text = read_text(path)
        status = section(text, "Status")
        if status_is_active(status):
            candidates.append(path)
    if len(candidates) == 1:
        return candidates[0]
    return None


def latest_verification_lines(ledger_text: str, limit: int = 8) -> list[str]:
    lines = [line.strip() for line in section(ledger_text, "Verification Log").splitlines() if line.strip()]
    return lines[-limit:]


def open_loop_lines(ledger_text: str, limit: int = 12) -> list[str]:
    lines = [line.strip() for line in section(ledger_text, "Open Loops").splitlines() if line.strip()]
    return lines[-limit:]


def unfinished_milestones(ledger_text: str) -> list[str]:
    milestones = section(ledger_text, "Milestones")
    out = []
    for line in milestones.splitlines():
        if re.match(r"^- \[ \]", line.strip()):
            out.append(line.strip())
    return out


def completed_milestones(ledger_text: str) -> list[str]:
    milestones = section(ledger_text, "Milestones")
    out = []
    for line in milestones.splitlines():
        if re.match(r"^- \[x\]", line.strip(), flags=re.IGNORECASE):
            out.append(line.strip())
    return out


def safe_rel(root: Path, maybe_path: str | None) -> Path | None:
    if not maybe_path:
        return None
    p = Path(maybe_path)
    if not p.is_absolute():
        p = root / p
    try:
        p.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    return p


def main() -> int:
    start = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
    root = git_root(start)

    code, branch, _ = run(["git", "branch", "--show-current"], root)
    if code != 0:
        branch = ""
    _, status_short, _ = run(["git", "status", "--short"], root)
    _, diff_stat, _ = run(["git", "diff", "--stat"], root)

    roadmap_path = root / "notes" / "roadmap.md"
    roadmap_text = read_text(roadmap_path)
    roadmap_exists = bool(roadmap_text)
    active = parse_active_epic(roadmap_text) if roadmap_exists else {"name": None, "ledger": None, "state": None}

    ledger_path = safe_rel(root, active.get("ledger"))
    if ledger_path is None or not ledger_path.exists():
        ledger_path = find_obvious_active_ledger(root)

    ledger_text = read_text(ledger_path) if ledger_path else ""

    warnings: list[str] = []
    if (root / ".deepdone" / "STOP").exists():
        warnings.append("stop_file_present")
    if roadmap_exists and active.get("ledger") and ledger_path is None:
        warnings.append("roadmap_ledger_path_invalid")
    if status_short and not ledger_text:
        warnings.append("dirty_git_without_active_ledger")
    if ledger_text and not section(ledger_text, "Next Action"):
        warnings.append("ledger_missing_next_action")
    if ledger_text and not section(ledger_text, "Verification Log"):
        warnings.append("ledger_has_no_verification_log_entries")

    data: dict[str, Any] = {
        "repo_root": str(root),
        "branch": branch,
        "stop_file_present": (root / ".deepdone" / "STOP").exists(),
        "git_status_short": status_short.splitlines() if status_short else [],
        "git_diff_stat": diff_stat.splitlines() if diff_stat else [],
        "roadmap_path": str(roadmap_path.relative_to(root)) if roadmap_exists else None,
        "roadmap_exists": roadmap_exists,
        "roadmap_active_epic": active,
        "ledger_path": str(ledger_path.relative_to(root)) if ledger_path else None,
        "ledger_exists": bool(ledger_text),
        "ledger_status": section(ledger_text, "Status") if ledger_text else "",
        "ledger_next_action": section(ledger_text, "Next Action") if ledger_text else "",
        "open_loops": open_loop_lines(ledger_text),
        "latest_verification": latest_verification_lines(ledger_text),
        "unfinished_milestones": unfinished_milestones(ledger_text),
        "completed_milestones": completed_milestones(ledger_text),
        "warnings": warnings,
    }

    print(json.dumps(data, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
