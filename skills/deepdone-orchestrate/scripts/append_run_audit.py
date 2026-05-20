#!/usr/bin/env python3
"""Append one DeepDone supervisor audit event as JSONL."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


RUN_ID_RE = re.compile(r"^\d{8}-\d{6}$")


def parse_files(raw: str) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"files_touched must be JSON list: {exc.msg}") from exc
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("files_touched must be JSON list of strings")
    return value


def run_id_now() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def audit_path(root: Path, run_id: str) -> Path:
    if not RUN_ID_RE.match(run_id):
        raise ValueError("run id must match YYYYMMDD-HHMMSS")
    return root / ".deepdone" / "runs" / f"{run_id}.jsonl"


def append_event(root: Path, run_id: str, event: dict[str, Any]) -> Path:
    path = audit_path(root, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Append a DeepDone supervisor audit event")
    parser.add_argument("--root", default=".", help="repository root or working directory")
    parser.add_argument("--run-id", default="", help="YYYYMMDD-HHMMSS, default is current local time")
    parser.add_argument("--state-before", required=True)
    parser.add_argument("--skill-invoked", required=True)
    parser.add_argument("--state-after", required=True)
    parser.add_argument("--files-touched", default="[]", help="JSON list of changed paths")
    parser.add_argument("--stop-reason", default="", help="empty means null")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    run_id = args.run_id or run_id_now()
    try:
        files_touched = parse_files(args.files_touched)
        event = {
            "state_before": args.state_before,
            "skill_invoked": args.skill_invoked,
            "state_after": args.state_after,
            "files_touched": files_touched,
            "stop_reason": args.stop_reason or None,
        }
        path = append_event(root, run_id, event)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(path.relative_to(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
