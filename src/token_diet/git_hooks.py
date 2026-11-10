"""
git_hooks.py

Git worktree and core.hooksPath resolution layer for token-diet.
Provides robust resolution of git directories, common directories,
hooks paths, and detection of unmonitored AI review tool invocations.
"""

import os
import re
from typing import List, Optional, Tuple

AI_HOOK_KEYWORDS = ["gga", "opencode", "gentle-ai", "claude", "gemini", "ollama", "llm review"]

# Shell control operators that delimit independent subcommands on a single line.
# Command substitutions (``$(``), subshells (``(``/``)``), backticks, list
# separators (``;``, ``&&``, ``||``, ``;;``) and pipes all start a new command.
_SEPARATOR_RE = re.compile(r"&&|\|\||\$\(|;;|[;|&()`]")

# Bounded keyword patterns: reject matches glued to an identifier/hyphen before,
# and to a word/path/extension character after (so ``./claude`` counts while
# ``.json`` and ``.py`` suffixes do not).
_AI_KEYWORD_PATTERNS = {
    kw: re.compile(r"(?<![\w\-])" + re.escape(kw) + r"(?![\w\-\.\/])")
    for kw in AI_HOOK_KEYWORDS
}

_DISABLED_PREFIX = "# [token-diet disabled]"
_DISABLED_INLINE_MARKER = "# [token-diet disabled: {commands}]"


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


def _strip_inline_comment(line: str) -> str:
    """Strips unquoted shell comments (#) from a line."""
    in_single = False
    in_double = False
    escaped = False
    for i, ch in enumerate(line):
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            continue
        if ch == "#" and not in_single and not in_double:
            if i == 0 or line[i - 1].isspace() or line[i - 1] in ";|&":
                return line[:i]
    return line


def _quoted_mask(line: str) -> List[bool]:
    """Returns a per-character mask marking positions inside quotes or escaped."""
    mask = [False] * len(line)
    in_single = False
    in_double = False
    escaped = False
    for i, ch in enumerate(line):
        if escaped:
            mask[i] = True
            escaped = False
            continue
        if ch == "\\" and not in_single:
            mask[i] = True
            escaped = True
            continue
        if ch == "'" and not in_double:
            mask[i] = True
            in_single = not in_single
            continue
        if ch == '"' and not in_single:
            mask[i] = True
            in_double = not in_double
            continue
        if in_single or in_double:
            mask[i] = True
    return mask


def _subcommand_spans(line: str) -> List[Tuple[int, int]]:
    """Splits a shell line into (start, end) subcommand spans, ignoring quoted operators."""
    if not line:
        return [(0, 0)]

    quoted = _quoted_mask(line)
    spans: List[Tuple[int, int]] = []
    start = 0
    for match in _SEPARATOR_RE.finditer(line):
        if any(quoted[match.start():match.end()]):
            continue
        spans.append((start, match.start()))
        start = match.end()
    spans.append((start, len(line)))
    return spans


def _should_skip_subcommand(subcmd: str) -> bool:
    """Returns True for subcommands that never execute AI tooling (echo, assignments)."""
    tokens = subcmd.split()
    if not tokens:
        return True
    first_token = tokens[0].lower()
    if first_token in ("echo", "printf"):
        return True
    # Skip pure variable assignments like FOO=12 or export PATH=...
    if "=" in first_token and not (first_token.startswith("exec") or first_token.startswith("env")):
        return True
    if first_token == "export" and len(tokens) > 1 and "=" in tokens[1]:
        return True
    return False


def _subcommand_keyword_matches(subcmd: str) -> List[str]:
    """Returns AI keywords invoked inside a single subcommand, in AI_HOOK_KEYWORDS order."""
    lower_subcmd = subcmd.lower()
    return [kw for kw in AI_HOOK_KEYWORDS if _AI_KEYWORD_PATTERNS[kw].search(lower_subcmd)]


def _first_keyword_offset(subcmd: str, keywords: List[str]) -> int:
    """Returns the offset of the earliest AI keyword match within a subcommand, or -1."""
    lower_subcmd = subcmd.lower()
    best = -1
    for kw in keywords:
        match = _AI_KEYWORD_PATTERNS[kw].search(lower_subcmd)
        if match and (best == -1 or match.start() < best):
            best = match.start()
    return best


def find_ai_invocations(line: str) -> List[Tuple[int, int, List[str]]]:
    """
    Locates AI tooling invocations inside a shell line.

    Returns a list of ``(start, end, keywords)`` tuples where ``start``/``end``
    delimit the offending subcommand span within ``line`` and ``keywords`` are
    the matched AI hook keywords. Quoted mentions are not treated as invocations.
    """
    exec_part = _strip_inline_comment(line)
    if not exec_part.strip():
        return []

    quoted = _quoted_mask(exec_part)
    invocations: List[Tuple[int, int, List[str]]] = []

    for seg_start, seg_end in _subcommand_spans(exec_part):
        subcmd = exec_part[seg_start:seg_end]
        if not subcmd.strip() or _should_skip_subcommand(subcmd):
            continue

        keywords = _subcommand_keyword_matches(subcmd)
        if not keywords:
            continue

        offset = _first_keyword_offset(subcmd, keywords)
        if offset < 0:
            continue

        abs_start = seg_start + offset
        if quoted[abs_start]:
            # Quoted argument text (e.g. a commit message), not an invocation.
            continue

        invocations.append((abs_start, seg_end, keywords))

    return invocations


def has_ai_invocation(line: str) -> List[str]:
    """Inspects a script line for invocations of AI review tools, returning matched keywords."""
    matched = set()
    for _, _, keywords in find_ai_invocations(line):
        matched.update(keywords)
    return [kw for kw in AI_HOOK_KEYWORDS if kw in matched]


def rewrite_line_neutralizing_ai(line: str) -> Tuple[str, int]:
    """
    Neutralizes AI tooling invocations on a shell line while preserving syntax.

    1. A line whose whole statement is the AI invocation becomes a full-line
       comment: ``# [token-diet disabled]: gga run``.
    2. On compound lines only the offending subcommand is replaced with ``true``
       and the disabled command is recorded in a trailing comment:
       ``npm test && true  # [token-diet disabled: claude review]``.
    3. Every other part of the line (linters, tests, control operators,
       subshell delimiters, redirections) is preserved verbatim.

    Returns a ``(new_line, neutralized_count)`` tuple. The original line is
    returned unchanged when no AI invocation is found.
    """
    exec_part = _strip_inline_comment(line)
    remainder = line[len(exec_part):]
    invocations = find_ai_invocations(line)
    if not invocations:
        return line, 0

    newline = ""
    if line.endswith("\r\n"):
        newline = "\r\n"
    elif line.endswith("\n"):
        newline = "\n"

    spans = _subcommand_spans(exec_part)
    has_separators = len([s for s in spans if exec_part[s[0]:s[1]].strip()]) > 1
    leading_offset = len(exec_part) - len(exec_part.lstrip())

    if len(invocations) == 1 and not has_separators and invocations[0][0] == leading_offset:
        # The line is nothing but the AI invocation: comment it out wholesale.
        return f"{_DISABLED_PREFIX}: {line.strip()}{newline}", 1

    # A trailing backslash continues the statement on the next line, so the
    # replacement must stop before it and cannot carry a trailing comment.
    stripped_exec = exec_part.rstrip()
    continuation = stripped_exec.endswith("\\")
    span_boundary = len(stripped_exec) - 1 if continuation else len(exec_part)

    # Replace offending spans right-to-left so earlier offsets stay valid.
    rewritten = exec_part
    commands: List[str] = []
    for start, end, _ in reversed(invocations):
        command_text = exec_part[start:min(end, span_boundary)].rstrip()
        commands.append(" ".join(command_text.split()))
        rewritten = rewritten[:start] + "true" + rewritten[start + len(command_text):]
    commands.reverse()

    marker = _DISABLED_INLINE_MARKER.format(commands="; ".join(commands))
    trailing = remainder.strip()

    if continuation:
        result = rewritten
    else:
        result = f"{rewritten.rstrip()}  {marker}"
        if trailing:
            result = f"{result}  {trailing}"

    return f"{result}{newline}", len(commands)

