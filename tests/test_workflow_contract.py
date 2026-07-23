from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = (
    ROOT / "skills/deepdone/references/state-machine.md",
    ROOT / "skills/deepdone/references/safety-and-modes.md",
)
REQUIRED = {
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
SUBJECT_PATHS = {
    "deepdone": ROOT / "skills/deepdone/SKILL.md",
    **{
        f"phase-{name}": ROOT / f"skills/deepdone/references/phase-{name}.md"
        for name in ("advance", "archive", "commit", "decide", "fixup", "implement", "plan", "pr", "review", "sync", "verify")
    },
}


def section(text: str, name: str) -> str:
    match = re.search(rf"^##\s+{re.escape(name)}\s*$", text, flags=re.MULTILINE)
    if not match:
        return ""
    start = match.end()
    next_match = re.search(r"^##\s+", text[start:], flags=re.MULTILINE)
    end = start + next_match.start() if next_match else len(text)
    return text[start:end]


def contract_invariants() -> dict[str, set[str]]:
    invariants: dict[str, set[str]] = {}
    for path in CONTRACTS:
        text = path.read_text(encoding="utf-8")
        matches = list(re.finditer(r"^###\s+(DD-[A-Z]+-[0-9]{3}):\s+.+$", section(text, "Active Invariants"), flags=re.MULTILINE))
        active = section(text, "Active Invariants")
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(active)
            block = active[match.end() : end]
            applies = re.search(r"^-\s+Applies to:\s+(.+)$", block, flags=re.MULTILINE)
            invariants[match.group(1)] = set(re.findall(r"`(deepdone|phase-[a-z0-9-]+)`", applies.group(1))) if applies else set()
    return invariants


class WorkflowContractTests(unittest.TestCase):
    def test_required_invariant_registry_is_complete(self) -> None:
        self.assertEqual(set(contract_invariants()), REQUIRED)

    def test_every_invariant_declares_rule_and_evidence(self) -> None:
        for path in CONTRACTS:
            active = section(path.read_text(encoding="utf-8"), "Active Invariants")
            blocks = re.split(r"^###\s+DD-[A-Z]+-[0-9]{3}:\s+.+$", active, flags=re.MULTILINE)[1:]
            for block in blocks:
                self.assertRegex(block, r"(?m)^- Rule: \S")
                self.assertRegex(block, r"(?m)^- Applies to: \S")
                self.assertRegex(block, r"(?m)^- Evidence: \S")

    def test_subject_conformance_matches_contract_ownership(self) -> None:
        invariants = contract_invariants()
        for invariant_id, subjects in invariants.items():
            self.assertTrue(subjects, invariant_id)
            for subject in subjects:
                subject_text = SUBJECT_PATHS[subject].read_text(encoding="utf-8")
                refs = set(re.findall(r"`(DD-[A-Z]+-[0-9]{3})`", section(subject_text, "Conforms To")))
                self.assertIn(invariant_id, refs, subject)

    def test_no_skill_references_unknown_or_retired_invariant(self) -> None:
        active = set(contract_invariants())
        retired: set[str] = set()
        for path in CONTRACTS:
            retired.update(re.findall(r"^###\s+(DD-[A-Z]+-[0-9]{3}):", section(path.read_text(encoding="utf-8"), "Retired Invariants"), flags=re.MULTILINE))
        for subject, path in SUBJECT_PATHS.items():
            refs = set(re.findall(r"`(DD-[A-Z]+-[0-9]{3})`", section(path.read_text(encoding="utf-8"), "Conforms To")))
            self.assertFalse(refs.difference(active), subject)
            self.assertFalse(refs.intersection(retired), subject)


if __name__ == "__main__":
    unittest.main()
