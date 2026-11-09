"""
test_security.py

Security regression and hardening test suite for token-diet.
Verifies protections against:
1. Symlink following in hook modification and backup creation.
2. Repository containment escapes via core.hooksPath.
3. Unbounded reads and non-regular file DoS (/dev/zero, FIFOs, devices).
4. CI gate bypasses via NaN / Inf in --max-delta.
5. Absolute / relative path AI invocation detection without false positives on filenames.
6. Terminal ANSI / control character injection sanitization.
"""

import argparse
import os
import shutil
import stat
import tempfile
import unittest

from token_diet.baseline import check_budget, load_baseline
from token_diet.cli import _validate_max_delta, fix_git_hooks, sanitize_text
from token_diet.git_hooks import has_ai_invocation
from token_diet.mcp_audit import audit_mcp_config
from token_diet.sections import audit_sections


class TestSecurityHardening(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="token_diet_sec_test_")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_fix_git_hooks_rejects_symlink_hook(self):
        """Verify fix_git_hooks refuses to write to a symlinked hook file."""
        repo_dir = os.path.join(self.test_dir, "repo")
        git_dir = os.path.join(repo_dir, ".git")
        hooks_dir = os.path.join(git_dir, "hooks")
        os.makedirs(hooks_dir, exist_ok=True)

        target_file = os.path.join(self.test_dir, "target_outside.sh")
        with open(target_file, "w") as f:
            f.write("#!/bin/sh\nclaude review\n")

        hook_path = os.path.join(hooks_dir, "pre-commit")
        os.symlink(target_file, hook_path)

        result = fix_git_hooks(repo_dir)
        self.assertFalse(result["fixed"])
        self.assertIn("symlink", result["error"].lower())

        # Verify target was NOT modified
        with open(target_file, "r") as f:
            self.assertIn("claude review", f.read())

    def test_fix_git_hooks_rejects_symlink_backup(self):
        """Verify fix_git_hooks refuses to overwrite a symlinked .bak path."""
        repo_dir = os.path.join(self.test_dir, "repo")
        git_dir = os.path.join(repo_dir, ".git")
        hooks_dir = os.path.join(git_dir, "hooks")
        os.makedirs(hooks_dir, exist_ok=True)

        hook_path = os.path.join(hooks_dir, "pre-commit")
        with open(hook_path, "w") as f:
            f.write("#!/bin/sh\nclaude review\n")

        sensitive_target = os.path.join(self.test_dir, "sensitive.txt")
        with open(sensitive_target, "w") as f:
            f.write("SECRET_DATA")

        backup_path = hook_path + ".bak"
        os.symlink(sensitive_target, backup_path)

        result = fix_git_hooks(repo_dir)
        self.assertFalse(result["fixed"])
        self.assertIn("symlink", result["error"].lower())

        # Verify sensitive target was preserved intact
        with open(sensitive_target, "r") as f:
            self.assertEqual(f.read(), "SECRET_DATA")

    def test_fix_git_hooks_boundary_escape_prevention(self):
        """Verify fix_git_hooks refuses to modify hooks outside the repository boundary."""
        repo_dir = os.path.join(self.test_dir, "repo")
        git_dir = os.path.join(repo_dir, ".git")
        os.makedirs(git_dir, exist_ok=True)

        external_hooks = os.path.join(self.test_dir, "external_hooks")
        os.makedirs(external_hooks, exist_ok=True)
        external_hook = os.path.join(external_hooks, "pre-commit")
        with open(external_hook, "w") as f:
            f.write("#!/bin/sh\nclaude review\n")

        # Point core.hooksPath outside the repo
        config_path = os.path.join(git_dir, "config")
        with open(config_path, "w") as f:
            f.write(f"[core]\n\thooksPath = {external_hooks}\n")

        result = fix_git_hooks(repo_dir)
        self.assertFalse(result["fixed"])
        self.assertIn("outside repository boundary", result["error"].lower())

    def test_sections_rejects_special_files(self):
        """Verify audit_sections rejects character devices, FIFOs, and non-regular files."""
        if os.path.exists("/dev/zero"):
            result = audit_sections("/dev/zero")
            self.assertFalse(result["exists"])
            self.assertIn("Not a regular file", result["error"])

    def test_baseline_rejects_special_files(self):
        """Verify load_baseline rejects character devices and non-regular files."""
        if os.path.exists("/dev/zero"):
            result = load_baseline("/dev/zero")
            self.assertFalse(result["ok"])
            self.assertIn("not a regular file", result["error"].lower())

    def test_mcp_audit_rejects_special_files(self):
        """Verify audit_mcp_config rejects character devices and non-regular files."""
        if os.path.exists("/dev/zero"):
            result = audit_mcp_config("/dev/zero")
            self.assertFalse(result["exists"])
            self.assertIn("Not a regular file", result["error"])

    def test_max_delta_nan_and_inf_validation(self):
        """Verify _validate_max_delta and check_budget reject NaN and Inf."""
        for invalid_val in ["nan", "NaN", "inf", "-inf", "Infinity"]:
            with self.assertRaises(argparse.ArgumentTypeError):
                _validate_max_delta(invalid_val)

        res_nan = check_budget(100, 100, float("nan"))
        self.assertTrue(res_nan["exceeded"])

        res_inf = check_budget(100, 100, float("inf"))
        self.assertTrue(res_inf["exceeded"])

    def test_has_ai_invocation_paths_and_extensions(self):
        """Verify absolute/relative paths match while file extensions do not."""
        self.assertEqual(has_ai_invocation("/usr/local/bin/claude run"), ["claude"])
        self.assertEqual(has_ai_invocation("./claude check"), ["claude"])
        self.assertEqual(has_ai_invocation("/opt/tools/gemini --fix"), ["gemini"])
        self.assertEqual(has_ai_invocation("exec /bin/opencode"), ["opencode"])

        # Extensions and subdirectories should NOT match
        self.assertEqual(has_ai_invocation("echo opencode.json"), [])
        self.assertEqual(has_ai_invocation("cat claude.md"), [])
        self.assertEqual(has_ai_invocation("python gemini.py"), [])
        self.assertEqual(has_ai_invocation("ls /var/log/claude/audit.log"), [])

    def test_sanitize_text_strips_ansi_and_control_chars(self):
        """Verify sanitize_text removes terminal escapes and dangerous control sequences."""
        malicious_heading = "\x1b[31;1mDanger\x1b[0m \x1b[2JHeading\a"
        sanitized = sanitize_text(malicious_heading)
        self.assertEqual(sanitized, "Danger Heading")
        self.assertNotIn("\x1b", sanitized)
        self.assertNotIn("\a", sanitized)


if __name__ == "__main__":
    unittest.main()
