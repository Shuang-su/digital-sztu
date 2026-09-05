from __future__ import annotations

import importlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NamingCompatibilityTests(unittest.TestCase):
    def test_installed_distribution_and_plugin_agree(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
        plugin = json.loads((ROOT / ".codex-plugin/plugin.json").read_text())
        self.assertEqual(project["name"], "digital-sztu")
        self.assertEqual(plugin["name"], project["name"])
        self.assertEqual(plugin["version"], project["version"])
        self.assertEqual(importlib.metadata.version("digital-sztu"), project["version"])
        self.assertEqual(project["scripts"]["digital-sztu"], project["scripts"]["sztu-connect"])

    def test_legacy_imports_share_the_implementation(self):
        for name in ("build", "chat", "cli", "ingest", "knowledge", "privacy", "utils", "validation"):
            with self.subTest(module=name):
                self.assertIs(importlib.import_module(f"sztu_connect.{name}"),
                              importlib.import_module(f"digital_sztu.{name}"))

    def test_both_module_commands_validate_existing_records(self):
        results = []
        for module in ("digital_sztu", "sztu_connect"):
            result = subprocess.run([sys.executable, "-m", module, "--root", str(ROOT),
                                     "validate", "--json"], check=True, capture_output=True, text=True)
            results.append(json.loads(result.stdout))
        self.assertTrue(results[0]["ok"])
        self.assertEqual(results[0], results[1])
