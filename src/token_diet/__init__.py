"""
token-diet: Diagnostic tools and methodology to audit and optimize token footprint in AI coding workflows.
"""

from token_diet.cli import (
    estimate_tokens,
    audit_file,
    detect_local_prompts,
    audit_git_hooks,
    fix_git_hooks,
    classify_size,
    resolve_target_paths,
    audit_known_prompts,
    summarize_footprint,
    main,
    DEFAULT_PROMPT_PATHS,
    LOCAL_PROMPT_CANDIDATES,
    THRESHOLD_WARN_BYTES,
    THRESHOLD_ALERT_BYTES,
)
from token_diet.baseline import (
    check_budget,
    compare_tokens,
    extract_total_tokens,
    load_baseline,
)
from token_diet.git_hooks import (
    AI_HOOK_KEYWORDS,
    has_ai_invocation,
    read_core_hooks_path,
    resolve_common_dir,
    resolve_git_dir,
    resolve_hooks_dir,
)
from token_diet.mcp_audit import (
    MCP_CONFIG_CANDIDATES,
    audit_mcp_config,
    audit_mcp_overhead,
    discover_mcp_configs,
)
from token_diet.sections import (
    audit_sections,
    audit_sections_for_paths,
    split_sections,
)

__version__ = "0.1.0"
__all__ = [
    "estimate_tokens",
    "audit_file",
    "detect_local_prompts",
    "audit_git_hooks",
    "fix_git_hooks",
    "classify_size",
    "resolve_target_paths",
    "audit_known_prompts",
    "summarize_footprint",
    "main",
    "DEFAULT_PROMPT_PATHS",
    "LOCAL_PROMPT_CANDIDATES",
    "THRESHOLD_WARN_BYTES",
    "THRESHOLD_ALERT_BYTES",
    "AI_HOOK_KEYWORDS",
    "has_ai_invocation",
    "read_core_hooks_path",
    "resolve_common_dir",
    "resolve_git_dir",
    "resolve_hooks_dir",
    "check_budget",
    "compare_tokens",
    "extract_total_tokens",
    "load_baseline",
    "MCP_CONFIG_CANDIDATES",
    "audit_mcp_config",
    "audit_mcp_overhead",
    "discover_mcp_configs",
    "audit_sections",
    "audit_sections_for_paths",
    "split_sections",
]
