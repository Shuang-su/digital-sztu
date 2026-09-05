from __future__ import annotations

import re
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
EXPANSION = "Grounded Origins University Stories, History & Interlinks"
TERMS = [
    ("G", "Grounded"),
    ("O", "Origins"),
    ("U", "University"),
    ("S", "Stories"),
    ("H", "History"),
    ("I", "Interlinks"),
]


def prose_without_code(markdown: str) -> str:
    lines = []
    fence = ""
    for line in markdown.splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence:
            if (
                marker
                and marker[1][0] == fence[0]
                and len(marker[1]) >= len(fence)
                and not marker[2].strip()
            ):
                fence = ""
            continue
        if marker:
            fence = marker[1]
            continue
        lines.append(line)
    return "\n".join(lines)


def identity_example() -> str:
    return "\n\n".join([
        "# Digital SZTU",
        "## 🐔🧱构史 · G.O.U.S.H.I.",
        EXPANSION,
        *(f"**{letter} — {term}**" for letter, term in TERMS),
    ])


class ReadmeTests(unittest.TestCase):
    def assert_public_identity(self, markdown: str) -> None:
        # These checks cover public wording, not inline emphasis or section placement.
        visible = re.sub(r"(?m)^> ?", "", re.sub(r"[*_`]", "", prose_without_code(markdown)))
        headings = [
            (len(marks), " ".join(title.split()))
            for marks, title in re.findall(r"(?m)^(#{1,6})[ \t]+([^\n]+)$", visible)
        ]
        self.assertEqual([title for level, title in headings if level == 1], ["Digital SZTU"])
        self.assertEqual(" ".join(visible.split()).count("🐔🧱构史 · G.O.U.S.H.I."), 1)
        self.assertEqual(" ".join(visible.split()).count(EXPANSION), 1)
        self.assertEqual(
            re.findall(r"(?m)^[ \t]*([GOUSHI])[ \t]+—[ \t]+([^\n]+?)[ \t]*$", visible),
            TERMS,
        )
        self.assertNotIn((2, "命名"), headings)
        self.assertNotIn("中文显示名称", visible)
        self.assertNotIn("🐔🧱时空", visible)
        self.assertNotIn("G.U.S.H.I.", visible)

    def test_readme_public_name_contract(self) -> None:
        self.assert_public_identity((ROOT / "README.md").read_text(encoding="utf-8"))

    def test_identity_allows_layout_and_emphasis_changes(self) -> None:
        original = identity_example()
        formatted = original.replace(
            "# Digital SZTU\n\n", "# **Digital SZTU**\n\n<br>\n\n项目介绍。\n\n"
        ).replace("## 🐔🧱构史 · G.O.U.S.H.I.", "## **🐔🧱构史** ·  G.O.U.S.H.I.")
        for letter, term in TERMS:
            formatted = formatted.replace(f"**{letter} — {term}**", f"**{letter}** — *{term}*")
        for example in (original, formatted + "\n\n新的收束段落。\n"):
            with self.subTest(example=example):
                self.assert_public_identity(example)

    def test_identity_rejects_name_and_expansion_regressions(self) -> None:
        original = identity_example()
        invalid_examples = {
            "standard name": original.replace("# Digital SZTU", "# Another Project"),
            "extra primary heading": original + "\n\n# Another Heading",
            "old five-letter name": original.replace("G.O.U.S.H.I.", "G.U.S.H.I."),
            "duplicate expansion": original + "\n\n" + EXPANSION,
            "plural English expansion": original.replace("Stories, History", "Stories, Histories"),
            "plural H entry": original.replace("H — History", "H — Histories"),
            "missing O entry": original.replace("**O — Origins**", ""),
            "wrong term order": original.replace(
                "**G — Grounded**\n\n**O — Origins**", "**O — Origins**\n\n**G — Grounded**"
            ),
        }
        for label, example in invalid_examples.items():
            with self.subTest(case=label), self.assertRaises(AssertionError):
                self.assert_public_identity(example)

    def test_code_examples_do_not_define_public_identity(self) -> None:
        original = identity_example()
        for marker in ("```", "~~~~"):
            with self.subTest(marker=marker):
                self.assert_public_identity(original + f"\n\n{marker}markdown\n# Example\n{marker}")
                with self.assertRaises(AssertionError):
                    self.assert_public_identity(f"{marker}markdown\n{original}\n{marker}")

    def test_readme_relative_links_exist(self) -> None:
        readme = prose_without_code((ROOT / "README.md").read_text(encoding="utf-8"))
        links = re.findall(r"(?<!!)\[[^\]\n]+\]\(([^)\n]+)\)", readme)
        self.assertTrue(links)
        for link in links:
            with self.subTest(link=link):
                target = urlsplit(link.strip("<>"))
                self.assertNotIn(target.scheme, {"file", "codex"})
                if target.scheme or not target.path:
                    continue
                path = Path(unquote(target.path))
                self.assertFalse(path.is_absolute())
                self.assertTrue((ROOT / path).resolve().is_relative_to(ROOT))
                self.assertTrue((ROOT / path).exists(), f"Missing README target: {path}")


if __name__ == "__main__":
    unittest.main()
