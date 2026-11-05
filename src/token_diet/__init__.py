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
]
