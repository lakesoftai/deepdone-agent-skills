#!/usr/bin/env python3
"""Prepare or create a safe DeepDone git commit.

Default mode prints a commit candidate and does not commit.
Actual commit requires --commit --yes.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

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
]

VERIFICATION_RESULT_RE = re.compile(r"(^|\s|[-*`])result:\s*(pass|fail|blocked)\b", re.IGNORECASE)
REVIEW_RESULT_RE = re.compile(r"(^|\s|[-*`])review-result:\s*(pass|fail|blocked)\b", re.IGNORECASE)
REVIEW_BLOCKER_RE = re.compile(
    r"\b(blocked|blocking|unresolved|deferred|needs user|needs_user|failed|fail)\b",
    re.IGNORECASE,
)
REVIEW_CLEAR_RE = re.compile(r"\b(no blocking|no findings|clean|pass|passed)\b", re.IGNORECASE)


@dataclass
class GitFile:
    status: str
    path: str


def run(cmd: list[str], cwd: Path, check: bool = False) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if check and proc.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{proc.stderr.rstrip()}")
    return proc.returncode, proc.stdout.rstrip("\n"), proc.stderr.rstrip("\n")


def git_root(start: Path) -> Path:
    code, out, err = run(["git", "rev-parse", "--show-toplevel"], start)
    if code != 0 or not out:
        raise RuntimeError(f"Not a git repository: {err}")
    return Path(out)


def parse_status(lines: list[str]) -> list[GitFile]:
    files: list[GitFile] = []
    for line in lines:
        if not line:
            continue
        status = line[:2]
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        files.append(GitFile(status=status.strip(), path=path))
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
    m = re.search(rf"^##\s+{re.escape(name)}\s*$", text, flags=re.MULTILINE)
    if not m:
        return ""
    start = m.end()
    next_m = re.search(r"^##\s+", text[start:], flags=re.MULTILINE)
    end = start + next_m.start() if next_m else len(text)
    return text[start:end].strip()


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


def parse_active_ledger(root: Path) -> tuple[str | None, str | None, str | None, str]:
    roadmap_path = root / "notes" / "roadmap.md"
    roadmap = read_text(roadmap_path)
    if roadmap:
        active = section(roadmap, "Active Epic")
        name = None
        ledger = None
        state = None
        m_name = re.search(r"^-\s*name:\s*(.+?)\s*$", active, flags=re.MULTILINE)
        m_ledger = re.search(r"^-\s*ledger:\s*(.+?)\s*$", active, flags=re.MULTILINE)
        m_state = re.search(r"^-\s*state:\s*(.+?)\s*$", active, flags=re.MULTILINE)
        if m_name:
            name = m_name.group(1).strip()
        if m_ledger:
            ledger = m_ledger.group(1).strip()
        if m_state:
            state = m_state.group(1).strip().lower()
        if ledger and ledger not in {"none", "null"}:
            try:
                ledger_path = ensure_repo_path(root, ledger)
            except ValueError:
                return name, ledger, state, ""
            return name, ledger, state, read_text(ledger_path)
    epics = root / "notes" / "epics"
    if epics.exists():
        candidates: list[Path] = []
        for path in sorted(epics.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
            text = read_text(path)
            if status_is_active(section(text, "Status")):
                candidates.append(path)
        if len(candidates) == 1:
            text = read_text(candidates[0])
            return None, str(candidates[0].relative_to(root)), None, text
    return None, None, None, ""


def latest_lines(text: str, section_name: str, limit: int = 8) -> list[str]:
    lines = [line.strip() for line in section(text, section_name).splitlines() if line.strip()]
    return lines[-limit:]


def current_milestone(ledger_text: str) -> str | None:
    milestones = section(ledger_text, "Milestones")
    for line in milestones.splitlines():
        s = line.strip()
        if s.startswith("- [ ]") or s.startswith("- [-]"):
            return re.sub(r"^- \[[ xX-]\]\s*", "", s).strip()
    done = None
    for line in milestones.splitlines():
        s = line.strip()
        if s.lower().startswith("- [x]"):
            done = re.sub(r"^- \[[xX]\]\s*", "", s).strip()
    return done


def review_lines(ledger_text: str) -> list[str]:
    review_section = latest_lines(ledger_text, "Review", limit=12)
    decision_review = [line for line in latest_lines(ledger_text, "Decisions", limit=20) if "review" in line.lower()]
    return (review_section + decision_review)[-12:]


def blocking_open_loops(open_loops: list[str]) -> list[str]:
    non_blocking = {"none", "- none", "none found", "- none found", "n/a", "- n/a"}
    return [line for line in open_loops if line.strip().lower() not in non_blocking]


def review_has_blocker(review: list[str]) -> bool:
    for line in review:
        if REVIEW_BLOCKER_RE.search(line) and not REVIEW_CLEAR_RE.search(line):
            return True
    return False


def review_results(review: list[str]) -> list[str]:
    results: list[str] = []
    for line in review:
        match = REVIEW_RESULT_RE.search(line)
        if match:
            results.append(match.group(2).lower())
    return results


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
        if results and any(result in {"fail", "blocked"} for result in results):
            errors.append("review evidence indicates blocking or unresolved findings")
        elif not results and review_has_blocker(review):
            errors.append("review evidence indicates blocking or unresolved findings")
    blocked_loops = blocking_open_loops(open_loops)
    if blocked_loops:
        errors.append("open loops remain unresolved")
    return errors


def guess_area(files: list[GitFile]) -> str:
    paths = [f.path for f in files]
    if any(p.startswith("notes/") for p in paths) and len(paths) <= 3:
        return "docs"
    if any(p.startswith("tests/") or "/tests/" in p for p in paths):
        return "test"
    if any(p.endswith(".py") for p in paths):
        return "python"
    if any(p.endswith((".ts", ".tsx", ".js", ".jsx")) for p in paths):
        return "app"
    return "deepdone"


def make_subject(area: str, milestone: str | None, files: list[GitFile]) -> str:
    if milestone:
        raw = milestone.lower()
        raw = re.sub(r"[^a-z0-9 ]+", " ", raw)
        raw = re.sub(r"\s+", " ", raw).strip()
        words = raw.split()[:8]
        summary = " ".join(words) or "update workflow"
    else:
        summary = f"update {len(files)} files"
    subject = f"{area}: {summary}"
    if len(subject) > 72:
        subject = subject[:69].rstrip() + "..."
    return subject


def build_message(epic: str | None, milestone: str | None, verification: list[str], review: list[str], files: list[GitFile]) -> str:
    area = guess_area(files)
    subject = make_subject(area, milestone, files)
    verification_text = verification or ["not found in active ledger"]
    review_text = review or ["not found in active ledger"]
    lines = [
        subject,
        "",
        "DeepDone:",
        f"- Epic: {epic or 'none'}",
        f"- Milestone: {milestone or 'none'}",
        "- Verification:",
    ]
    lines.extend(f"  - {line}" for line in verification_text)
    lines.append("- Review:")
    lines.extend(f"  - {line}" for line in review_text)
    return "\n".join(lines).rstrip() + "\n"


def render_candidate(candidate: dict, files: list[GitFile], excluded_local: list[GitFile], message: str) -> str:
    verification = candidate["verification"]
    review = candidate["review"]
    open_loops = candidate["open_loops"]
    gate_errors = candidate["commit_gate_errors"]
    return (
        "# DeepDone Commit Candidate\n\n"
        "## Message\n\n"
        "```text\n" + message + "```\n\n"
        "## Files\n\n"
        + ("\n".join(f"- `{f.status}` `{f.path}`" for f in files) if files else "- none")
        + "\n\n## Excluded Local Files\n\n"
        + ("\n".join(f"- `{f.status}` `{f.path}`" for f in excluded_local) if excluded_local else "- none")
        + "\n\n## Verification\n\n"
        + ("\n".join(f"- {line}" for line in verification) if verification else "- not found")
        + "\n\n## Review\n\n"
        + ("\n".join(f"- {line}" for line in review) if review else "- not found")
        + "\n\n## Open Loops\n\n"
        + ("\n".join(f"- {line}" for line in open_loops) if open_loops else "- none found")
        + "\n\n## Commit Gate\n\n"
        + ("\n".join(f"- blocked: {line}" for line in gate_errors) if gate_errors else "- pass")
        + "\n\n## JSON\n\n```json\n"
        + json.dumps(candidate, indent=2)
        + "\n```\n"
    )


def ensure_repo_path(root: Path, rel: str) -> Path:
    path = (root / rel).resolve()
    path.relative_to(root.resolve())
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare or create a DeepDone commit")
    parser.add_argument("--candidate", action="store_true", help="prepare candidate only, default")
    parser.add_argument("--commit", action="store_true", help="create commit")
    parser.add_argument("--yes", action="store_true", help="confirm actual commit")
    parser.add_argument("--include-untracked", action="store_true", help="deprecated; expected untracked files are staged by exact path")
    parser.add_argument("--message-file", help="use an existing commit message file")
    parser.add_argument("--output", default="-", help="candidate output path, or '-' for stdout")
    args = parser.parse_args()

    root = git_root(Path.cwd())

    if (root / ".deepdone" / "STOP").exists():
        print("Refusing: .deepdone/STOP exists", file=sys.stderr)
        return 2

    code, status_out, status_err = run(["git", "status", "--short", "--untracked-files=all"], root)
    if code != 0:
        print(status_err, file=sys.stderr)
        return 2
    all_files = parse_status(status_out.splitlines())
    excluded_local = [f for f in all_files if is_local_only(f.path)]
    files = [f for f in all_files if not is_local_only(f.path)]
    if not files:
        print("No changes to commit.")
        if excluded_local:
            print("Ignored local-only files:")
            for f in excluded_local:
                print(f"- {f.path}")
        return 0

    dangerous = [f.path for f in files if is_dangerous(f.path)]
    if dangerous:
        print("Refusing dangerous paths:", file=sys.stderr)
        for p in dangerous:
            print(f"- {p}", file=sys.stderr)
        return 2

    epic, ledger_path, active_epic_state, ledger_text = parse_active_ledger(root)
    milestone = current_milestone(ledger_text) if ledger_text else None
    verification = latest_lines(ledger_text, "Verification Log") if ledger_text else []
    review = review_lines(ledger_text) if ledger_text else []
    open_loops = latest_lines(ledger_text, "Open Loops") if ledger_text else []
    gate_errors = commit_gate_errors(ledger_path, active_epic_state, ledger_text, verification, review, open_loops)

    message = read_text(ensure_repo_path(root, args.message_file)) if args.message_file else build_message(epic, milestone, verification, review, files)

    _, diff_stat, _ = run(["git", "diff", "--stat"], root)
    _, staged_stat, _ = run(["git", "diff", "--cached", "--stat"], root)

    candidate = {
        "epic": epic,
        "ledger_path": ledger_path,
        "active_epic_state": active_epic_state,
        "milestone": milestone,
        "files": [{"status": f.status, "path": f.path} for f in files],
        "excluded_local_files": [{"status": f.status, "path": f.path} for f in excluded_local],
        "verification": verification,
        "review": review,
        "open_loops": open_loops,
        "commit_gate_errors": gate_errors,
        "diff_stat": diff_stat.splitlines() if diff_stat else [],
        "staged_stat": staged_stat.splitlines() if staged_stat else [],
        "message": message,
    }

    if not args.commit:
        rendered = render_candidate(candidate, files, excluded_local, message)
        if args.output == "-":
            print(rendered, end="")
        else:
            output_path = ensure_repo_path(root, args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered, encoding="utf-8")
            print(f"Wrote candidate: {output_path.relative_to(root)}")
        return 0
    if not args.yes:
        print("Refusing actual commit without --yes", file=sys.stderr)
        return 2
    if gate_errors:
        print("Refusing actual commit because commit gates failed:", file=sys.stderr)
        for error in gate_errors:
            print(f"- {error}", file=sys.stderr)
        return 2

    for f in files:
        ensure_repo_path(root, f.path)
        run(["git", "add", "--", f.path], root, check=True)

    message_file: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write(message)
            message_file = Path(handle.name)
        run(["git", "commit", "-F", str(message_file)], root, check=True)
    finally:
        if message_file is not None:
            message_file.unlink(missing_ok=True)
    _, commit_hash, _ = run(["git", "rev-parse", "--short", "HEAD"], root)
    print(f"Committed: {commit_hash}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        logging.basicConfig(level=logging.ERROR, format="%(levelname)s: %(message)s")
        logging.exception("Unhandled error while preparing DeepDone commit")
        raise SystemExit(2)
