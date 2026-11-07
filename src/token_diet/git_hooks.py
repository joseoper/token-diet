"""
git_hooks.py

Git worktree and core.hooksPath resolution layer for token-diet.
Provides robust resolution of git directories, common directories,
hooks paths, and detection of unmonitored AI review tool invocations.
"""

import os
from typing import List, Optional

AI_HOOK_KEYWORDS = ["gga", "opencode", "gentle-ai", "claude", "gemini", "ollama", "llm review"]


def resolve_git_dir(repo_dir: str = ".") -> Optional[str]:
    """Resolves the git directory for a repository, handling directories and .git pointer files."""
    git_candidate = os.path.join(repo_dir, ".git")
    if not os.path.exists(git_candidate):
        return None

    if os.path.isdir(git_candidate):
        return os.path.abspath(git_candidate)

    if os.path.isfile(git_candidate):
        try:
            with open(git_candidate, "r", encoding="utf-8", errors="ignore") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line:
                        continue
                    if not line.startswith("gitdir:"):
                        return None
                    path_val = line[len("gitdir:"):].strip()
                    if not path_val:
                        return None
                    expanded = os.path.expanduser(path_val)
                    if not os.path.isabs(expanded):
                        expanded = os.path.join(repo_dir, expanded)
                    abs_path = os.path.abspath(os.path.normpath(expanded))
                    if os.path.isdir(abs_path):
                        return abs_path
                    return None
        except (OSError, IOError):
            return None

    return None


def resolve_common_dir(git_dir: Optional[str]) -> Optional[str]:
    """Resolves the git common directory, following commondir files in linked worktrees."""
    if git_dir is None:
        return None

    commondir_path = os.path.join(git_dir, "commondir")
    if not os.path.isfile(commondir_path):
        return git_dir

    try:
        with open(commondir_path, "r", encoding="utf-8", errors="ignore") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                expanded = os.path.expanduser(line)
                if not os.path.isabs(expanded):
                    expanded = os.path.join(git_dir, expanded)
                abs_path = os.path.abspath(os.path.normpath(expanded))
                if os.path.isdir(abs_path):
                    return abs_path
                return git_dir
    except (OSError, IOError):
        return git_dir

    return git_dir


def read_core_hooks_path(git_dir: Optional[str]) -> Optional[str]:
    """Reads core.hooksPath from git config in git_dir, tracking case-insensitive [core] sections."""
    if git_dir is None:
        return None

    config_path = os.path.join(git_dir, "config")
    if not os.path.isfile(config_path):
        return None

    result: Optional[str] = None
    in_core = False

    try:
        with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
            for raw_line in f:
                stripped = raw_line.strip()
                if not stripped:
                    continue
                if stripped.startswith("#") or stripped.startswith(";"):
                    continue

                if stripped.startswith("[") and stripped.endswith("]"):
                    section_name = stripped[1:-1].strip()
                    in_core = (section_name.lower() == "core")
                    continue

                if in_core:
                    if "=" in stripped:
                        key, _, val = stripped.partition("=")
                        if key.strip().lower() == "hookspath":
                            val = val.strip()
                            if len(val) >= 2 and val.startswith('"') and val.endswith('"'):
                                val = val[1:-1].strip()
                            result = val
                    else:
                        if stripped.strip().lower() == "hookspath":
                            result = ""
    except (OSError, IOError):
        return None

    return result


def resolve_hooks_dir(repo_dir: str = ".") -> Optional[str]:
    """Resolves the active hooks directory for a repository, respecting core.hooksPath and worktrees."""
    git_dir = resolve_git_dir(repo_dir)
    if git_dir is None:
        return None

    common_dir = resolve_common_dir(git_dir)
    if common_dir is None:
        return None

    hooks_path = read_core_hooks_path(common_dir)
    if hooks_path == "":
        return None

    if hooks_path is not None:
        expanded = os.path.expanduser(hooks_path)
        if not os.path.isabs(expanded):
            expanded = os.path.join(repo_dir, expanded)
        return os.path.abspath(os.path.normpath(expanded))

    return os.path.abspath(os.path.normpath(os.path.join(common_dir, "hooks")))


def has_ai_invocation(line: str) -> List[str]:
    """Inspects a script line for invocations of AI review tools, returning matched keywords."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return []
    lower = stripped.lower()
    return [kw for kw in AI_HOOK_KEYWORDS if kw in lower]
