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
from typing import List, Dict, Any, Optional, Tuple

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
THRESHOLD_WARN_BYTES = 4_000   # ~1,000 tokens
THRESHOLD_ALERT_BYTES = 16_000 # ~4,000 tokens


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


def estimate_tokens(char_count: int) -> int:
    """Estimates tokens based on a conservative heuristic of ~4 characters per token."""
    if char_count <= 0:
        return 0
    return char_count // 4


def classify_size(size_bytes: int) -> Tuple[str, str]:
    """Returns (status_label, severity) based on byte size."""
    if size_bytes > THRESHOLD_ALERT_BYTES:
        return "ALERT", "critical"
    elif size_bytes > THRESHOLD_WARN_BYTES:
        return "WARN", "warning"
    return "OK", "optimal"


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
    """Inspects .git/hooks for automated scripts that may silently trigger LLM calls."""
    alerts: List[Dict[str, Any]] = []
    hook_path = os.path.join(os.path.abspath(repo_dir), ".git", "hooks", "pre-commit")

    if not os.path.exists(hook_path):
        return alerts

    try:
        keywords = ["gga", "opencode", "gentle-ai", "claude", "gemini", "ollama", "llm review"]
        matched = []
        with open(hook_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                lower_line = stripped.lower()
                for k in keywords:
                    if k in lower_line and k not in matched:
                        matched.append(k)

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
    Safely neutralizes unmonitored AI/LLM invocations in .git/hooks/pre-commit:
    1. Creates a backup copy at .git/hooks/pre-commit.bak.
    2. Comments out lines that invoke matched AI review keywords.
    3. Preserves original executable file permissions.
    """
    hook_path = os.path.join(os.path.abspath(repo_dir), ".git", "hooks", "pre-commit")
    if not os.path.exists(hook_path):
        return {
            "fixed": False,
            "hook_path": hook_path,
            "backup_path": None,
            "disabled_count": 0,
            "message": "No pre-commit hook found in .git/hooks/",
        }

    keywords = ["gga", "opencode", "gentle-ai", "claude", "gemini", "ollama", "llm review"]
    try:
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

            lower_line = line.lower()
            if any(k in lower_line for k in keywords):
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
                "message": "No irregular AI hooks detected to disable in .git/hooks/pre-commit",
            }

        backup_path = hook_path + ".bak"
        with open(backup_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        mode = os.stat(hook_path).st_mode
        with open(hook_path, "w", encoding="utf-8") as f:
            f.writelines(modified_lines)
        os.chmod(hook_path, mode)

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
        local_files = detect_local_prompts(".")
        if local_files:
            return local_files

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
        help="Automatically neutralize unmonitored AI review invocations in .git/hooks/pre-commit (creates .bak backup).",
    )
    args = parser.parse_args()

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

    results = audit_known_prompts(targets, check_local=check_local)
    summary = summarize_footprint(results, hook_alerts)

    if args.json:
        payload = {
            "summary": summary,
            "hook_alerts": hook_alerts,
            "details": results,
        }
        print(json.dumps(payload, indent=2))
        _check_exit_conditions(summary, args.max_tokens, args.strict)
        return

    # Terminal Output
    print(bold("=" * 80))
    print(bold("TOKEN DIET: FOOTPRINT & CONTEXT AUDIT"))
    print(bold("=" * 80))
    print(f'{"File / Directive":<46} | {"Bytes":>9} | {"Tokens":>9} | {"Status":>8}')
    print("-" * 80)

    for r in results:
        status_path = r["path"]
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
            print(red(f"  • [{h['hook']}] {h['message']}"))
            print(f"    Path: {h['path']}")
        print(colorize("  💡 Tip: Run 'token-diet --fix-hooks' to automatically neutralize silent AI invocations.", "96"))

    # Print Recommendations if bloated
    if summary["alerts"] > 0:
        print("\n" + red(bold("⚠️  CONTEXT BLOAT DETECTED:")))
        print("  Files marked [ALERT] exceed 16 KB (>4k tokens) and severely penalize context windows.")
        print("  Recommendation: Decouple procedures into On-Demand Skills using the LUT Router pattern.")
    elif summary["warnings"] > 0:
        print("\n" + yellow("ℹ️  MODERATE CONTEXT SIZE:"))
        print("  Files marked [WARN] exceed 4 KB. Review if non-essential sections can be pruned.")

    _check_exit_conditions(summary, args.max_tokens, args.strict)


def _check_exit_conditions(summary: Dict[str, Any], max_tokens: Optional[int], strict: bool):
    """Handles exit codes for CI/CD gates."""
    if max_tokens is not None and summary["total_tokens"] > max_tokens:
        sys.exit(1)
    if strict and (summary["alerts"] > 0 or summary["warnings"] > 0):
        sys.exit(1)


if __name__ == "__main__":
    main()
