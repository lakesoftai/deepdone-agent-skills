from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAPTURE_SCRIPT = ROOT / "skills/deepdone/scripts/capture_reviewed_change_set.py"
ADVANCE_SCRIPT = ROOT / "skills/deepdone/scripts/check_reviewed_change_set.py"
COMMIT_SCRIPT = ROOT / "skills/deepdone/scripts/commit_progress.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=check)


class ReviewedChangeSetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.capture = load_module("capture_reviewed_change_set_test", CAPTURE_SCRIPT)
        self.advance = load_module("check_reviewed_change_set_test", ADVANCE_SCRIPT)

    def init_repo(self, root: Path) -> str:
        git(root, "init", "-q")
        git(root, "config", "user.name", "DeepDone Test")
        git(root, "config", "user.email", "deepdone@example.test")
        (root / ".gitignore").write_text(
            ".deepdone/\nnotes/epics/\nnotes/roadmap.md\n",
            encoding="utf-8",
        )
        app = root / "src" / "app.py"
        app.parent.mkdir(parents=True)
        app.write_text("VALUE = 1\n", encoding="utf-8")
        ledger = root / "notes" / "epics" / "demo.md"
        ledger.parent.mkdir(parents=True)
        ledger.write_text("# Demo\n\n## Status\n\nactive\n", encoding="utf-8")
        git(root, "add", ".gitignore", "src/app.py")
        git(root, "commit", "-qm", "initial")
        return git(root, "rev-parse", "HEAD").stdout.strip()

    def write_passing_ledger(
        self,
        root: Path,
        head: str,
        include: list[str],
        review_id: str = "20260711T120000Z-a1b2c3d4",
        evidence: dict[str, str] | None = None,
    ) -> Path:
        ledger = root / "notes" / "epics" / "demo.md"
        include_lines = "\n".join(f"      - {path}" for path in include)
        evidence_values = evidence or {"ledger": "notes/epics/demo.md"}
        evidence_lines = "\n".join(f"    {role}: {path}" for role, path in evidence_values.items())
        ledger.write_text(
            "# Demo\n\n"
            "## Milestones\n\n- [x] ship demo\n\n"
            "## Verification Log\n\n"
            "- command: `python3 -m unittest`\n"
            "  result: pass\n"
            "  notes: ok\n\n"
            "## Review\n\n"
            "- reviewed-at: 2026-07-11T12:00:00Z\n"
            "  result: pass\n"
            f"  review-id: {review_id}\n"
            f"  base-head: {head}\n"
            f"  manifest: .deepdone/reviews/{review_id}.json\n"
            "  scope:\n"
            "    include:\n"
            f"{include_lines}\n"
            "    exclude:\n"
            "  evidence:\n"
            f"{evidence_lines}\n"
            "  notes: no blocking findings\n\n"
            "## Open Loops\n\nnone\n\n"
            "## Next Action\n\nPrepare commit.\n\n"
            "## Status\n\ncomplete\n",
            encoding="utf-8",
        )
        return ledger

    def capture_ready(self, root: Path) -> Path:
        import verification
        ledger = "notes/epics/demo.md"
        check = {
            "id": "app-syntax", "acceptance": "Application source compiles", "required": True,
            "argv": [sys.executable, "-I", "-B", "-c", "from pathlib import Path; compile(Path('src/app.py').read_bytes(), 'src/app.py', 'exec')"],
            "cwd": ".", "inputs": [{"path": "src/app.py", "role": "source"}],
            "exclusions": [], "env": {}, "context": "local-files", "timeout": 10,
        }
        verification.initialize(root, ledger, [check], "Migrate deterministic fixture to captured execution")
        receipt = verification.run_check(root, ledger, check["id"])
        self.assertEqual(receipt["exit_code"], 0, receipt)
        return self.capture.capture(root, ledger)

    def prepare_review(self, root: Path, include: list[str] | None = None) -> Path:
        head = self.init_repo(root)
        (root / "src" / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        self.write_passing_ledger(root, head, include or ["src/"])
        return self.capture_ready(root)

    def test_capture_requires_explicit_verification_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            head = self.init_repo(root)
            (root / "src/app.py").write_text("VALUE = 2\n")
            self.write_passing_ledger(root, head, ["src/"])
            with self.assertRaisesRegex(ValueError, "verification contract"):
                self.capture.capture(root, "notes/epics/demo.md")

    def run_commit(self, root: Path, manifest: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(COMMIT_SCRIPT),
                "--commit",
                "--yes",
                "--authorized-by",
                "exact-user-request",
                "--ledger",
                "notes/epics/demo.md",
                "--reviewed-change-set",
                manifest.relative_to(root.resolve()).as_posix(),
                *extra,
            ],
            cwd=root,
            text=True,
            capture_output=True,
        )

    def run_candidate(self, root: Path, manifest: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(COMMIT_SCRIPT),
                "--candidate",
                "--ledger",
                "notes/epics/demo.md",
                "--reviewed-change-set",
                manifest.relative_to(root.resolve()).as_posix(),
            ],
            cwd=root,
            text=True,
            capture_output=True,
        )

    def test_candidate_verification_requires_flat_unambiguous_records(self) -> None:
        failed = "- command: `pytest`\n  result: fail"
        passed = "- command: `pytest`\n  result: pass"
        malformed = [
            "- command: `pytest`\n  notes: |\n    result: pass",
            "- command: `pytest`\n  result : fail\n  result: pass",
            "- command: `pytest`\n  command : `lint`\n  result: pass",
            "- command: `pytest`\n  scope : api\n  scope: web\n  result: pass",
            "- command: `pytest`\n  result: pass\n  notes: >-",
            "- command: `pytest`\n  result: pass\n    scope: api",
            "- command: `pytest`\n  result: pass\n    - command: `lint`\n      result: pass",
            "  - command: `pytest`\n    result: pass",
        ]
        cases = [(f"{failed}\n{entry}\n{passed}", "malformed") for entry in malformed]
        cases += [
            ("  - command: `pytest`\n  result: pass", "malformed"),
            (f"{failed}\n{passed}", None),
            (f"- command: `pytest`\n  result: blocked\n{passed}", None),
            (f"{passed}\n  notes: expected result: fail in diagnostic", None),
            (f"{passed}\n{failed}", "failing"),
            (f"{failed}\n" + "\n".join(f"- command: `{cmd}`\n  result: pass" for cmd in ("lint", "format", "types")), "failing"),
            (f"{failed}\n  scope: api\n{passed}\n  scope: web", "failing"),
            (f"{failed}\n  scope: api\n{passed}", "failing"),
            (f"{failed}\n  scope: api\n  cwd: server\n{passed}\n  cwd: server\n  scope: api", None),
        ]
        for history, blocker in cases:
            with self.subTest(history=history), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                head = self.init_repo(root)
                (root / "src/app.py").write_text("VALUE = 2\n")
                ledger = self.write_passing_ledger(root, head, ["src/"])
                ledger.write_text(ledger.read_text().replace(
                    "- command: `python3 -m unittest`\n  result: pass\n  notes: ok", history,
                ))
                manifest = self.capture_ready(root)
                (root / "scratch.txt").write_text("unrelated user work\n")
                index_before = (root / ".git/index").read_bytes()
                result = self.run_candidate(root, manifest)
                self.assertEqual(result.returncode, 0, result.stderr)
                match = re.search(r"## JSON\s+```json\n(.*?)\n```", result.stdout, re.DOTALL)
                self.assertIsNotNone(match, result.stdout)
                candidate = json.loads(match.group(1))
                self.assertEqual(candidate["commit_gate_errors"], [], candidate)
                # Historical flat-record parsing remains strict; explicit migration makes it archival.
                import commit_progress
                errors = commit_progress.commit_gate_errors(
                    "notes/epics/demo.md", None, ledger.read_text(),
                    commit_progress.latest_verification_lines(ledger.read_text()),
                    commit_progress.review_lines(ledger.read_text()), [],
                )
                if blocker == "malformed":
                    self.assertIn("verification log lacks structured result markers", errors)
                elif blocker == "failing":
                    self.assertEqual(errors, ["verification log contains failing or blocked check"])
                else:
                    self.assertEqual(errors, [])
                self.assertEqual(candidate["reviewed_file_count"], 1)
                self.assertEqual(candidate["stale_reviewed_file_count"], 0)
                self.assertLessEqual(sum(line.startswith("- command:") for line in candidate["verification"]), 3)
                self.assertEqual((root / ".git/index").read_bytes(), index_before)
                self.assertEqual(git(root, "rev-parse", "HEAD").stdout.strip(), head)
                self.assertEqual((root / "scratch.txt").read_text(), "unrelated user work\n")

    def test_capture_uses_compact_git_snapshot_and_ignored_ledger_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = self.prepare_review(root)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(manifest["schema_version"], 2)
            self.assertNotIn("paths", manifest)
            self.assertEqual(manifest["commit_path_count"], 1)
            self.assertEqual(manifest["scope"]["include"], ["src"])
            self.assertEqual(manifest["evidence"][0]["role"], "ledger")
            self.assertEqual(manifest["evidence"][0]["path"], "notes/epics/demo.md")
            self.assertEqual(
                git(root, "rev-parse", manifest["review_ref"]).stdout.strip(),
                manifest["review_commit"],
            )
            self.assertEqual(
                git(root, "rev-parse", f"{manifest['review_commit']}^{{tree}}").stdout.strip(),
                manifest["review_tree"],
            )
            self.assertEqual(git(root, "check-ignore", "notes/epics/demo.md").returncode, 0)

    def test_capture_hashes_ignored_roadmap_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            head = self.init_repo(root)
            (root / "src/app.py").write_text("VALUE = 2\n", encoding="utf-8")
            roadmap = root / "notes" / "roadmap.md"
            roadmap.write_text("# Roadmap\n\n## Status\n\nactive\n", encoding="utf-8")
            self.write_passing_ledger(
                root,
                head,
                ["src/"],
                evidence={
                    "ledger": "notes/epics/demo.md",
                    "roadmap": "notes/roadmap.md",
                },
            )

            manifest = json.loads(self.capture_ready(root).read_text(encoding="utf-8"))

            self.assertEqual(
                {item["role"] for item in manifest["evidence"]},
                {"ledger", "roadmap"},
            )
            self.assertTrue(all(item["sha256"] for item in manifest["evidence"]))

    def test_capture_rejects_repository_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            head = self.init_repo(root)
            (root / "src/app.py").write_text("VALUE = 2\n", encoding="utf-8")
            self.write_passing_ledger(root, head, ["../outside"])

            with self.assertRaisesRegex(ValueError, "escapes repository"):
                self.capture_ready(root)

    def test_capture_handles_rename_deletion_symlink_binary_and_spaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.init_repo(root)
            old = root / "src" / "old.txt"
            deleted = root / "src" / "delete.txt"
            old.write_text("old\n", encoding="utf-8")
            deleted.write_text("delete\n", encoding="utf-8")
            git(root, "add", "src/old.txt", "src/delete.txt")
            git(root, "commit", "-qm", "add fixtures")
            head = git(root, "rev-parse", "HEAD").stdout.strip()
            git(root, "mv", "src/old.txt", "src/new name.txt")
            (root / "src/delete.txt").unlink()
            (root / "src/blob.bin").write_bytes(b"\x00\xffdeepdone")
            os.symlink("app.py", root / "src/link.py")
            os.chmod(root / "src/app.py", 0o755)
            self.write_passing_ledger(root, head, ["src/"])

            manifest = json.loads(self.capture_ready(root).read_text(encoding="utf-8"))
            changed = set(
                git(
                    root,
                    "diff",
                    "--name-only",
                    "--no-renames",
                    manifest["base_head"],
                    manifest["review_commit"],
                ).stdout.splitlines()
            )

            self.assertEqual(
                changed,
                {
                    "src/app.py",
                    "src/old.txt",
                    "src/new name.txt",
                    "src/delete.txt",
                    "src/blob.bin",
                    "src/link.py",
                },
            )
            self.assertEqual(manifest["commit_path_count"], len(changed))

    def test_capture_blocks_rename_crossing_scope_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.init_repo(root)
            source = root / "src" / "move.txt"
            source.write_text("move\n", encoding="utf-8")
            git(root, "add", "src/move.txt")
            git(root, "commit", "-qm", "add move source")
            head = git(root, "rev-parse", "HEAD").stdout.strip()
            destination = root / "other" / "move.txt"
            destination.parent.mkdir()
            git(root, "mv", "src/move.txt", "other/move.txt")
            self.write_passing_ledger(root, head, ["src/"])

            with self.assertRaisesRegex(ValueError, "rename crosses review include boundary"):
                self.capture_ready(root)

    def test_capture_does_not_change_head_or_real_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            head = self.init_repo(root)
            (root / "src/app.py").write_text("VALUE = 2\n", encoding="utf-8")
            (root / "scratch.txt").write_text("staged user work\n", encoding="utf-8")
            git(root, "add", "scratch.txt")
            before_index = git(root, "write-tree").stdout.strip()
            self.write_passing_ledger(root, head, ["src/"])

            self.capture_ready(root)

            self.assertEqual(git(root, "rev-parse", "HEAD").stdout.strip(), head)
            self.assertEqual(git(root, "write-tree").stdout.strip(), before_index)
            self.assertIn("A  scratch.txt", git(root, "status", "--short").stdout)

    def test_manifest_and_candidate_stay_bounded_for_five_thousand_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            head = self.init_repo(root)
            generated = root / "generated"
            generated.mkdir()
            for index in range(5000):
                (generated / f"file-{index:04d}.txt").write_text(f"{index}\n", encoding="utf-8")
            self.write_passing_ledger(root, head, ["generated/"])

            manifest_path = self.capture_ready(root)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            candidate = self.run_candidate(root, manifest_path)

            self.assertEqual(manifest["commit_path_count"], 5000)
            self.assertLess(manifest_path.stat().st_size, 5000)
            self.assertNotIn("file-4999.txt", manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(candidate.returncode, 0, candidate.stderr)
            self.assertLess(len(candidate.stdout), 25000)
            self.assertIn('"reviewed_file_count": 5000', candidate.stdout)
            self.assertNotIn("file-4999.txt", candidate.stdout)

    def test_exact_commit_preserves_unrelated_work_and_retains_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.prepare_review(root)
            manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
            unrelated = root / "scratch.txt"
            unrelated.write_text("user work\n", encoding="utf-8")
            before = git(root, "rev-parse", "HEAD").stdout.strip()

            result = self.run_commit(root, manifest)

            self.assertEqual(result.returncode, 0, result.stderr)
            committed = set(
                git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "--no-renames", f"{before}..HEAD").stdout.splitlines()
            )
            self.assertEqual(committed, {"src/app.py"})
            self.assertEqual(unrelated.read_text(encoding="utf-8"), "user work\n")
            self.assertIn("?? scratch.txt", git(root, "status", "--short", "--untracked-files=all").stdout)
            self.assertTrue(manifest.exists())
            self.assertEqual(
                git(root, "rev-parse", manifest_data["review_ref"]).stdout.strip(),
                manifest_data["review_commit"],
            )
            self.assertEqual(
                git(root, "rev-parse", "HEAD^{tree}").stdout.strip(),
                manifest_data["review_tree"],
            )

    def test_unrelated_staged_path_blocks_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.prepare_review(root)
            (root / "scratch.txt").write_text("user work\n", encoding="utf-8")
            git(root, "add", "scratch.txt")
            before = git(root, "rev-parse", "HEAD").stdout.strip()

            result = self.run_commit(root, manifest)

            self.assertEqual(result.returncode, 2)
            self.assertIn("staged paths exist outside reviewed change set", result.stderr)
            self.assertEqual(git(root, "rev-parse", "HEAD").stdout.strip(), before)
            self.assertTrue(manifest.exists())

    def test_staged_development_evidence_blocks_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.prepare_review(root)
            git(root, "add", "-f", "notes/epics/demo.md")

            result = self.run_commit(root, manifest)

            self.assertEqual(result.returncode, 2)
            self.assertIn("staged paths exist outside reviewed change set", result.stderr)

    def test_actual_commit_requires_explicit_manifest_argument(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.prepare_review(root)

            result = subprocess.run(
                [
                    sys.executable,
                    str(COMMIT_SCRIPT),
                    "--commit",
                    "--yes",
                    "--authorized-by",
                    "exact-user-request",
                    "--ledger",
                    "notes/epics/demo.md",
                ],
                cwd=root,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("actual commit requires --reviewed-change-set", result.stderr)

    def test_changed_reviewed_path_blocks_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.prepare_review(root)
            (root / "src/app.py").write_text("VALUE = 3\n", encoding="utf-8")

            result = self.run_commit(root, manifest)

            self.assertEqual(result.returncode, 2)
            self.assertIn("reviewed Git snapshot changed after review", result.stderr)

    def test_changed_development_evidence_blocks_commit_and_advance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.prepare_review(root)
            ledger = root / "notes/epics/demo.md"
            ledger.write_text(ledger.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")

            result = self.run_commit(root, manifest)

            self.assertEqual(result.returncode, 2)
            self.assertIn("development evidence changed after review", result.stderr)
            with self.assertRaisesRegex(ValueError, "development evidence changed after review"):
                self.advance.check(root, "notes/epics/demo.md")

    def test_base_head_change_blocks_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.prepare_review(root)
            git(root, "commit", "--allow-empty", "-qm", "move head")

            result = self.run_commit(root, manifest)

            self.assertEqual(result.returncode, 2)
            self.assertIn("repository HEAD changed after review", result.stderr)

    def test_manifest_schema_tampering_blocks_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.prepare_review(root)
            data = json.loads(manifest.read_text(encoding="utf-8"))
            data["schema_version"] = 99
            manifest.write_text(json.dumps(data), encoding="utf-8")

            result = self.run_commit(root, manifest)

            self.assertEqual(result.returncode, 2)
            self.assertIn("schema version is unsupported", result.stderr)

    def test_manifest_ledger_mismatch_blocks_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.prepare_review(root)
            data = json.loads(manifest.read_text(encoding="utf-8"))
            data["ledger_path"] = "notes/epics/other.md"
            manifest.write_text(json.dumps(data), encoding="utf-8")

            result = self.run_commit(root, manifest)

            self.assertEqual(result.returncode, 2)
            self.assertIn("ledger does not match", result.stderr)

    def test_missing_schema_v2_manifest_blocks_clean_advance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.prepare_review(root)
            result = self.run_commit(root, manifest)
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest.unlink()

            with self.assertRaisesRegex(ValueError, "schema-v2 review manifest is missing"):
                self.advance.check(root, "notes/epics/demo.md")

    def test_existing_ref_requires_manifest_commit_ownership(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            head = self.init_repo(root)
            review_id = "20260711T120000Z-a1b2c3d4"
            ref = f"refs/deepdone/reviews/{review_id}"
            git(root, "update-ref", ref, head)
            manifest = root / ".deepdone/reviews" / f"{review_id}.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "ledger_path": "notes/epics/demo.md",
                        "review_ref": ref,
                        "review_commit": "0" * len(head),
                    }
                ),
                encoding="utf-8",
            )

            self.assertFalse(
                self.capture.prior_manifest_owns_ref(
                    manifest,
                    "notes/epics/demo.md",
                    ref,
                    head,
                )
            )

    def test_dangerous_reviewed_path_blocks_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            head = self.init_repo(root)
            (root / "secret.pem").write_text("not-a-real-secret\n", encoding="utf-8")
            self.write_passing_ledger(root, head, ["secret.pem"])
            manifest = self.capture_ready(root)

            result = self.run_commit(root, manifest)

            self.assertEqual(result.returncode, 2)
            self.assertIn("dangerous paths", result.stderr)

    def test_rename_commit_matches_git_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.init_repo(root)
            old = root / "src/old.txt"
            old.write_text("rename me\n", encoding="utf-8")
            git(root, "add", "src/old.txt")
            git(root, "commit", "-qm", "add rename source")
            base = git(root, "rev-parse", "HEAD").stdout.strip()
            git(root, "mv", "src/old.txt", "src/new name.txt")
            self.write_passing_ledger(root, base, ["src/"])
            manifest = self.capture_ready(root)

            result = self.run_commit(root, manifest)

            self.assertEqual(result.returncode, 0, result.stderr)
            committed = set(git(root, "diff", "--name-only", "--no-renames", f"{base}..HEAD").stdout.splitlines())
            self.assertEqual(committed, {"src/old.txt", "src/new name.txt"})

    def test_untracked_file_with_pathspec_characters_commits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self.init_repo(root)
            new_file = root / "src/new [file]*.bin"
            new_file.write_bytes(b"\x00\xffreviewed")
            self.write_passing_ledger(root, base, ["src/"])
            manifest = self.capture_ready(root)

            result = self.run_commit(root, manifest)

            self.assertEqual(result.returncode, 0, result.stderr)
            committed = set(git(root, "diff", "--name-only", "--no-renames", f"{base}..HEAD").stdout.splitlines())
            self.assertEqual(committed, {"src/new [file]*.bin"})

    def test_advance_blocks_dirty_snapshot_then_cleans_up_after_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.prepare_review(root)
            manifest_data = json.loads(manifest.read_text(encoding="utf-8"))

            dirty, reviewed = self.advance.check(root, "notes/epics/demo.md")
            self.assertEqual(dirty, ["src/app.py"])
            self.assertEqual(reviewed, ["src/app.py"])

            result = self.run_commit(root, manifest)
            self.assertEqual(result.returncode, 0, result.stderr)
            dirty, reviewed = self.advance.check(root, "notes/epics/demo.md")
            self.assertEqual((dirty, reviewed), ([], ["src/app.py"]))

            removed_manifest, removed_ref = self.advance.cleanup(root, "notes/epics/demo.md")
            self.assertEqual(removed_manifest, manifest)
            self.assertEqual(removed_ref, manifest_data["review_ref"])
            self.assertFalse(manifest.exists())
            self.assertNotEqual(git(root, "rev-parse", "--verify", removed_ref, check=False).returncode, 0)

    def test_cleanup_allows_roadmap_change_written_by_advance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            head = self.init_repo(root)
            (root / "src/app.py").write_text("VALUE = 2\n", encoding="utf-8")
            roadmap = root / "notes" / "roadmap.md"
            roadmap.write_text("# Roadmap\n\n## Status\n\nactive\n", encoding="utf-8")
            self.write_passing_ledger(
                root,
                head,
                ["src/"],
                evidence={
                    "ledger": "notes/epics/demo.md",
                    "roadmap": "notes/roadmap.md",
                },
            )
            manifest = self.capture_ready(root)
            result = self.run_commit(root, manifest)
            self.assertEqual(result.returncode, 0, result.stderr)

            roadmap.write_text("# Roadmap\n\n## Status\n\ncomplete\n", encoding="utf-8")
            removed_manifest, _ = self.advance.cleanup(root, "notes/epics/demo.md")

            self.assertEqual(removed_manifest, manifest)
            self.assertFalse(manifest.exists())

    def test_cleanup_cli_requires_roadmap_to_advance_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            head = self.init_repo(root)
            (root / "src/app.py").write_text("VALUE = 2\n", encoding="utf-8")
            roadmap = root / "notes" / "roadmap.md"
            roadmap.write_text(
                "# Roadmap\n\n## Active Epic\n\n"
                "- name: Demo\n"
                "- ledger: notes/epics/demo.md\n"
                "- state: complete-pending-advance\n\n"
                "## Status\n\nactive\n",
                encoding="utf-8",
            )
            self.write_passing_ledger(
                root,
                head,
                ["src/"],
                evidence={
                    "ledger": "notes/epics/demo.md",
                    "roadmap": "notes/roadmap.md",
                },
            )
            manifest = self.capture_ready(root)
            result = self.run_commit(root, manifest)
            self.assertEqual(result.returncode, 0, result.stderr)
            command = [
                sys.executable,
                str(ADVANCE_SCRIPT),
                "--ledger",
                "notes/epics/demo.md",
                "--cleanup-after-advance",
            ]

            before = subprocess.run(command, cwd=root, text=True, capture_output=True)
            self.assertEqual(before.returncode, 2)
            self.assertIn("roadmap has not advanced", before.stderr)

            roadmap.write_text(
                "# Roadmap\n\n## Active Epic\n\n"
                "- name: Next\n"
                "- ledger: notes/epics/next.md\n"
                "- state: active\n\n"
                "## Status\n\nactive\n",
                encoding="utf-8",
            )
            after = subprocess.run(command, cwd=root, text=True, capture_output=True)
            self.assertEqual(after.returncode, 0, after.stderr)
            self.assertFalse(manifest.exists())

    def test_legacy_review_blocks_advance_only_while_repository_dirty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.init_repo(root)
            ledger = root / "notes/epics/demo.md"
            ledger.write_text(
                "# Demo\n\n## Review\n\n- reviewed-at: now\n  result: pass\n  notes: legacy\n\n## Status\n\ncomplete\n",
                encoding="utf-8",
            )
            (root / "src/app.py").write_text("VALUE = 2\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "legacy passing review"):
                self.advance.check(root, "notes/epics/demo.md")

            git(root, "add", "src/app.py")
            git(root, "commit", "-qm", "legacy reviewed work")
            dirty, reviewed = self.advance.check(root, "notes/epics/demo.md")
            self.assertEqual((dirty, reviewed), ([], []))

    def test_failed_capture_removes_partial_ref_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            head = self.init_repo(root)
            (root / "src/app.py").write_text("VALUE = 2\n", encoding="utf-8")
            review_id = "20260711T120000Z-a1b2c3d4"
            self.write_passing_ledger(
                root,
                head,
                ["src/"],
                review_id=review_id,
                evidence={
                    "ledger": "notes/epics/demo.md",
                    "roadmap": "notes/roadmap.md",
                },
            )

            with self.assertRaisesRegex(ValueError, "roadmap evidence"):
                self.capture_ready(root)

            manifest = root / ".deepdone/reviews" / f"{review_id}.json"
            ref = f"refs/deepdone/reviews/{review_id}"
            self.assertFalse(manifest.exists())
            self.assertNotEqual(git(root, "rev-parse", "--verify", ref, check=False).returncode, 0)


if __name__ == "__main__":
    unittest.main()
