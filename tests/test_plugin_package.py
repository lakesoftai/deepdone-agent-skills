from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_URI = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
VERSION = "2.1.0"
DESCRIPTION = "End-to-end development with your coding agent."
AUTHOR = {"name": "lakesoftai"}
ALLOWED_PLUGIN_FIELDS = {
    "$schema",
    "name",
    "version",
    "description",
    "author",
    "homepage",
    "repository",
    "license",
    "keywords",
    "extensions",
}
ALLOWED_SKILL_FIELDS = {
    "name",
    "description",
    "license",
    "compatibility",
    "metadata",
    "allowed-tools",
}


def load_doctor():
    path = ROOT / "scripts/doctor.py"
    spec = importlib.util.spec_from_file_location("deepdone_doctor_plugin_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


DOCTOR = load_doctor()


def load_json(relative_path: str) -> dict[str, object]:
    value = json.loads((ROOT / relative_path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"{relative_path} must contain a JSON object")
    return value


def skill_frontmatter() -> tuple[dict[str, str], str]:
    text = (ROOT / "skills/deepdone/SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"^---\n(?P<body>.*?)\n---\n", text, flags=re.DOTALL)
    if not match:
        raise AssertionError("skills/deepdone/SKILL.md has no frontmatter")
    fields: dict[str, str] = {}
    for line in match.group("body").splitlines():
        if not line or line[0].isspace() or ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key] = value.strip()
    return fields, match.group("body")


class PluginPackageTests(unittest.TestCase):
    def test_portable_manifest_uses_agent_plugins_v1(self) -> None:
        manifest = load_json("plugin.json")

        self.assertEqual(set(manifest).difference(ALLOWED_PLUGIN_FIELDS), set())
        self.assertEqual(manifest["$schema"], SCHEMA_URI)
        self.assertEqual(manifest["name"], "deepdone")
        self.assertEqual(manifest["version"], VERSION)
        self.assertEqual(manifest["description"], DESCRIPTION)
        self.assertEqual(manifest["author"], AUTHOR)
        self.assertEqual(manifest["homepage"], "https://deepdone.ai/")
        self.assertEqual(manifest["repository"], "https://github.com/lakesoftai/deepdone-agent-skills")
        self.assertEqual(manifest["license"], "Apache-2.0")
        self.assertNotIn("skills", manifest)
        self.assertNotIn("mcpServers", manifest)

    def test_fixed_skill_discovery_finds_only_deepdone(self) -> None:
        discovered = {
            path.parent.name
            for path in (ROOT / "skills").glob("*/SKILL.md")
            if path.is_file()
        }

        self.assertEqual(discovered, {"deepdone"})
        self.assertFalse((ROOT / "mcp.json").exists())

    def test_skill_frontmatter_conforms_to_agent_skills(self) -> None:
        fields, raw = skill_frontmatter()

        self.assertEqual(set(fields).difference(ALLOWED_SKILL_FIELDS), set())
        self.assertEqual(fields["name"], "deepdone")
        self.assertTrue(fields["description"])
        self.assertLessEqual(len(fields["description"]), 1024)
        self.assertEqual(fields["license"], "Apache-2.0")
        self.assertLessEqual(len(fields["compatibility"]), 500)
        self.assertIn("metadata", fields)
        self.assertRegex(raw, r"(?m)^  author: lakesoftai$")
        self.assertNotIn("slug", fields)

    def test_codex_overlay_contains_only_presentation_metadata(self) -> None:
        manifest = load_json("plugin.json")
        overlay = load_json(".codex-plugin/plugin.json")

        self.assertEqual(set(overlay), {"name", "version", "description", "author", "interface"})
        self.assertEqual(overlay["name"], manifest["name"])
        self.assertEqual(overlay["version"], manifest["version"])
        self.assertEqual(overlay["description"], manifest["description"])
        self.assertEqual(overlay["author"], manifest["author"])
        interface = overlay["interface"]
        self.assertIsInstance(interface, dict)
        assert isinstance(interface, dict)
        self.assertEqual(interface["displayName"], "DeepDone")
        self.assertEqual(interface["developerName"], "lakesoftai")
        self.assertEqual(interface["websiteURL"], manifest["homepage"])
        prompts = interface["defaultPrompt"]
        self.assertIsInstance(prompts, list)
        assert isinstance(prompts, list)
        self.assertLessEqual(len(prompts), 3)
        self.assertTrue(all(isinstance(prompt, str) and 0 < len(prompt) <= 128 for prompt in prompts))

    def test_repo_marketplace_points_at_plugin_root(self) -> None:
        marketplace = load_json(".agents/plugins/marketplace.json")

        self.assertEqual(marketplace["name"], "deepdone")
        plugins = marketplace["plugins"]
        self.assertIsInstance(plugins, list)
        assert isinstance(plugins, list)
        self.assertEqual(len(plugins), 1)
        entry = plugins[0]
        self.assertEqual(entry["name"], "deepdone")
        self.assertEqual(entry["source"], {"source": "local", "path": "."})
        self.assertEqual(
            entry["policy"],
            {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        )

    def test_plugin_package_paths_stay_inside_root(self) -> None:
        root = ROOT.resolve()
        package_paths = [
            ROOT / "plugin.json",
            ROOT / "skills",
            ROOT / ".codex-plugin",
            ROOT / ".agents/plugins",
        ]

        paths: list[Path] = []
        for package_path in package_paths:
            paths.append(package_path)
            if package_path.is_dir():
                paths.extend(package_path.rglob("*"))

        self.assertTrue(all(path.resolve().is_relative_to(root) for path in paths))

    def test_containment_rejects_escape_and_broken_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            root.mkdir()
            inside = root / "inside.txt"
            inside.write_text("inside\n", encoding="utf-8")
            outside = Path(tmp) / "outside.txt"
            outside.write_text("outside\n", encoding="utf-8")
            internal_link = root / "internal-link"
            escape_link = root / "escape-link"
            broken_link = root / "broken-link"
            os.symlink(inside, internal_link)
            os.symlink(outside, escape_link)
            os.symlink(root / "missing.txt", broken_link)

            self.assertTrue(DOCTOR.package_path_is_contained(internal_link, root))
            self.assertFalse(DOCTOR.package_path_is_contained(escape_link, root))
            self.assertFalse(DOCTOR.package_path_is_contained(broken_link, root))


if __name__ == "__main__":
    unittest.main()
