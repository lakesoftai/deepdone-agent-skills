from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAPTURE_SCRIPT = ROOT / "skills/deepdone-review/scripts/capture_reviewed_change_set.py"
ADVANCE_SCRIPT = ROOT / "skills/deepdone-advance/scripts/check_reviewed_change_set.py"
COMMIT_SCRIPT = ROOT / "skills/deepdone-commit/scripts/commit_progress.py"


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
        self.commit = load_module("commit_progress_reviewed_set_test", COMMIT_SCRIPT)

    def init_repo(self, root: Path) -> str:
        git(root, "init", "-q")
        git(root, "config", "user.name", "DeepDone Test")
        git(root, "config", "user.email", "deepdone@example.test")
        (root / ".gitignore").write_text(".deepdone/\n", encoding="utf-8")
        app = root / "src" / "app.py"
        app.parent.mkdir(parents=True)
        app.write_text("VALUE = 1\n", encoding="utf-8")
        ledger = root / "notes" / "epics" / "demo.md"
        ledger.parent.mkdir(parents=True)
        ledger.write_text("# Demo\n\n## Status\n\nactive\n", encoding="utf-8")
        git(root, "add", ".gitignore", "src/app.py", "notes/epics/demo.md")
        git(root, "commit", "-qm", "initial")
        return git(root, "rev-parse", "HEAD").stdout.strip()

    def write_passing_ledger(self, root: Path, head: str, paths: list[str], review_id: str = "20260711T120000Z-a1b2c3d4") -> Path:
        ledger = root / "notes" / "epics" / "demo.md"
        path_lines = "\n".join(f"    - {path}" for path in paths)
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
            "  paths:\n"
            f"{path_lines}\n"
            "  notes: no blocking findings\n\n"
            "## Open Loops\n\nnone\n\n"
            "## Next Action\n\nPrepare commit.\n\n"
            "## Status\n\ncomplete\n",
            encoding="utf-8",
        )
        return ledger

    def prepare_review(self, root: Path, extra_paths: list[str] | None = None) -> Path:
        head = self.init_repo(root)
        (root / "src" / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        paths = ["src/app.py", "notes/epics/demo.md", *(extra_paths or [])]
        self.write_passing_ledger(root, head, paths)
        return self.capture.capture(root, "notes/epics/demo.md")

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

    def test_capture_records_exact_content_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = self.prepare_review(root)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["ledger_path"], "notes/epics/demo.md")
        self.assertEqual({item["path"] for item in manifest["paths"]}, {"src/app.py", "notes/epics/demo.md"})
        self.assertTrue(all(item["sha256"] for item in manifest["paths"]))

    def test_capture_rejects_repository_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            head = self.init_repo(root)
            (root / "src/app.py").write_text("VALUE = 2\n", encoding="utf-8")
            self.write_passing_ledger(root, head, ["src/app.py", "notes/epics/demo.md", "../outside"])

            with self.assertRaisesRegex(ValueError, "escapes repository"):
                self.capture.capture(root, "notes/epics/demo.md")

    def test_capture_handles_rename_deletion_symlink_binary_and_spaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            head = self.init_repo(root)
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
            self.write_passing_ledger(
                root,
                head,
                ["src/new name.txt", "src/delete.txt", "src/blob.bin", "src/link.py", "notes/epics/demo.md"],
            )

            manifest = json.loads(self.capture.capture(root, "notes/epics/demo.md").read_text(encoding="utf-8"))

        by_path = {item["path"]: item for item in manifest["paths"]}
        self.assertEqual(by_path["src/new name.txt"]["old_path"], "src/old.txt")
        self.assertEqual(by_path["src/delete.txt"]["kind"], "deleted")
        self.assertEqual(by_path["src/blob.bin"]["kind"], "file")
        self.assertEqual(by_path["src/link.py"]["kind"], "symlink")

    def test_exact_commit_preserves_unrelated_unstaged_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.prepare_review(root)
            unrelated = root / "scratch.txt"
            unrelated.write_text("user work\n", encoding="utf-8")
            before = git(root, "rev-parse", "HEAD").stdout.strip()

            result = self.run_commit(root, manifest)

            self.assertEqual(result.returncode, 0, result.stderr)
            committed = set(git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "--no-renames", f"{before}..HEAD").stdout.splitlines())
            self.assertEqual(committed, {"src/app.py", "notes/epics/demo.md"})
            self.assertEqual(unrelated.read_text(encoding="utf-8"), "user work\n")
            self.assertIn("?? scratch.txt", git(root, "status", "--short", "--untracked-files=all").stdout)
            self.assertFalse(manifest.exists())

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
            self.assertIn("reviewed paths changed after review", result.stderr)

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

    def test_dangerous_reviewed_path_blocks_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            head = self.init_repo(root)
            (root / "secret.pem").write_text("not-a-real-secret\n", encoding="utf-8")
            self.write_passing_ledger(root, head, ["secret.pem", "notes/epics/demo.md"])
            manifest = self.capture.capture(root, "notes/epics/demo.md")

            result = self.run_commit(root, manifest)

            self.assertEqual(result.returncode, 2)
            self.assertIn("dangerous paths", result.stderr)

    def test_rename_commit_matches_effective_reviewed_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.init_repo(root)
            old = root / "src/old.txt"
            old.write_text("rename me\n", encoding="utf-8")
            git(root, "add", "src/old.txt")
            git(root, "commit", "-qm", "add rename source")
            base = git(root, "rev-parse", "HEAD").stdout.strip()
            git(root, "mv", "src/old.txt", "src/new name.txt")
            self.write_passing_ledger(root, base, ["src/new name.txt", "notes/epics/demo.md"])
            manifest = self.capture.capture(root, "notes/epics/demo.md")

            result = self.run_commit(root, manifest)

            self.assertEqual(result.returncode, 0, result.stderr)
            committed = set(
                git(root, "diff", "--name-only", "--no-renames", f"{base}..HEAD").stdout.splitlines()
            )
            self.assertEqual(committed, {"src/old.txt", "src/new name.txt", "notes/epics/demo.md"})

    def test_untracked_file_with_spaces_commits_when_reviewed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self.init_repo(root)
            new_file = root / "src/new [file]*.bin"
            new_file.write_bytes(b"\x00\xffreviewed")
            self.write_passing_ledger(root, base, ["src/new [file]*.bin", "notes/epics/demo.md"])
            manifest = self.capture.capture(root, "notes/epics/demo.md")

            result = self.run_commit(root, manifest)

            self.assertEqual(result.returncode, 0, result.stderr)
            committed = set(git(root, "diff", "--name-only", "--no-renames", f"{base}..HEAD").stdout.splitlines())
            self.assertEqual(committed, {"src/new [file]*.bin", "notes/epics/demo.md"})

    def test_advance_blocks_dirty_reviewed_set_and_allows_clean_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.prepare_review(root)

            dirty, reviewed = self.advance.check(root, "notes/epics/demo.md")
            self.assertEqual(set(dirty), {"src/app.py", "notes/epics/demo.md"})
            self.assertEqual(set(reviewed), {"src/app.py", "notes/epics/demo.md"})

            git(root, "add", "src/app.py", "notes/epics/demo.md")
            git(root, "commit", "-qm", "manual reviewed commit")
            dirty, _ = self.advance.check(root, "notes/epics/demo.md")
            self.assertEqual(dirty, [])

    def test_legacy_review_blocks_advance_only_while_dirty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.init_repo(root)
            ledger = root / "notes/epics/demo.md"
            ledger.write_text(
                "# Demo\n\n## Review\n\n- reviewed-at: now\n  result: pass\n  notes: legacy\n\n## Status\n\ncomplete\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "legacy passing review"):
                self.advance.check(root, "notes/epics/demo.md")

            git(root, "add", "notes/epics/demo.md")
            git(root, "commit", "-qm", "legacy reviewed work")
            dirty, reviewed = self.advance.check(root, "notes/epics/demo.md")
            self.assertEqual((dirty, reviewed), ([], []))


if __name__ == "__main__":
    unittest.main()
