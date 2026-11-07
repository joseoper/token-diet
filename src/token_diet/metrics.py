"""
metrics.py

Shared size metrics and health thresholds used by every token-diet audit surface.

Every module in this package reports footprint through these helpers so that a
byte count maps to exactly one badge and one token estimate across the CLI,
the section breakdown, and MCP payload auditing.
"""

from typing import Tuple

# Size thresholds in bytes
THRESHOLD_WARN_BYTES = 4_000   # ~1,000 tokens
THRESHOLD_ALERT_BYTES = 16_000 # ~4,000 tokens


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
