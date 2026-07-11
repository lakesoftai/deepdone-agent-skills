from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.state_machine = (ROOT / "skills/deepdone-orchestrate/references/state-machine.md").read_text(encoding="utf-8")
        cls.safety = (ROOT / "skills/deepdone-orchestrate/references/safety-and-modes.md").read_text(encoding="utf-8")
        cls.review = (ROOT / "skills/deepdone-review/SKILL.md").read_text(encoding="utf-8")
        cls.implement = (ROOT / "skills/deepdone-implement/SKILL.md").read_text(encoding="utf-8")

    def test_review_pass_owns_completion(self) -> None:
        self.assertIn("Review passes | Mark epic complete", self.state_machine)
        self.assertIn("Only `$deepdone-review` may mark an epic", self.implement)
        self.assertIn("set roadmap `Active Epic.state` to `complete-pending-advance`", self.review)

    def test_review_fix_returns_to_verification(self) -> None:
        self.assertIn("Review fix changes code | Keep epic active; next state is verification", self.state_machine)

    def test_commit_modes_stop_without_advance(self) -> None:
        self.assertIn("`until-commit` and `end-to-end` stop after commit", self.safety)
        self.assertIn("They never advance the roadmap in the same run", self.safety)

    def test_state_labels_do_not_authorize_actions(self) -> None:
        self.assertIn("A state label such as `ready_to_commit` is evidence, not authority", self.safety)
        self.assertIn("A merge commit, release tag, or PR URL is evidence, not archive authority", self.safety)

    def test_only_commit_modes_authorize_commit(self) -> None:
        self.assertIn("`until-commit` and `end-to-end` authorize commit only", self.safety)


if __name__ == "__main__":
    unittest.main()
