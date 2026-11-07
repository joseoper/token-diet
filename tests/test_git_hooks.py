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
    has_ai_invocation,
    read_core_hooks_path,
    resolve_common_dir,
    resolve_git_dir,
    resolve_hooks_dir,
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

        # Multiple keywords in single line
        self.assertEqual(
            has_ai_invocation("gga run --provider opencode"),
            ["gga", "opencode"],
        )

        # Case-insensitivity
        self.assertEqual(has_ai_invocation("OpenCode audit"), ["opencode"])
        self.assertEqual(has_ai_invocation("CLAUDE check"), ["claude"])

        # Preserves AI_HOOK_KEYWORDS order regardless of appearance in line
        self.assertEqual(
            has_ai_invocation("ollama or gemini or gentle-ai"),
            ["gentle-ai", "gemini", "ollama"],
        )


if __name__ == "__main__":
    unittest.main()
