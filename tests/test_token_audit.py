import unittest
import os
import sys
import tempfile

# Ensure src is in sys.path
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from token_diet import (
    estimate_tokens,
    classify_size,
    audit_file,
    detect_local_prompts,
    audit_git_hooks,
    fix_git_hooks,
    summarize_footprint,
    resolve_target_paths,
    audit_known_prompts,
    DEFAULT_PROMPT_PATHS,
    THRESHOLD_WARN_BYTES,
    THRESHOLD_ALERT_BYTES,
)


class TestTokenAudit(unittest.TestCase):
    def test_estimate_tokens(self):
        self.assertEqual(estimate_tokens(0), 0)
        self.assertEqual(estimate_tokens(4), 1)
        self.assertEqual(estimate_tokens(400), 100)
        self.assertEqual(estimate_tokens(10), 2)

    def test_classify_size(self):
        self.assertEqual(classify_size(100), ("OK", "optimal"))
        self.assertEqual(classify_size(THRESHOLD_WARN_BYTES + 1), ("WARN", "warning"))
        self.assertEqual(classify_size(THRESHOLD_ALERT_BYTES + 1), ("ALERT", "critical"))

    def test_audit_file_non_existent(self):
        res = audit_file("/non/existent/path/never_created.md")
        self.assertFalse(res["exists"])
        self.assertEqual(res["bytes"], 0)
        self.assertEqual(res["estimated_tokens"], 0)
        self.assertEqual(res["status"], "MISSING")

    def test_audit_file_exists(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".md") as f:
            f.write("12345678")
            tmp_path = f.name
        try:
            res = audit_file(tmp_path)
            self.assertTrue(res["exists"])
            self.assertEqual(res["bytes"], 8)
            self.assertEqual(res["estimated_tokens"], 2)
            self.assertEqual(res["status"], "OK")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_detect_local_prompts(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            agent_file = os.path.join(tmp_dir, "AGENTS.md")
            with open(agent_file, "w") as f:
                f.write("# Rule")
            cursor_file = os.path.join(tmp_dir, ".cursorrules")
            with open(cursor_file, "w") as f:
                f.write("# Cursor")

            detected = detect_local_prompts(tmp_dir)
            self.assertIn(agent_file, detected)
            self.assertIn(cursor_file, detected)

    def test_audit_git_hooks_safe_and_alert(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            hooks_dir = os.path.join(tmp_dir, ".git", "hooks")
            os.makedirs(hooks_dir)
            hook_file = os.path.join(hooks_dir, "pre-commit")

            # 1. Clean hook
            with open(hook_file, "w") as f:
                f.write("#!/bin/sh\nflake8 scripts/\n")
            alerts = audit_git_hooks(tmp_dir)
            self.assertEqual(len(alerts), 0)

            # 2. Irregular hook invoking LLM
            with open(hook_file, "w") as f:
                f.write("#!/bin/sh\ngga run --provider opencode\n")
            alerts = audit_git_hooks(tmp_dir)
            self.assertEqual(len(alerts), 1)
            self.assertEqual(alerts[0]["severity"], "critical")
            self.assertIn("gga", alerts[0]["matched_patterns"])

    def test_summarize_footprint(self):
        sample = [
            {"path": "a", "exists": True, "bytes": 100, "estimated_tokens": 25, "status": "OK"},
            {"path": "b", "exists": True, "bytes": 5000, "estimated_tokens": 1250, "status": "WARN"},
            {"path": "c", "exists": True, "bytes": 20000, "estimated_tokens": 5000, "status": "ALERT"},
            {"path": "d", "exists": False, "bytes": 0, "estimated_tokens": 0, "status": "MISSING"},
        ]
        summary = summarize_footprint(sample)
        self.assertEqual(summary["total_bytes"], 25100)
        self.assertEqual(summary["total_tokens"], 6275)
        self.assertEqual(summary["files_found"], 3)
        self.assertEqual(summary["total_checked"], 4)
        self.assertEqual(summary["warnings"], 1)
        self.assertEqual(summary["alerts"], 1)
        self.assertEqual(summary["status"], "CRITICAL_BLOAT")

    def test_resolve_target_paths_default_global(self):
        # When check_local is False
        paths = resolve_target_paths(None, check_local=False)
        self.assertEqual(paths, DEFAULT_PROMPT_PATHS)

    def test_resolve_target_paths_custom_files_and_dirs(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            f1 = os.path.join(tmp_dir, "a.txt")
            with open(f1, "w") as f:
                f.write("hello")
            sub_dir = os.path.join(tmp_dir, "sub")
            os.makedirs(sub_dir)
            f2 = os.path.join(sub_dir, "b.md")
            with open(f2, "w") as f:
                f.write("world")

    def test_fix_git_hooks_non_existent(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            res = fix_git_hooks(tmp_dir)
            self.assertFalse(res["fixed"])
            self.assertEqual(res["disabled_count"], 0)

    def test_fix_git_hooks_clean_no_op(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            hooks_dir = os.path.join(tmp_dir, ".git", "hooks")
            os.makedirs(hooks_dir)
            hook_file = os.path.join(hooks_dir, "pre-commit")
            with open(hook_file, "w") as f:
                f.write("#!/bin/sh\npytest tests/\n")

            res = fix_git_hooks(tmp_dir)
            self.assertFalse(res["fixed"])
            self.assertEqual(res["disabled_count"], 0)
            self.assertFalse(os.path.exists(hook_file + ".bak"))

    def test_fix_git_hooks_success(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            hooks_dir = os.path.join(tmp_dir, ".git", "hooks")
            os.makedirs(hooks_dir)
            hook_file = os.path.join(hooks_dir, "pre-commit")
            original_content = (
                "#!/bin/sh\n"
                "# Normal linter\n"
                "ruff check .\n"
                "# Silent LLM review\n"
                "gga run --provider opencode\n"
                "claude review --all\n"
            )
            with open(hook_file, "w") as f:
                f.write(original_content)
            os.chmod(hook_file, 0o755)

            # Before fix, audit should find critical alert
            alerts = audit_git_hooks(tmp_dir)
            self.assertEqual(len(alerts), 1)

            # Apply fix
            res = fix_git_hooks(tmp_dir)
            self.assertTrue(res["fixed"])
            self.assertEqual(res["disabled_count"], 2)
            self.assertTrue(os.path.exists(res["backup_path"]))

            # Verify backup content equals original content
            with open(res["backup_path"], "r") as f:
                self.assertEqual(f.read(), original_content)

            # Verify hook content has commented lines
            with open(hook_file, "r") as f:
                content = f.read()
            self.assertIn("# [token-diet disabled]: gga run --provider opencode", content)
            self.assertIn("# [token-diet disabled]: claude review --all", content)
            self.assertIn("ruff check .", content)

            # After fix, audit should find 0 alerts!
            alerts_after = audit_git_hooks(tmp_dir)
            self.assertEqual(len(alerts_after), 0)

            # Re-running fix should be a no-op
            res_repeat = fix_git_hooks(tmp_dir)
            self.assertFalse(res_repeat["fixed"])


if __name__ == "__main__":
    unittest.main()
