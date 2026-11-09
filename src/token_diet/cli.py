#!/usr/bin/env python3
"""
cli.py

Core diagnostic logic to inspect, quantify, and audit token and byte footprint
of prompt directives, project files, and system configurations with automated alerts.
"""

import os
import sys
import json
import argparse
import math
import re
import stat
import tempfile
from typing import List, Dict, Any, Optional, Tuple

from .metrics import (
    THRESHOLD_ALERT_BYTES,
    THRESHOLD_WARN_BYTES,
    classify_size,
    estimate_tokens,
)
from .baseline import check_budget, compare_tokens, load_baseline
from .git_hooks import (
    AI_HOOK_KEYWORDS,
    has_ai_invocation,
    resolve_common_dir,
    resolve_git_dir,
    resolve_hooks_dir,
)
from .mcp_audit import audit_mcp_overhead
from .sections import audit_sections_for_paths

ANSI_OR_CONTROL_RE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_text(text: str) -> str:
    """Strips terminal escape sequences and non-printable control characters."""
    return ANSI_OR_CONTROL_RE.sub("", text)


def _validate_max_delta(value_str: str) -> float:
    """Validates that --max-delta argument is a finite float."""
    try:
        val = float(value_str)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid float value: '{value_str}'")
    if not math.isfinite(val) or math.isnan(val):
        raise argparse.ArgumentTypeError(f"--max-delta must be a finite percentage, got: '{value_str}'")
    return val



DEFAULT_PROMPT_PATHS = [
    os.path.expanduser("~/.codex/AGENTS.md"),
    os.path.expanduser("~/.codex/engram-instructions.md"),
    os.path.expanduser("~/.codex/engram-compact-prompt.md"),
    os.path.expanduser("~/.claude/CLAUDE.md"),
    os.path.expanduser("~/.gemini/GEMINI.md"),
    os.path.expanduser("~/.gemini/system.md"),
    os.path.expanduser("~/.config/opencode/AGENTS.md"),
]

LOCAL_PROMPT_CANDIDATES = [
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    ".cursorrules",
    ".windsurfrules",
    ".clinerules",
    ".github/copilot-instructions.md",
]

# Size thresholds in bytes
# THRESHOLD_WARN_BYTES and THRESHOLD_ALERT_BYTES are re-exported from .metrics


def supports_color() -> bool:
    """Returns True if the running terminal supports ANSI color codes."""
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return False
    return True


def colorize(text: str, color_code: str) -> str:
    """Applies ANSI color code if terminal supports color."""
    if not supports_color():
        return text
    return f"\033[{color_code}m{text}\033[0m"


def green(text: str) -> str:
    return colorize(text, "92")


def yellow(text: str) -> str:
    return colorize(text, "93")


def red(text: str) -> str:
    return colorize(text, "91")


def bold(text: str) -> str:
    return colorize(text, "1")


def audit_file(filepath: str) -> Dict[str, Any]:
    """Inspects a file and returns its size in bytes, estimated tokens, and health status."""
    if not os.path.exists(filepath):
        return {
            "path": filepath,
            "exists": False,
            "bytes": 0,
            "estimated_tokens": 0,
            "status": "MISSING",
            "severity": "none",
        }
    try:
        size = os.path.getsize(filepath)
        tokens = estimate_tokens(size)
        status, severity = classify_size(size)
        return {
            "path": filepath,
            "exists": True,
            "bytes": size,
            "estimated_tokens": tokens,
            "status": status,
            "severity": severity,
        }
    except Exception as e:
        return {
            "path": filepath,
            "exists": False,
            "error": str(e),
            "bytes": 0,
            "estimated_tokens": 0,
            "status": "ERROR",
            "severity": "critical",
        }


def detect_local_prompts(base_dir: str = ".") -> List[str]:
    """Detects standard AI agent directive files in the given directory."""
    found: List[str] = []
    abs_base = os.path.abspath(base_dir)

    for candidate in LOCAL_PROMPT_CANDIDATES:
        p = os.path.join(abs_base, candidate)
        if os.path.isfile(p):
            found.append(p)

    # Check .cursor/rules directory if it exists
    cursor_rules_dir = os.path.join(abs_base, ".cursor", "rules")
    if os.path.isdir(cursor_rules_dir):
        for root, _, files in os.walk(cursor_rules_dir):
            for f in sorted(files):
                if f.endswith((".md", ".mdc", ".txt")):
                    found.append(os.path.join(root, f))

    return found


def audit_git_hooks(repo_dir: str = ".") -> List[Dict[str, Any]]:
    """
    Inspects the active pre-commit hook for automated scripts that may silently
    trigger LLM calls. Resolves `.git` gitdir files (linked worktrees, submodules)
    and honors the repository `core.hooksPath` setting.
    """
    alerts: List[Dict[str, Any]] = []
    hooks_dir = resolve_hooks_dir(repo_dir)
    if hooks_dir is None:
        return alerts

    hook_path = os.path.join(hooks_dir, "pre-commit")
    if not os.path.isfile(hook_path):
        return alerts

    try:
        matched = []
        with open(hook_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                for keyword in has_ai_invocation(line):
                    if keyword not in matched:
                        matched.append(keyword)

        if matched:
            alerts.append({
                "hook": "pre-commit",
                "path": hook_path,
                "severity": "critical",
                "matched_patterns": matched,
                "message": (
                    f"Pre-commit hook invokes AI/LLM review tooling ({', '.join(matched)}). "
                    "This causes invisible token consumption on every commit."
                ),
            })
    except Exception as e:
        alerts.append({
            "hook": "pre-commit",
            "path": hook_path,
            "severity": "warning",
            "error": str(e),
            "message": f"Could not inspect pre-commit hook: {e}",
        })

    return alerts


def fix_git_hooks(repo_dir: str = ".") -> Dict[str, Any]:
    """
    Safely neutralizes unmonitored AI/LLM invocations in the active pre-commit hook:
    1. Creates a backup copy at <hook>.bak.
    2. Comments out lines that invoke matched AI review keywords.
    3. Preserves original executable file permissions.
    """
    hooks_dir = resolve_hooks_dir(repo_dir)
    if hooks_dir is None:
        return {
            "fixed": False,
            "hook_path": None,
            "backup_path": None,
            "disabled_count": 0,
            "message": "No Git hooks directory detected for this repository.",
        }

    # Ensure hooks directory is contained within the repository or git directory
    repo_real = os.path.realpath(os.path.abspath(repo_dir))
    git_dir = resolve_git_dir(repo_dir)
    git_real = os.path.realpath(git_dir) if git_dir else None
    common_dir = resolve_common_dir(git_dir) if git_dir else None
    common_real = os.path.realpath(common_dir) if common_dir else None

    hooks_real = os.path.realpath(os.path.abspath(hooks_dir))
    is_contained = (
        hooks_real == repo_real
        or hooks_real.startswith(repo_real + os.sep)
        or (git_real and (hooks_real == git_real or hooks_real.startswith(git_real + os.sep)))
        or (common_real and (hooks_real == common_real or hooks_real.startswith(common_real + os.sep)))
    )
    if not is_contained:
        return {
            "fixed": False,
            "hook_path": os.path.join(hooks_dir, "pre-commit"),
            "backup_path": None,
            "disabled_count": 0,
            "error": "Hooks directory outside repository boundary",
            "message": f"Refusing to modify hooks outside repository boundary: {hooks_real}",
        }

    hook_path = os.path.join(hooks_dir, "pre-commit")
    if os.path.islink(hook_path):
        return {
            "fixed": False,
            "hook_path": hook_path,
            "backup_path": None,
            "disabled_count": 0,
            "error": "Refusing to modify hook through symlink",
            "message": f"Pre-commit hook is a symlink: {hook_path}. Refusing to modify target through symlink.",
        }

    if not os.path.isfile(hook_path):
        return {
            "fixed": False,
            "hook_path": hook_path,
            "backup_path": None,
            "disabled_count": 0,
            "message": "No pre-commit hook found in the active hooks directory.",
        }

    try:
        orig_stat = os.lstat(hook_path)

        if not stat.S_ISREG(orig_stat.st_mode):
            return {
                "fixed": False,
                "hook_path": hook_path,
                "backup_path": None,
                "disabled_count": 0,
                "error": "Not a regular file",
                "message": f"Pre-commit hook is not a regular file: {hook_path}",
            }

        MAX_SAFE_BYTES = 10 * 1024 * 1024  # 10 MB
        if orig_stat.st_size > MAX_SAFE_BYTES:
            return {
                "fixed": False,
                "hook_path": hook_path,
                "backup_path": None,
                "disabled_count": 0,
                "error": "File exceeds maximum size limit",
                "message": f"Pre-commit hook exceeds 10MB limit ({orig_stat.st_size} bytes): {hook_path}",
            }

        with open(hook_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        modified_lines = []
        disabled_count = 0
        for line in lines:
            stripped = line.strip()
            # Preserve already-commented lines
            if stripped.startswith("#"):
                modified_lines.append(line)
                continue

            if has_ai_invocation(line):
                modified_lines.append(f"# [token-diet disabled]: {line}")
                disabled_count += 1
            else:
                modified_lines.append(line)

        if disabled_count == 0:
            return {
                "fixed": False,
                "hook_path": hook_path,
                "backup_path": None,
                "disabled_count": 0,
                "message": f"No irregular AI hooks detected to disable in {hook_path}",
            }

        backup_path = hook_path + ".bak"
        if os.path.islink(backup_path):
            return {
                "fixed": False,
                "hook_path": hook_path,
                "backup_path": None,
                "disabled_count": 0,
                "error": "Symlink detected at backup path",
                "message": f"Backup target is a symlink: {backup_path}. Refusing to write backup.",
            }

        # Write backup safely (create or overwrite regular file safely with mode 0o600 or orig_stat)
        backup_flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
        backup_fd = os.open(backup_path, backup_flags, 0o600)
        with os.fdopen(backup_fd, "w", encoding="utf-8") as f:
            f.writelines(lines)

        # Atomic replacement for hook_path
        hooks_dir = os.path.dirname(hook_path)
        with tempfile.NamedTemporaryFile("w", dir=hooks_dir, delete=False, encoding="utf-8") as tmp:
            tmp.writelines(modified_lines)
            temp_name = tmp.name

        try:
            os.chmod(temp_name, orig_stat.st_mode)
            # Verify original inode didn't switch to a symlink right before rename
            current_stat = os.lstat(hook_path)
            if os.path.islink(hook_path) or current_stat.st_ino != orig_stat.st_ino:
                os.remove(temp_name)
                return {
                    "fixed": False,
                    "hook_path": hook_path,
                    "backup_path": backup_path,
                    "disabled_count": 0,
                    "error": "TOCTOU race detected",
                    "message": "File status changed during remediation; aborting replacement.",
                }
            os.replace(temp_name, hook_path)
        except Exception:
            if os.path.exists(temp_name):
                os.remove(temp_name)
            raise

        return {
            "fixed": True,
            "hook_path": hook_path,
            "backup_path": backup_path,
            "disabled_count": disabled_count,
            "message": f"Successfully neutralized {disabled_count} AI invocation(s). Backup saved to {backup_path}",
        }
    except Exception as e:
        return {
            "fixed": False,
            "hook_path": hook_path,
            "backup_path": None,
            "disabled_count": 0,
            "error": str(e),
            "message": f"Failed to fix pre-commit hook: {e}",
        }


def resolve_target_paths(input_paths: Optional[List[str]] = None, check_local: bool = True) -> List[str]:
    """Resolves file paths, expanding directories recursively or defaulting to local/global prompts."""
    if input_paths:
        resolved: List[str] = []
        for p in input_paths:
            expanded = os.path.abspath(os.path.expanduser(p))
            if os.path.isdir(expanded):
                for root, _, files in os.walk(expanded):
                    for f in sorted(files):
                        if not f.startswith("."):
                            resolved.append(os.path.join(root, f))
            else:
                resolved.append(expanded)
        return resolved

    if check_local:
        return detect_local_prompts(".")

    return DEFAULT_PROMPT_PATHS


def audit_known_prompts(custom_paths: Optional[List[str]] = None, check_local: bool = True) -> List[Dict[str, Any]]:
    """Audits target paths and returns itemized results."""
    paths = resolve_target_paths(custom_paths, check_local=check_local)
    return [audit_file(p) for p in paths]


def summarize_footprint(results: List[Dict[str, Any]], hook_alerts: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Calculates aggregate footprint summary, status totals, and health indicators."""
    total_bytes = sum(r.get("bytes", 0) for r in results)
    total_tokens = sum(r.get("estimated_tokens", 0) for r in results)
    files_found = sum(1 for r in results if r.get("exists"))
    alert_count = sum(1 for r in results if r.get("status") == "ALERT")
    warn_count = sum(1 for r in results if r.get("status") == "WARN")

    if hook_alerts:
        alert_count += len([h for h in hook_alerts if h.get("severity") == "critical"])

    overall_status = "HEALTHY"
    if alert_count > 0:
        overall_status = "CRITICAL_BLOAT"
    elif warn_count > 0:
        overall_status = "WARNING_MODERATE"

    return {
        "total_bytes": total_bytes,
        "total_tokens": total_tokens,
        "files_found": files_found,
        "total_checked": len(results),
        "alerts": alert_count,
        "warnings": warn_count,
        "status": overall_status,
    }


def main():
    parser = argparse.ArgumentParser(
        prog="token-diet",
        description="Audit token footprint and detect silent context leaks in AI agent workflows.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Optional files or directories to inspect. Defaults to auto-detecting project files in CWD or global prompts.",
    )
    parser.add_argument(
        "--global",
        dest="global_only",
        action="store_true",
        help="Inspect global assistant prompts (~/.claude, ~/.codex, ~/.gemini) instead of local project files.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output structured JSON payload.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        metavar="N",
        help="Exit with code 1 if total estimated tokens exceed N (useful for CI/CD gates).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if any alert or warning threshold is exceeded.",
    )
    parser.add_argument(
        "--fix-hooks",
        action="store_true",
        help="Automatically neutralize unmonitored AI review invocations in the active pre-commit hook (worktree and core.hooksPath aware; creates a .bak backup).",
    )
    parser.add_argument(
        "--sections",
        action="store_true",
        help="Break down token and byte footprint per Markdown level-2 heading to locate prompt bloat.",
    )
    parser.add_argument(
        "--mcp",
        action="store_true",
        help="Audit MCP server payload overhead from local opencode.json, .mcp.json, or mcp.json configs.",
    )
    parser.add_argument(
        "--baseline",
        metavar="FILE",
        help="Compare total estimated tokens against a previously saved JSON report (e.g. 'token-diet --json > baseline.json').",
    )
    parser.add_argument(
        "--max-delta",
        type=_validate_max_delta,
        metavar="PERCENT",
        help="Exit with code 1 if total estimated tokens grow more than PERCENT over --baseline.",
    )

    args = parser.parse_args()

    if args.max_delta is not None and args.baseline is None:
        parser.error("--max-delta requires --baseline <file.json>")

    if args.fix_hooks:
        fix_result = fix_git_hooks(".")
        if args.json:
            print(json.dumps({"fix_hooks": fix_result}, indent=2))
        else:
            if fix_result["fixed"]:
                print(green(bold("🛠️  AUTO-REMEDIATION: PRE-COMMIT HOOKS NEUTRALIZED")))
                print(f"  • Backup saved: {fix_result['backup_path']}")
                print(f"  • Neutralized {fix_result['disabled_count']} AI review invocation(s).")
                print("  • Safe pre-commit hook is active without silent token bleed.")
            else:
                print(yellow(f"ℹ️  {fix_result['message']}"))
        return

    check_local = not args.global_only
    targets = args.paths if args.paths else None

    # Detect git hooks in current working directory
    hook_alerts = audit_git_hooks(".") if check_local and not targets else []

    target_paths = resolve_target_paths(targets, check_local=check_local)
    results = [audit_file(p) for p in target_paths]
    summary = summarize_footprint(results, hook_alerts)

    baseline_comparison: Optional[Dict[str, Any]] = None
    if args.baseline is not None:
        baseline = load_baseline(args.baseline)
        if not baseline["ok"]:
            parser.error(baseline["error"])
        if args.max_delta is not None:
            baseline_comparison = check_budget(
                summary["total_tokens"], baseline["tokens"], args.max_delta
            )
        else:
            baseline_comparison = compare_tokens(summary["total_tokens"], baseline["tokens"])

    section_report = sections_payload(target_paths) if args.sections else None
    mcp_report = audit_mcp_overhead(".") if args.mcp else None
    baseline_exceeded = bool(baseline_comparison and baseline_comparison.get("exceeded"))

    if args.json:
        payload = {
            "summary": summary,
            "hook_alerts": hook_alerts,
            "details": results,
        }
        if section_report is not None:
            payload["sections"] = section_report
        if mcp_report is not None:
            payload["mcp"] = mcp_report
        if baseline_comparison is not None:
            payload["baseline_comparison"] = baseline_comparison
        print(json.dumps(payload, indent=2))
        _check_exit_conditions(summary, args.max_tokens, args.strict, baseline_exceeded)
        return

    # Terminal Output
    print(bold("=" * 80))
    print(bold("TOKEN DIET: FOOTPRINT & CONTEXT AUDIT"))
    print(bold("=" * 80))
    print(f'{"File / Directive":<46} | {"Bytes":>9} | {"Tokens":>9} | {"Status":>8}')
    print("-" * 80)

    for r in results:
        status_path = sanitize_text(r["path"])
        if len(status_path) > 44:
            status_path = "..." + status_path[-41:]

        if not r["exists"]:
            status_str = colorize("(missing)", "90")
            print(f'{status_path:<46} | {"-":>9} | {"-":>9} | {status_str:>8}')
        else:
            status = r["status"]
            if status == "ALERT":
                badge = red("[ALERT]")
            elif status == "WARN":
                badge = yellow("[WARN]")
            else:
                badge = green("[OK]")

            print(f'{status_path:<46} | {r["bytes"]:>9,d} | {r["estimated_tokens"]:>9,d} | {badge:>17}')

    print(bold("=" * 80))
    print(f"Total Bytes:     {summary['total_bytes']:,d} B")
    print(f"Total Tokens:    ~{summary['total_tokens']:,d} estimated base tokens per turn")
    print(f"Files Detected:  {summary['files_found']} of {summary['total_checked']}")

    # Print Hook Alerts if any
    if hook_alerts:
        print("\n" + red(bold("🚨 IRREGULAR HOOK DETECTED:")))
        for h in hook_alerts:
            h_hook = sanitize_text(str(h.get("hook", "")))
            h_msg = sanitize_text(str(h.get("message", "")))
            h_path = sanitize_text(str(h.get("path", "")))
            print(red(f"  • [{h_hook}] {h_msg}"))
            print(f"    Path: {h_path}")
        print(colorize("  💡 Tip: Run 'token-diet --fix-hooks' to automatically neutralize silent AI invocations.", "96"))

    # Print Recommendations if bloated
    if summary["alerts"] > 0:
        print("\n" + red(bold("⚠️  CONTEXT BLOAT DETECTED:")))
        print("  Files marked [ALERT] exceed 16 KB (>4k tokens) and severely penalize context windows.")
        print("  Recommendation: Decouple procedures into On-Demand Skills using the LUT Router pattern.")
    elif summary["warnings"] > 0:
        print("\n" + yellow("ℹ️  MODERATE CONTEXT SIZE:"))
        print("  Files marked [WARN] exceed 4 KB. Review if non-essential sections can be pruned.")

    if section_report is not None:
        print()
        render_sections_report(section_report)

    if mcp_report is not None:
        print()
        render_mcp_report(mcp_report)

    if baseline_comparison is not None:
        print()
        render_baseline_report(baseline_comparison, args.max_delta)

    _check_exit_conditions(summary, args.max_tokens, args.strict, baseline_exceeded)


def status_badge(status: str) -> str:
    """Returns a colored [OK] / [WARN] / [ALERT] badge for a status label."""
    if status == "ALERT":
        return red("[ALERT]")
    if status == "WARN":
        return yellow("[WARN]")
    return green("[OK]")


def sections_payload(paths: List[str]) -> Dict[str, Any]:
    """Builds the `--sections` report payload, dropping internal section source text."""
    report = audit_sections_for_paths(paths)
    files: List[Dict[str, Any]] = []
    for entry in report["files"]:
        compact = {k: v for k, v in entry.items() if k != "sections"}
        compact["sections"] = [
            {k: v for k, v in section.items() if k != "text"}
            for section in entry.get("sections", [])
        ]
        files.append(compact)
    return {
        "files": files,
        "file_count": report["file_count"],
        "total_bytes": report["total_bytes"],
        "total_tokens": report["total_tokens"],
    }


def render_sections_report(report: Dict[str, Any]) -> None:
    """Prints the per-heading footprint breakdown."""
    print(bold("=" * 80))
    print(bold("SECTION BREAKDOWN: MARKDOWN HEADING FOOTPRINT"))
    print(bold("=" * 80))
    if report["file_count"] == 0:
        print(yellow("  No files matched for section analysis."))
        return

    for entry in report["files"]:
        entry_path = sanitize_text(entry["path"])
        if not entry["exists"]:
            print(colorize(f"{entry_path}: (missing)", "90"))
            continue
        print(bold(f"{entry_path}  ({entry['bytes']:,d} B / ~{entry['estimated_tokens']:,d} tokens)"))
        print(f'{"Line":>6} | {"Heading":<40} | {"Bytes":>9} | {"Tokens":>9} | {"Status":>8}')
        print("-" * 80)
        for section in entry["sections"]:
            heading = sanitize_text(section["heading"])
            if len(heading) > 38:
                heading = heading[:35] + "..."
            badge = status_badge(section["status"])
            print(
                f'{section["line"]:>6} | {heading:<40} | '
                f'{section["bytes"]:>9,d} | {section["estimated_tokens"]:>9,d} | {badge:>17}'
            )
        print("-" * 80)

    print(f"Total Sections:  {sum(len(e['sections']) for e in report['files'])}")
    print(f"Total Bytes:     {report['total_bytes']:,d} B")
    print(f"Total Tokens:    ~{report['total_tokens']:,d} estimated")


def render_mcp_report(report: Dict[str, Any]) -> None:
    """Prints the MCP server payload overhead breakdown."""
    print(bold("=" * 80))
    print(bold("MCP SERVER PAYLOAD AUDIT"))
    print(bold("=" * 80))
    if report["config_count"] == 0:
        print(yellow("  No MCP configuration found (opencode.json, .mcp.json, mcp.json)."))
        return

    for config in report["configs"]:
        config_path = sanitize_text(config["path"])
        if config.get("error"):
            config_err = sanitize_text(str(config["error"]))
            print(red(f"{config_path}: unreadable ({config_err})"))
            continue
        config_fmt = sanitize_text(str(config["format"]))
        print(bold(f"{config_path}  [{config_fmt}]  ({config['total_servers']} server(s))"))
        if not config["servers"]:
            print(colorize("  No MCP servers declared.", "90"))
            continue
        print(f'{"Server":<30} | {"Transport":<9} | {"Tools":>5} | {"Bytes":>9} | {"Tokens":>9} | {"Status":>8}')
        print("-" * 80)
        for server in config["servers"]:
            name = sanitize_text(server["name"])
            if len(name) > 28:
                name = name[:25] + "..."
            badge = status_badge(server["status"])

            print(
                f'{name:<30} | {server["transport"]:<9} | {server["tool_count"]:>5,d} | '
                f'{server["bytes"]:>9,d} | {server["estimated_tokens"]:>9,d} | {badge:>17}'
            )
        print("-" * 80)

    print(f"MCP Servers:     {report['total_servers']}")
    print(f"Total Bytes:     {report['total_bytes']:,d} B")
    print(f"Total Tokens:    ~{report['total_tokens']:,d} estimated")


def render_baseline_report(comparison: Dict[str, Any], max_delta: Optional[float]) -> None:
    """Prints the baseline delta and, when a budget is set, its verdict."""
    delta = comparison["delta_tokens"]
    sign = "+" if delta > 0 else ""
    print(bold("BASELINE COMPARISON:"))
    print(f"  Baseline: ~{comparison['baseline_tokens']:,d} tokens")
    print(f"  Current:  ~{comparison['current_tokens']:,d} tokens")
    if comparison.get("indeterminate"):
        print(f"  Delta:    {sign}{delta:,d} tokens (indeterminate from 0 baseline)")
    else:
        print(f"  Delta:    {sign}{delta:,d} tokens ({sign}{comparison['delta_percent']}%)")
    if max_delta is None:
        return
    if comparison["exceeded"]:
        if comparison.get("indeterminate"):
            print(red("  BUDGET EXCEEDED: new tokens introduced from a zero baseline."))
        else:
            print(red(f"  BUDGET EXCEEDED: growth above the allowed {max_delta}% delta."))
    else:
        print(green(f"  Within budget: growth is at most {max_delta}%."))


def _check_exit_conditions(
    summary: Dict[str, Any],
    max_tokens: Optional[int],
    strict: bool,
    baseline_exceeded: bool = False,
):
    """Handles exit codes for CI/CD gates."""
    # If gate enforcement flags are set (--strict, --max-tokens), require at least one directive measured
    if (strict or max_tokens is not None) and summary.get("files_found", 0) == 0:
        sys.stderr.write("Error: Token budget gate active (--strict or --max-tokens) but 0 prompt directives found.\n")
        sys.exit(1)

    if max_tokens is not None and summary["total_tokens"] > max_tokens:
        sys.exit(1)
    if strict and (summary["alerts"] > 0 or summary["warnings"] > 0):
        sys.exit(1)
    if baseline_exceeded:
        sys.exit(1)


if __name__ == "__main__":
    main()
