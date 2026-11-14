import os
import sys
import tempfile
import unittest
from unittest import mock

# Ensure src is in sys.path
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from token_diet.git_hooks import (
    AI_HOOK_KEYWORDS,
    find_ai_invocations,
    has_ai_invocation,
    read_core_hooks_path,
    resolve_common_dir,
    resolve_git_dir,
    resolve_hooks_dir,
    rewrite_line_neutralizing_ai,
)


class TestGitHooks(unittest.TestCase):
    def test_resolve_git_dir_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            git_dir = os.path.join(tmp_dir, ".git")
            os.makedirs(git_dir)
            resolved = resolve_git_dir(tmp_dir)
            self.assertEqual(resolved, os.path.abspath(git_dir))

    def test_resolve_git_dir_file_relative(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_dir = os.path.join(tmp_dir, "worktree1")
            os.makedirs(repo_dir)
            main_git = os.path.join(tmp_dir, "main", ".git", "worktrees", "wt1")
            os.makedirs(main_git)

            git_file = os.path.join(repo_dir, ".git")
            with open(git_file, "w", encoding="utf-8") as f:
                f.write("gitdir: ../main/.git/worktrees/wt1\n")

            resolved = resolve_git_dir(repo_dir)
            self.assertEqual(resolved, os.path.abspath(main_git))

    def test_resolve_git_dir_file_absolute(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_dir = os.path.join(tmp_dir, "worktree1")
            os.makedirs(repo_dir)
            target_git = os.path.join(tmp_dir, "target_git")
            os.makedirs(target_git)

            git_file = os.path.join(repo_dir, ".git")
            with open(git_file, "w", encoding="utf-8") as f:
                f.write(f"gitdir: {target_git}\n")

            resolved = resolve_git_dir(repo_dir)
            self.assertEqual(resolved, os.path.abspath(target_git))

    def test_resolve_git_dir_tilde_expansion(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_home = os.path.join(tmp_dir, "home")
            target_git = os.path.join(fake_home, "my_git_dir")
            os.makedirs(target_git)

            repo_dir = os.path.join(tmp_dir, "repo")
            os.makedirs(repo_dir)
            git_file = os.path.join(repo_dir, ".git")
            with open(git_file, "w", encoding="utf-8") as f:
                f.write("gitdir: ~/my_git_dir\n")

            with mock.patch.dict(os.environ, {"HOME": fake_home}):
                resolved = resolve_git_dir(repo_dir)
                self.assertEqual(resolved, os.path.abspath(target_git))

    def test_resolve_git_dir_missing_malformed_and_nonexistent(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Missing .git
            self.assertIsNone(resolve_git_dir(tmp_dir))

            # Malformed .git file (no gitdir: prefix)
            git_file = os.path.join(tmp_dir, ".git")
            with open(git_file, "w", encoding="utf-8") as f:
                f.write("not a valid git pointer\n")
            self.assertIsNone(resolve_git_dir(tmp_dir))

            # Empty .git file
            with open(git_file, "w", encoding="utf-8") as f:
                f.write("\n\n")
            self.assertIsNone(resolve_git_dir(tmp_dir))

            # gitdir: pointing at non-existent directory
            with open(git_file, "w", encoding="utf-8") as f:
                f.write("gitdir: /non/existent/path/for/sure\n")
            self.assertIsNone(resolve_git_dir(tmp_dir))

    def test_resolve_common_dir_none(self):
        self.assertIsNone(resolve_common_dir(None))

    def test_resolve_common_dir_absent(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            git_dir = os.path.join(tmp_dir, ".git")
            os.makedirs(git_dir)
            self.assertEqual(resolve_common_dir(git_dir), git_dir)

    def test_resolve_common_dir_relative(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            main_git = os.path.join(tmp_dir, "main", ".git")
            os.makedirs(main_git)
            wt_git = os.path.join(main_git, "worktrees", "wt1")
            os.makedirs(wt_git)

            commondir_file = os.path.join(wt_git, "commondir")
            with open(commondir_file, "w", encoding="utf-8") as f:
                f.write("../..\n")

            resolved = resolve_common_dir(wt_git)
            self.assertEqual(resolved, os.path.abspath(main_git))

    def test_resolve_common_dir_tilde_and_fallback(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_home = os.path.join(tmp_dir, "home")
            common_target = os.path.join(fake_home, "common_git")
            os.makedirs(common_target)

            git_dir = os.path.join(tmp_dir, "wt_git")
            os.makedirs(git_dir)
            commondir_file = os.path.join(git_dir, "commondir")

            # Tilde expansion when directory exists
            with open(commondir_file, "w", encoding="utf-8") as f:
                f.write("~/common_git\n")
            with mock.patch.dict(os.environ, {"HOME": fake_home}):
                self.assertEqual(resolve_common_dir(git_dir), os.path.abspath(common_target))

            # Non-existent target falls back to git_dir
            with open(commondir_file, "w", encoding="utf-8") as f:
                f.write("/non/existent/common_dir\n")
            self.assertEqual(resolve_common_dir(git_dir), git_dir)

    def test_read_core_hooks_path_none_and_missing(self):
        self.assertIsNone(read_core_hooks_path(None))
        with tempfile.TemporaryDirectory() as tmp_dir:
            self.assertIsNone(read_core_hooks_path(tmp_dir))

    def test_read_core_hooks_path_absent_key(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = os.path.join(tmp_dir, "config")
            with open(config_file, "w", encoding="utf-8") as f:
                f.write("[core]\n    bare = false\n[remote \"origin\"]\n    url = test\n")
            self.assertIsNone(read_core_hooks_path(tmp_dir))

    def test_read_core_hooks_path_variants(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = os.path.join(tmp_dir, "config")

            # hooksPath = value with comments
            with open(config_file, "w", encoding="utf-8") as f:
                f.write(
                    "# Comment at start\n"
                    "; Semi-colon comment\n"
                    "[Core]\n"
                    "    hooksPath = .githooks\n"
                )
            self.assertEqual(read_core_hooks_path(tmp_dir), ".githooks")

            # hookspath=value (lowercase, no spaces around =)
            with open(config_file, "w", encoding="utf-8") as f:
                f.write("[core]\n    hookspath=custom/hooks\n")
            self.assertEqual(read_core_hooks_path(tmp_dir), "custom/hooks")

            # Quoted value with whitespace
            with open(config_file, "w", encoding="utf-8") as f:
                f.write('[core]\n    hooksPath = "  my/hooks  "\n')
            self.assertEqual(read_core_hooks_path(tmp_dir), "my/hooks")

            # Valueless form
            with open(config_file, "w", encoding="utf-8") as f:
                f.write("[core]\n    hooksPath\n")
            self.assertEqual(read_core_hooks_path(tmp_dir), "")

            # Explicitly empty hooksPath =
            with open(config_file, "w", encoding="utf-8") as f:
                f.write("[core]\n    hooksPath =\n")
            self.assertEqual(read_core_hooks_path(tmp_dir), "")

            # Empty quotes hooksPath = ""
            with open(config_file, "w", encoding="utf-8") as f:
                f.write('[core]\n    hooksPath = ""\n')
            self.assertEqual(read_core_hooks_path(tmp_dir), "")

    def test_resolve_hooks_dir_missing_repo(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self.assertIsNone(resolve_hooks_dir(tmp_dir))

    def test_resolve_hooks_dir_default(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            git_dir = os.path.join(tmp_dir, ".git")
            os.makedirs(git_dir)
            expected = os.path.abspath(os.path.join(git_dir, "hooks"))
            self.assertEqual(resolve_hooks_dir(tmp_dir), expected)

    def test_resolve_hooks_dir_relative_hooks_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            git_dir = os.path.join(tmp_dir, ".git")
            os.makedirs(git_dir)
            config_file = os.path.join(git_dir, "config")
            with open(config_file, "w", encoding="utf-8") as f:
                f.write("[core]\n    hooksPath = .githooks\n")

            expected = os.path.abspath(os.path.join(tmp_dir, ".githooks"))
            self.assertEqual(resolve_hooks_dir(tmp_dir), expected)

    def test_resolve_hooks_dir_absolute_hooks_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            git_dir = os.path.join(tmp_dir, ".git")
            os.makedirs(git_dir)
            abs_hooks = os.path.abspath(os.path.join(tmp_dir, "custom_hooks"))
            config_file = os.path.join(git_dir, "config")
            with open(config_file, "w", encoding="utf-8") as f:
                f.write(f"[core]\n    hooksPath = {abs_hooks}\n")

            self.assertEqual(resolve_hooks_dir(tmp_dir), abs_hooks)

    def test_resolve_hooks_dir_tilde_hooks_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_home = os.path.join(tmp_dir, "home")
            git_dir = os.path.join(tmp_dir, ".git")
            os.makedirs(git_dir)
            config_file = os.path.join(git_dir, "config")
            with open(config_file, "w", encoding="utf-8") as f:
                f.write("[core]\n    hooksPath = ~/global_hooks\n")

            with mock.patch.dict(os.environ, {"HOME": fake_home}):
                expected = os.path.abspath(os.path.join(fake_home, "global_hooks"))
                self.assertEqual(resolve_hooks_dir(tmp_dir), expected)

    def test_resolve_hooks_dir_explicitly_empty(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            git_dir = os.path.join(tmp_dir, ".git")
            os.makedirs(git_dir)
            config_file = os.path.join(git_dir, "config")
            with open(config_file, "w", encoding="utf-8") as f:
                f.write("[core]\n    hooksPath =\n")

            self.assertIsNone(resolve_hooks_dir(tmp_dir))

    def test_resolve_hooks_dir_linked_worktree(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            main_git = os.path.join(tmp_dir, "repo", ".git")
            os.makedirs(main_git)
            wt_git = os.path.join(main_git, "worktrees", "wt1")
            os.makedirs(wt_git)

            # Common dir config specifies hooksPath
            config_file = os.path.join(main_git, "config")
            with open(config_file, "w", encoding="utf-8") as f:
                f.write("[core]\n    hooksPath = .shared-hooks\n")

            wt_dir = os.path.join(tmp_dir, "wt_working_copy")
            os.makedirs(wt_dir)
            with open(os.path.join(wt_dir, ".git"), "w", encoding="utf-8") as f:
                f.write(f"gitdir: {wt_git}\n")
            with open(os.path.join(wt_git, "commondir"), "w", encoding="utf-8") as f:
                f.write("../..\n")

            expected = os.path.abspath(os.path.join(wt_dir, ".shared-hooks"))
            self.assertEqual(resolve_hooks_dir(wt_dir), expected)

    def test_has_ai_invocation_cases(self):
        # Blank line
        self.assertEqual(has_ai_invocation("   \n"), [])
        self.assertEqual(has_ai_invocation(""), [])

        # Comment line
        self.assertEqual(has_ai_invocation("# gga run --provider opencode"), [])
        self.assertEqual(has_ai_invocation("   # claude review"), [])

        # Clean command
        self.assertEqual(has_ai_invocation("pytest tests/"), [])

        # Only the command word counts: ``--provider opencode`` is an argument.
        self.assertEqual(has_ai_invocation("gga run --provider opencode"), ["gga"])
        self.assertEqual(has_ai_invocation("npm test && claude review"), ["claude"])

        # Case-insensitivity
        self.assertEqual(has_ai_invocation("OpenCode audit"), ["opencode"])
        self.assertEqual(has_ai_invocation("CLAUDE check"), ["claude"])

        # Preserves AI_HOOK_KEYWORDS order regardless of appearance in line
        self.assertEqual(
            has_ai_invocation("ollama serve && gemini audit && gentle-ai run"),
            ["gentle-ai", "gemini", "ollama"],
        )

        # False positives avoidance: variables and path exports
        self.assertEqual(has_ai_invocation("export PATH=$HOME/.claude/bin:$PATH"), [])
        self.assertEqual(has_ai_invocation("gemini_count=12"), [])
        self.assertEqual(has_ai_invocation("echo opencode.json"), [])

        # Subcommand invocation with operators
        self.assertEqual(has_ai_invocation("npm test && claude review"), ["claude"])

        # Quoted arguments are not invocations
        self.assertEqual(has_ai_invocation('git commit -m "chore: claude review"'), [])
        self.assertEqual(has_ai_invocation('echo "npm && claude review"'), [])


class TestFindAiInvocations(unittest.TestCase):
    """Positional spans are what allows surgical, syntax-safe neutralization."""

    def test_reports_only_the_offending_subcommand_span(self):
        line = "npm test && claude review\n"
        invocations = find_ai_invocations(line)
        self.assertEqual(len(invocations), 1)
        start, end, keywords = invocations[0]
        self.assertEqual(line[start:end].strip(), "claude review")
        self.assertIn("claude", keywords)

    def test_semicolon_and_or_spans(self):
        semicolon = find_ai_invocations("make check ; gga audit\n")
        self.assertEqual(len(semicolon), 1)
        self.assertEqual("make check ; gga audit\n"[semicolon[0][0]:semicolon[0][1]].strip(), "gga audit")

        fallback = find_ai_invocations("claude review || exit 1\n")
        self.assertEqual(len(fallback), 1)
        self.assertEqual("claude review || exit 1\n"[fallback[0][0]:fallback[0][1]].strip(), "claude review")

    def test_subshell_span_excludes_delimiters(self):
        line = "echo $(claude review)\n"
        invocations = find_ai_invocations(line)
        self.assertEqual(len(invocations), 1)
        self.assertEqual(line[invocations[0][0]:invocations[0][1]].strip(), "claude review")

    def test_no_spans_for_clean_lines(self):
        self.assertEqual(find_ai_invocations("ruff check .\n"), [])
        self.assertEqual(find_ai_invocations("#!/bin/sh\n"), [])
        self.assertEqual(find_ai_invocations(""), [])


class TestRewriteLineNeutralizingAI(unittest.TestCase):
    """Neutralization must keep the surrounding shell syntax executable."""

    def test_and_operator_preserves_preceding_command(self):
        line, count = rewrite_line_neutralizing_ai("npm test && claude review\n")
        self.assertEqual(count, 1)
        self.assertEqual(line, "npm test && true  # [token-diet disabled: claude review]\n")
        self.assertEqual(has_ai_invocation(line), [])

    def test_semicolon_separated_commands(self):
        line, count = rewrite_line_neutralizing_ai("make check ; gga audit\n")
        self.assertEqual(count, 1)
        self.assertEqual(line, "make check ; true  # [token-diet disabled: gga audit]\n")
        self.assertEqual(has_ai_invocation(line), [])

    def test_or_operator_keeps_fallback_branch(self):
        line, count = rewrite_line_neutralizing_ai("claude review || exit 1\n")
        self.assertEqual(count, 1)
        self.assertEqual(line, "true || exit 1  # [token-diet disabled: claude review]\n")

    def test_command_substitution_keeps_closing_paren(self):
        line, count = rewrite_line_neutralizing_ai("echo $(claude review)\n")
        self.assertEqual(count, 1)
        self.assertIn("$(true)", line)
        self.assertIn(")", line)
        # A trailing comment must never swallow the closing paren of the substitution.
        self.assertNotIn("$(true #", line)

    def test_subshell_keeps_delimiters(self):
        line, count = rewrite_line_neutralizing_ai("ruff check . && (claude review)\n")
        self.assertEqual(count, 1)
        self.assertIn("ruff check . && (true)", line)

    def test_pipeline_preserves_neighbouring_stages(self):
        line, count = rewrite_line_neutralizing_ai("gga audit | tee report.log\n")
        self.assertEqual(count, 1)
        self.assertIn("true | tee report.log", line)

    def test_line_that_is_only_ai_invocation_is_commented(self):
        line, count = rewrite_line_neutralizing_ai("gga run --provider opencode\n")
        self.assertEqual(count, 1)
        self.assertEqual(line, "# [token-diet disabled]: gga run --provider opencode\n")
        self.assertEqual(has_ai_invocation(line), [])

    def test_multiple_invocations_on_one_line(self):
        line, count = rewrite_line_neutralizing_ai("gga run && claude review\n")
        self.assertEqual(count, 2)
        self.assertIn("true && true", line)
        self.assertIn("gga run; claude review", line)

    def test_shell_control_keywords_are_preserved(self):
        line, count = rewrite_line_neutralizing_ai("if [ -f x ]; then claude review; fi\n")
        self.assertEqual(count, 1)
        self.assertEqual(
            line, "if [ -f x ]; then true; fi  # [token-diet disabled: claude review]\n"
        )

    def test_path_qualified_binary_keeps_its_path(self):
        line, count = rewrite_line_neutralizing_ai("/usr/bin/claude review --all\n")
        self.assertEqual(count, 1)
        self.assertIn("/usr/bin/true", line)

    def test_line_continuation_avoids_trailing_comment(self):
        line, count = rewrite_line_neutralizing_ai("npm test && claude review \\\n")
        self.assertEqual(count, 1)
        self.assertIn("npm test && true", line)
        self.assertTrue(line.rstrip("\n").endswith("\\"))
        self.assertNotIn("# [token-diet disabled", line)

    def test_non_ai_lines_are_untouched(self):
        for case in (
            "",
            "\n",
            "pytest tests/\n",
            "# claude review\n",
            "echo opencode.json\n",
            "export PATH=$HOME/.claude/bin:$PATH\n",
            "gemini_count=12\n",
            'git commit -m "chore: claude review"\n',
        ):
            self.assertEqual(rewrite_line_neutralizing_ai(case), (case, 0))

    def test_rewrite_is_idempotent(self):
        once, first_count = rewrite_line_neutralizing_ai("npm test && claude review\n")
        twice, second_count = rewrite_line_neutralizing_ai(once)
        self.assertEqual(first_count, 1)
        self.assertEqual(second_count, 0)
        self.assertEqual(twice, once)

    def test_preserves_crlf_line_endings(self):
        line, count = rewrite_line_neutralizing_ai("npm test && claude review\r\n")
        self.assertEqual(count, 1)
        self.assertTrue(line.endswith("\r\n"))


class TestCommandPositionDetection(unittest.TestCase):
    """A keyword only counts where a shell would actually run it: command position."""

    def test_keyword_as_plain_argument_is_not_an_invocation(self):
        # A1 finding 1: matching anywhere in the subcommand flagged read-only
        # greps, and --fix-hooks then corrupted them into "grep -r true".
        self.assertEqual(has_ai_invocation("grep -r claude docs"), [])
        self.assertEqual(find_ai_invocations("grep -r claude docs\n"), [])
        for line in ("grep -r claude docs\n", "rg claude-review notes/\n"):
            self.assertEqual(rewrite_line_neutralizing_ai(line), (line, 0))

    def test_argv0_keyword_is_still_flagged_and_neutralized(self):
        self.assertEqual(has_ai_invocation("claude review"), ["claude"])
        line, count = rewrite_line_neutralizing_ai("claude review\n")
        self.assertEqual(count, 1)
        self.assertEqual(line, "# [token-diet disabled]: claude review\n")
        self.assertEqual(has_ai_invocation(line), [])

    def test_wrapper_commands_are_looked_through(self):
        self.assertEqual(has_ai_invocation("sudo claude review"), ["claude"])
        self.assertEqual(has_ai_invocation("xargs claude"), ["claude"])
        self.assertEqual(has_ai_invocation("command exec claude review"), ["claude"])
        self.assertEqual(has_ai_invocation("env GGA_TOKEN=1 claude review"), ["claude"])
        self.assertEqual(has_ai_invocation("nice -n 10 claude review"), ["claude"])
        line, count = rewrite_line_neutralizing_ai("sudo claude review\n")
        self.assertEqual(count, 1)
        self.assertEqual(line, "sudo true  # [token-diet disabled: claude review]\n")

    def test_env_assignment_prefixes_are_stripped(self):
        # A1 finding 2: subcommands whose first token held "=" were skipped whole.
        self.assertEqual(has_ai_invocation("FOO=1 claude review"), ["claude"])
        self.assertEqual(has_ai_invocation("FOO=1 BAR=2 gga audit"), ["gga"])
        self.assertEqual(has_ai_invocation("FOO=1"), [])
        self.assertEqual(has_ai_invocation("FOO=1 grep -r claude docs"), [])
        line, count = rewrite_line_neutralizing_ai("FOO=1 claude review\n")
        self.assertEqual(count, 1)
        self.assertEqual(line, "FOO=1 true  # [token-diet disabled: claude review]\n")

    def test_added_keywords_match_at_command_position_only(self):
        # A1/docs: documented targets that were never detected.
        self.assertEqual(has_ai_invocation("codex exec --full-auto"), ["codex"])
        self.assertEqual(has_ai_invocation("aider --yes"), ["aider"])
        self.assertEqual(has_ai_invocation("cody chat hello"), ["cody"])
        self.assertEqual(has_ai_invocation("grep -r codex docs"), [])
        self.assertEqual(has_ai_invocation('git commit -m "codex review"'), [])

    def test_llm_binary_match_keeps_the_llm_review_phrase(self):
        self.assertEqual(has_ai_invocation("llm review"), ["llm review"])
        self.assertEqual(has_ai_invocation("llm chat"), ["llm"])
        self.assertEqual(has_ai_invocation("grep -r 'llm review' docs"), [])


if __name__ == "__main__":
    unittest.main()
