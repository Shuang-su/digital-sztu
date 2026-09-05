from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit

from test_readme import prose_without_code


ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = [
    "README.md", "AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md",
    "docs/GETTING_STARTED.md", "docs/PLUGIN.md", "docs/ONBOARDING_TEST_MATRIX.md",
    "docs/CHAT_IMPORT.md",
    *[path.relative_to(ROOT).as_posix() for path in sorted((ROOT / "skills").glob("*/SKILL.md"))],
]


def heading_anchors(markdown: str) -> set[str]:
    # Local links here target plain section names; preserve CJK and GitHub's
    # duplicate-heading suffix convention while excluding code fences.
    counts: dict[str, int] = {}
    result = set()
    for title in re.findall(r"(?m)^#{1,6}\s+(.+?)\s*$", prose_without_code(markdown)):
        visible = re.sub(r"<[^>]*>", "", title)
        visible = re.sub(r"[*_`]", "", visible).strip().lower()
        slug = re.sub(r"[^\w\- ]", "", visible).replace(" ", "-")
        index = counts.get(slug, 0)
        counts[slug] = index + 1
        result.add(slug if index == 0 else f"{slug}-{index}")
    return result


class OnboardingDocumentTests(unittest.TestCase):
    def test_relative_files_and_section_targets_resolve(self) -> None:
        for relative in DOCUMENTS:
            document = ROOT / relative
            markdown = prose_without_code(document.read_text(encoding="utf-8"))
            for link in re.findall(r"(?<!!)\[[^\]\n]+\]\(([^)\n]+)\)", markdown):
                with self.subTest(document=relative, link=link):
                    target = urlsplit(link.strip("<>"))
                    self.assertNotIn(target.scheme, {"codex", "file"})
                    if target.scheme:
                        continue
                    path = (document.parent / unquote(target.path)).resolve() if target.path else document
                    self.assertTrue(path.is_relative_to(ROOT))
                    self.assertTrue(path.exists(), path)
                    if target.fragment and path.suffix == ".md":
                        self.assertIn(unquote(target.fragment),
                                      heading_anchors(path.read_text(encoding="utf-8")))

    def test_public_prompt_maps_to_the_shared_local_guide(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        url = re.search(r"https://raw\.githubusercontent\.com/Shuang-su/digital-sztu/main/(\S+\.md)", readme)
        self.assertIsNotNone(url)
        self.assertEqual(url[1], "docs/GETTING_STARTED.md")
        self.assertTrue((ROOT / url[1]).is_file())
        # This is a local target check, deliberately not a remote availability claim.

    def test_native_routes_point_to_one_skill_and_existing_rules(self) -> None:
        manifest = json.loads((ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        skill_root = (ROOT / manifest["skills"]).resolve()
        self.assertTrue((skill_root / "setup-digital-sztu/SKILL.md").is_file())
        prompts = manifest["interface"]["defaultPrompt"]
        self.assertLessEqual(len(prompts), 3)
        self.assertTrue(all(len(item) <= 128 for item in prompts))
        self.assertTrue(any("setup-digital-sztu" in item for item in prompts))
        imports = re.findall(r"(?m)^@(\S+)$", (ROOT / "CLAUDE.md").read_text(encoding="utf-8"))
        self.assertEqual(imports, ["AGENTS.md"])
        self.assertTrue((ROOT / imports[0]).is_file())
        self.assertFalse((ROOT / ".agents/skills/setup-digital-sztu").exists())

    def test_starter_metadata_does_not_register_native_capabilities_as_services(self) -> None:
        manifest = json.loads((ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "digital-sztu")
        for field in ("mcpServers", "apps", "hooks"):
            self.assertNotIn(field, manifest)
        self.assertFalse((ROOT / ".mcp.json").exists())
        self.assertFalse((ROOT / ".app.json").exists())
        # Check discoverability and the user-facing consent entry, not prose layout.
        starter = manifest["interface"]["defaultPrompt"][0]
        self.assertIn("Computer Use", starter)
        self.assertIn("Computer History", starter)
        self.assertIn("我授权", starter)
        self.assertIn("setup-digital-sztu", starter)


if __name__ == "__main__":
    unittest.main()
