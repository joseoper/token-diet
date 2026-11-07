import unittest
import os
import sys
import io
import json
import tempfile
import contextlib
from unittest.mock import patch

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


class TestCliFlags(unittest.TestCase):
    """End-to-end coverage for the v0.2 audit surfaces exposed on the CLI."""

    def _run(self, argv, cwd=None):
        """Runs the CLI with argv, returning (exit_code, stdout, stderr)."""
        from token_diet import cli

        out, err = io.StringIO(), io.StringIO()
        code = 0
        old_cwd = os.getcwd()
        if cwd:
            os.chdir(cwd)
        try:
            with patch.object(sys, "argv", ["token-diet"] + argv):
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    try:
                        cli.main()
                    except SystemExit as exc:
                        code = exc.code if isinstance(exc.code, int) else 1
        finally:
            os.chdir(old_cwd)
        return code, out.getvalue(), err.getvalue()

    def test_sections_reports_heading_breakdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = os.path.join(tmp, "AGENTS.md")
            with open(doc, "w", encoding="utf-8") as f:
                f.write("# Title\n\nIntro.\n\n## Alpha\n\nAAAA\n\n## Beta\n\nBBBB\n")

            code, out, _ = self._run(["--sections", doc])
            self.assertEqual(code, 0)
            self.assertIn("SECTION BREAKDOWN", out)
            self.assertIn("Alpha", out)
            self.assertIn("Beta", out)

    def test_sections_json_payload_omits_source_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = os.path.join(tmp, "AGENTS.md")
            with open(doc, "w", encoding="utf-8") as f:
                f.write("## Alpha\n\nbody\n")

            code, out, _ = self._run(["--sections", "--json", doc])
            self.assertEqual(code, 0)
            payload = json.loads(out)
            self.assertEqual(payload["sections"]["file_count"], 1)
            section = payload["sections"]["files"][0]["sections"][0]
            self.assertEqual(section["heading"], "Alpha")
            self.assertNotIn("text", section)

    def test_mcp_reports_server_overhead(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "AGENTS.md"), "w", encoding="utf-8") as f:
                f.write("# local\n")
            with open(os.path.join(tmp, "opencode.json"), "w", encoding="utf-8") as f:
                json.dump({"mcp": {"engram": {"type": "local", "command": ["npx", "engram"]}}}, f)

            code, out, _ = self._run(["--mcp", "--json"], cwd=tmp)
            self.assertEqual(code, 0)
            payload = json.loads(out)
            self.assertEqual(payload["mcp"]["config_count"], 1)
            self.assertEqual(payload["mcp"]["total_servers"], 1)
            self.assertEqual(payload["mcp"]["configs"][0]["format"], "opencode")

    def test_hook_alert_through_gitdir_reference_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = os.path.join(tmp, "repo")
            gitdir = os.path.join(tmp, "gitdirs", "wt1")
            os.makedirs(repo)
            os.makedirs(os.path.join(gitdir, "hooks"))
            with open(os.path.join(repo, ".git"), "w", encoding="utf-8") as f:
                f.write(f"gitdir: {gitdir}\n")
            with open(os.path.join(gitdir, "hooks", "pre-commit"), "w", encoding="utf-8") as f:
                f.write("#!/bin/sh\ngga run --provider opencode\n")
            with open(os.path.join(repo, "AGENTS.md"), "w", encoding="utf-8") as f:
                f.write("# local\n")

            code, out, _ = self._run(["--json"], cwd=repo)
            self.assertEqual(code, 0)
            alerts = json.loads(out)["hook_alerts"]
            self.assertEqual(len(alerts), 1)
            self.assertIn("gga", alerts[0]["matched_patterns"])

    def test_hook_alert_follows_commondir_of_linked_worktree(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = os.path.join(tmp, "repo")
            gitdir = os.path.join(tmp, "gitdirs", "wt1")
            common = os.path.join(tmp, "gitdirs", "common")
            os.makedirs(repo)
            os.makedirs(gitdir)
            os.makedirs(os.path.join(common, "hooks"))
            with open(os.path.join(repo, ".git"), "w", encoding="utf-8") as f:
                f.write(f"gitdir: {gitdir}\n")
            with open(os.path.join(gitdir, "commondir"), "w", encoding="utf-8") as f:
                f.write("../common\n")
            with open(os.path.join(common, "hooks", "pre-commit"), "w", encoding="utf-8") as f:
                f.write("#!/bin/sh\nclaude review --all\n")
            with open(os.path.join(repo, "AGENTS.md"), "w", encoding="utf-8") as f:
                f.write("# local\n")

            code, out, _ = self._run(["--json"], cwd=repo)
            self.assertEqual(code, 0)
            alerts = json.loads(out)["hook_alerts"]
            self.assertEqual(len(alerts), 1)
            self.assertIn(common, alerts[0]["path"])

    def test_core_hooks_path_is_audited_and_fixed(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ".git"))
            hooks_dir = os.path.join(tmp, ".githooks")
            os.makedirs(hooks_dir)
            with open(os.path.join(tmp, ".git", "config"), "w", encoding="utf-8") as f:
                f.write("[core]\n\thooksPath = .githooks\n")
            hook = os.path.join(hooks_dir, "pre-commit")
            with open(hook, "w", encoding="utf-8") as f:
                f.write("#!/bin/sh\nruff check .\ngga run\n")
            with open(os.path.join(tmp, "AGENTS.md"), "w", encoding="utf-8") as f:
                f.write("# local\n")

            code, out, _ = self._run(["--json"], cwd=tmp)
            self.assertEqual(code, 0)
            self.assertEqual(len(json.loads(out)["hook_alerts"]), 1)

            code, out, _ = self._run(["--fix-hooks", "--json"], cwd=tmp)
            self.assertEqual(code, 0)
            fixed = json.loads(out)["fix_hooks"]
            self.assertTrue(fixed["fixed"])
            self.assertTrue(os.path.exists(hook + ".bak"))
            with open(hook, "r", encoding="utf-8") as f:
                self.assertIn("# [token-diet disabled]", f.read())

    def test_baseline_budget_gate_exceeded(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = os.path.join(tmp, "AGENTS.md")
            with open(doc, "w", encoding="utf-8") as f:
                f.write("x" * 400)
            baseline = os.path.join(tmp, "baseline.json")
            with open(baseline, "w", encoding="utf-8") as f:
                json.dump({"total_tokens": 50}, f)

            code, out, _ = self._run(["--baseline", baseline, "--max-delta", "10", doc])
            self.assertEqual(code, 1)
            self.assertIn("BUDGET EXCEEDED", out)

    def test_baseline_budget_gate_within_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = os.path.join(tmp, "AGENTS.md")
            with open(doc, "w", encoding="utf-8") as f:
                f.write("x" * 400)
            baseline = os.path.join(tmp, "baseline.json")
            with open(baseline, "w", encoding="utf-8") as f:
                json.dump({"total_tokens": 50}, f)

            code, out, _ = self._run(["--baseline", baseline, "--max-delta", "100", doc])
            self.assertEqual(code, 0)
            self.assertIn("Within budget", out)

    def test_max_delta_without_baseline_is_a_usage_error(self):
        code, _, err = self._run(["--max-delta", "10"])
        self.assertEqual(code, 2)
        self.assertIn("--baseline", err)

    def test_baseline_missing_file_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = os.path.join(tmp, "AGENTS.md")
            with open(doc, "w", encoding="utf-8") as f:
                f.write("x" * 400)
            missing = os.path.join(tmp, "nope.json")

            code, _, err = self._run(["--baseline", missing, doc])
            self.assertEqual(code, 2)
            self.assertIn("Baseline file not found", err)


if __name__ == "__main__":
    unittest.main()
