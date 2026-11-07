import os
import sys
import tempfile
import unittest

# Ensure src is in sys.path
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from token_diet.metrics import (
    THRESHOLD_ALERT_BYTES,
    THRESHOLD_WARN_BYTES,
    classify_size,
    estimate_tokens,
)
from token_diet.sections import (
    audit_sections,
    audit_sections_for_paths,
    split_sections,
)


class TestSections(unittest.TestCase):
    def test_preamble_and_two_sections_order_headings_lines(self):
        text = (
            "This is the preamble.\n"
            "It spans two lines.\n"
            "\n"
            "## Introduction\n"
            "Here is intro text.\n"
            "\n"
            "## Deep Dive\n"
            "Deeper details here.\n"
        )
        sections = split_sections(text, level=2)
        self.assertEqual(len(sections), 3)

        # 1. Preamble
        self.assertEqual(sections[0]["heading"], "(preamble)")
        self.assertEqual(sections[0]["level"], 0)
        self.assertEqual(sections[0]["line"], 1)
        self.assertEqual(
            sections[0]["text"],
            "This is the preamble.\nIt spans two lines.\n\n",
        )
        self.assertEqual(
            sections[0]["bytes"], len(sections[0]["text"].encode("utf-8"))
        )
        self.assertEqual(
            sections[0]["estimated_tokens"],
            estimate_tokens(sections[0]["bytes"]),
        )
        self.assertEqual(sections[0]["status"], "OK")
        self.assertEqual(sections[0]["severity"], "optimal")

        # 2. Section 1
        self.assertEqual(sections[1]["heading"], "Introduction")
        self.assertEqual(sections[1]["level"], 2)
        self.assertEqual(sections[1]["line"], 4)
        self.assertEqual(
            sections[1]["text"],
            "## Introduction\nHere is intro text.\n\n",
        )
        self.assertEqual(
            sections[1]["bytes"], len(sections[1]["text"].encode("utf-8"))
        )
        self.assertEqual(
            sections[1]["estimated_tokens"],
            estimate_tokens(sections[1]["bytes"]),
        )
        self.assertEqual(sections[1]["status"], "OK")
        self.assertEqual(sections[1]["severity"], "optimal")

        # 3. Section 2
        self.assertEqual(sections[2]["heading"], "Deep Dive")
        self.assertEqual(sections[2]["level"], 2)
        self.assertEqual(sections[2]["line"], 7)
        self.assertEqual(
            sections[2]["text"],
            "## Deep Dive\nDeeper details here.\n",
        )
        self.assertEqual(
            sections[2]["bytes"], len(sections[2]["text"].encode("utf-8"))
        )
        self.assertEqual(
            sections[2]["estimated_tokens"],
            estimate_tokens(sections[2]["bytes"]),
        )
        self.assertEqual(sections[2]["status"], "OK")
        self.assertEqual(sections[2]["severity"], "optimal")

    def test_subheading_stays_inside_parent_section(self):
        text = (
            "## Main Section\n"
            "Main content.\n"
            "### Sub Heading 1\n"
            "Sub content 1.\n"
            "#### Sub Sub Heading\n"
            "Sub sub content.\n"
            "## Next Section\n"
            "Next content.\n"
        )
        sections = split_sections(text, level=2)
        self.assertEqual(len(sections), 2)
        self.assertEqual(sections[0]["heading"], "Main Section")
        self.assertEqual(sections[0]["line"], 1)
        self.assertIn("### Sub Heading 1", sections[0]["text"])
        self.assertIn("#### Sub Sub Heading", sections[0]["text"])
        expected_parent_text = (
            "## Main Section\n"
            "Main content.\n"
            "### Sub Heading 1\n"
            "Sub content 1.\n"
            "#### Sub Sub Heading\n"
            "Sub sub content.\n"
        )
        self.assertEqual(sections[0]["text"], expected_parent_text)
        self.assertEqual(
            sections[0]["bytes"], len(expected_parent_text.encode("utf-8"))
        )
        self.assertEqual(sections[1]["heading"], "Next Section")
        self.assertEqual(sections[1]["line"], 7)

    def test_utf8_byte_counts_multibyte(self):
        text = "## Café & España 🔥\nContenido con acentos y emojis: 🚀\n"
        sections = split_sections(text, level=2)
        self.assertEqual(len(sections), 1)
        expected_bytes = len(text.encode("utf-8"))
        self.assertNotEqual(len(text), expected_bytes)
        self.assertEqual(sections[0]["bytes"], expected_bytes)
        self.assertEqual(sections[0]["heading"], "Café & España 🔥")

    def test_estimated_tokens_heuristic(self):
        text = "## Section\n" + ("a" * 100) + "\n"
        sections = split_sections(text, level=2)
        self.assertEqual(len(sections), 1)
        self.assertEqual(
            sections[0]["estimated_tokens"], sections[0]["bytes"] // 4
        )

    def test_size_threshold_classification(self):
        small_text = "## Small\n" + ("x" * 100) + "\n"
        s_small = split_sections(small_text)[0]
        self.assertEqual(s_small["status"], "OK")
        self.assertEqual(s_small["severity"], "optimal")

        warn_text = "## Warn\n" + ("w" * (THRESHOLD_WARN_BYTES + 10)) + "\n"
        s_warn = split_sections(warn_text)[0]
        self.assertEqual(s_warn["status"], "WARN")
        self.assertEqual(s_warn["severity"], "warning")

        alert_text = "## Alert\n" + ("!" * (THRESHOLD_ALERT_BYTES + 10)) + "\n"
        s_alert = split_sections(alert_text)[0]
        self.assertEqual(s_alert["status"], "ALERT")
        self.assertEqual(s_alert["severity"], "critical")

    def test_missing_file_returns_missing_shape(self):
        res = audit_sections("/non/existent/path/missing_test_file.md")
        self.assertEqual(
            res,
            {
                "path": "/non/existent/path/missing_test_file.md",
                "exists": False,
                "bytes": 0,
                "estimated_tokens": 0,
                "status": "MISSING",
                "severity": "none",
                "sections": [],
            },
        )

    def test_audit_sections_for_paths_aggregation(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            f1 = os.path.join(tmp_dir, "doc1.md")
            f2 = os.path.join(tmp_dir, "doc2.md")
            content1 = "## Heading 1\nHello world\n"
            content2 = "## Heading 2\nAnother document here\n"
            with open(f1, "w", encoding="utf-8") as f:
                f.write(content1)
            with open(f2, "w", encoding="utf-8") as f:
                f.write(content2)

            res = audit_sections_for_paths([f1, f2])
            self.assertEqual(res["file_count"], 2)
            self.assertEqual(len(res["files"]), 2)
            expected_bytes = len(content1.encode("utf-8")) + len(
                content2.encode("utf-8")
            )
            self.assertEqual(res["total_bytes"], expected_bytes)
            expected_tokens = estimate_tokens(
                len(content1.encode("utf-8"))
            ) + estimate_tokens(len(content2.encode("utf-8")))
            self.assertEqual(res["total_tokens"], expected_tokens)

    def test_text_with_no_headings_returns_empty(self):
        self.assertEqual(split_sections(""), [])
        self.assertEqual(split_sections("   \n\t  \n"), [])
        self.assertEqual(
            split_sections("This is plain text with no headings at all.\n"),
            [],
        )

    def test_whitespace_preamble_ignored(self):
        text = "   \n\n\t  \n## First Heading\nContent here.\n"
        sections = split_sections(text, level=2)
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0]["heading"], "First Heading")
        self.assertEqual(sections[0]["line"], 4)
        self.assertEqual(
            sections[0]["text"], "## First Heading\nContent here.\n"
        )

    def test_custom_heading_level(self):
        text = "# Level One\nContent 1\n## Level Two\nContent 2\n"
        sections_l1 = split_sections(text, level=1)
        self.assertEqual(len(sections_l1), 1)
        self.assertEqual(sections_l1[0]["heading"], "Level One")
        self.assertIn("## Level Two", sections_l1[0]["text"])

    def test_audit_sections_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = os.path.join(tmp_dir, "audit_test.md")
            content = "Preamble content\n\n## Section One\nBody text\n"
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            res = audit_sections(file_path)
            self.assertTrue(res["exists"])
            self.assertEqual(res["path"], file_path)
            expected_bytes = len(content.encode("utf-8"))
            self.assertEqual(res["bytes"], expected_bytes)
            self.assertEqual(
                res["estimated_tokens"], estimate_tokens(expected_bytes)
            )
            self.assertEqual(res["status"], "OK")
            self.assertEqual(res["severity"], "optimal")
            self.assertEqual(len(res["sections"]), 2)
            self.assertEqual(res["sections"][0]["heading"], "(preamble)")
            self.assertEqual(res["sections"][1]["heading"], "Section One")

    def test_audit_sections_oserror(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Passing a directory path to open will raise IsADirectoryError (an OSError)
            res = audit_sections(tmp_dir)
            self.assertFalse(res["exists"])
            self.assertEqual(res["path"], tmp_dir)
            self.assertEqual(res["status"], "ERROR")
            self.assertEqual(res["severity"], "critical")
            self.assertIn("error", res)
            self.assertEqual(res["sections"], [])
            self.assertEqual(res["bytes"], 0)
            self.assertEqual(res["estimated_tokens"], 0)


if __name__ == "__main__":
    unittest.main()
