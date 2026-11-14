"""
baseline.py

Baseline comparison and regression budget gatekeeper logic for token-diet.
"""

import json
import math
import os
from typing import Any, Dict, Optional


def extract_total_tokens(payload: Any) -> Optional[int]:
    """
    Extract total estimated tokens from a numeric value or report dictionary.

    Returns an integer token count if valid and non-negative, else None.
    Rejects booleans, negative numbers, and non-numeric values.
    """
    if isinstance(payload, bool):
        return None
    if isinstance(payload, (int, float)):
        if math.isnan(payload) or math.isinf(payload):
            return None
        if payload < 0:
            return None
        return int(payload)
    if isinstance(payload, dict):
        token_val = payload.get("total_tokens")
        if token_val is None and isinstance(payload.get("summary"), dict):
            token_val = payload["summary"].get("total_tokens")
        return extract_total_tokens(token_val)
    return None


def load_baseline(filepath: str) -> Dict[str, Any]:
    """
    Load baseline token count from a JSON report file.

    Returns a dict with 'ok', 'tokens', 'path', and 'error'.
    Never raises an exception.
    """
    if not os.path.exists(filepath):
        return {
            "ok": False,
            "tokens": None,
            "path": filepath,
            "error": f"Baseline file not found: {filepath}",
        }

    try:
        st = os.stat(filepath)
        import stat
        if not stat.S_ISREG(st.st_mode):
            return {
                "ok": False,
                "tokens": None,
                "path": filepath,
                "error": f"Baseline is not a regular file: {filepath}",
            }
        MAX_SAFE_BYTES = 10 * 1024 * 1024  # 10 MB
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read(MAX_SAFE_BYTES + 1)
        if len(content) > MAX_SAFE_BYTES:
            return {
                "ok": False,
                "tokens": None,
                "path": filepath,
                "error": f"Baseline file exceeds maximum size limit (10MB): {filepath}",
            }
        data = json.loads(content)
    except Exception as e:
        return {
            "ok": False,
            "tokens": None,
            "path": filepath,
            "error": f"Failed to parse baseline JSON: {e}",
        }

    tokens = extract_total_tokens(data)
    if tokens is None:
        return {
            "ok": False,
            "tokens": None,
            "path": filepath,
            "error": "No valid token count found in baseline file",
        }

    return {
        "ok": True,
        "tokens": tokens,
        "path": filepath,
        "error": None,
    }


def compare_tokens(current_tokens: int, baseline_tokens: int) -> Dict[str, Any]:
    """
    Compare current tokens against baseline tokens and compute delta metrics.

    Returns a dict with baseline_tokens, current_tokens, delta_tokens,
    delta_percent (rounded to 2 decimal places), direction, and indeterminate.
    """
    delta_tokens = current_tokens - baseline_tokens
    indeterminate = False
    if baseline_tokens > 0:
        delta_percent = round(delta_tokens / baseline_tokens * 100.0, 2)
    elif baseline_tokens == 0:
        if current_tokens > 0:
            delta_percent = None
            indeterminate = True
        else:
            delta_percent = 0.0
    else:
        delta_percent = 0.0

    if delta_tokens > 0:
        direction = "increase"
    elif delta_tokens < 0:
        direction = "decrease"
    else:
        direction = "unchanged"

    result = {
        "baseline_tokens": baseline_tokens,
        "current_tokens": current_tokens,
        "delta_tokens": delta_tokens,
        "delta_percent": delta_percent,
        "direction": direction,
    }
    if indeterminate:
        result["indeterminate"] = True
        result["delta_indeterminate"] = True

    return result


def check_budget(current_tokens: int, baseline_tokens: int, max_delta_percent: float) -> Dict[str, Any]:
    """
    Check if token growth exceeds the maximum allowed delta percentage budget.

    Budget is exceeded if direction is 'increase' and delta_percent is greater than max_delta_percent,
    or if baseline was 0 and new tokens were introduced (indeterminate infinite growth).
    Rejects NaN / Inf in max_delta_percent by treating invalid configurations as exceeded.
    """
    comparison = compare_tokens(current_tokens, baseline_tokens)
    max_delta = float(max_delta_percent)
    if not math.isfinite(max_delta) or math.isnan(max_delta):
        exceeded = True
    elif comparison.get("indeterminate"):
        exceeded = True
    else:
        exceeded = comparison["direction"] == "increase" and comparison["delta_percent"] > max_delta
    comparison["max_delta_percent"] = max_delta
    comparison["exceeded"] = exceeded
    return comparison

