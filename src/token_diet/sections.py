"""
sections.py

Markdown heading breakdown and section footprint auditing for token-diet.
Quantifies byte and token consumption per section to pinpoint context bloat.
"""

import os
from typing import Any, Dict, List

from .metrics import (
    THRESHOLD_ALERT_BYTES,
    THRESHOLD_WARN_BYTES,
    classify_size,
    estimate_tokens,
)


def split_sections(text: str, level: int = 2) -> List[Dict[str, Any]]:
    """Splits markdown text into section dictionaries based on heading level.

    A heading line starts with exactly level '#' characters followed by a space.
    Content prior to the first heading (if non-whitespace) forms a '(preamble)'
    section at level 0 and line 1.
    """
    if not text or level < 1:
        return []

    prefix = ("#" * level) + " "
    lines = text.splitlines(keepends=True)

    headings: List[Any] = []
    for idx, line in enumerate(lines):
        if line.startswith(prefix):
            heading_title = line[len(prefix) :].strip()
            headings.append((idx, idx + 1, heading_title))

    if not headings:
        return []

    sections: List[Dict[str, Any]] = []

    # Check for preamble before the first heading
    first_heading_idx = headings[0][0]
    if first_heading_idx > 0:
        preamble_lines = lines[:first_heading_idx]
        preamble_text = "".join(preamble_lines)
        if preamble_text.strip():
            b_count = len(preamble_text.encode("utf-8"))
            status, severity = classify_size(b_count)
            sections.append(
                {
                    "heading": "(preamble)",
                    "level": 0,
                    "line": 1,
                    "text": preamble_text,
                    "bytes": b_count,
                    "estimated_tokens": estimate_tokens(b_count),
                    "status": status,
                    "severity": severity,
                }
            )

    # Build sections for each heading
    for i, (idx, line_num, title) in enumerate(headings):
        next_idx = headings[i + 1][0] if i + 1 < len(headings) else len(lines)
        section_lines = lines[idx:next_idx]
        section_text = "".join(section_lines)
        b_count = len(section_text.encode("utf-8"))
        status, severity = classify_size(b_count)
        sections.append(
            {
                "heading": title,
                "level": level,
                "line": line_num,
                "text": section_text,
                "bytes": b_count,
                "estimated_tokens": estimate_tokens(b_count),
                "status": status,
                "severity": severity,
            }
        )

    return sections


def audit_sections(filepath: str) -> Dict[str, Any]:
    """Audits a markdown file and returns per-heading section breakdown and file metrics."""
    if not os.path.exists(filepath):
        return {
            "path": filepath,
            "exists": False,
            "bytes": 0,
            "estimated_tokens": 0,
            "status": "MISSING",
            "severity": "none",
            "sections": [],
        }

    try:
        st = os.stat(filepath)
        import stat
        if not stat.S_ISREG(st.st_mode):
            return {
                "path": filepath,
                "exists": False,
                "error": f"Not a regular file: {filepath}",
                "bytes": 0,
                "estimated_tokens": 0,
                "status": "ERROR",
                "severity": "critical",
                "sections": [],
            }
        MAX_SAFE_BYTES = 10 * 1024 * 1024  # 10 MB
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(MAX_SAFE_BYTES)
        size = st.st_size
        tokens = estimate_tokens(size)
        status, severity = classify_size(size)
        sections = split_sections(content)
        return {
            "path": filepath,
            "exists": True,
            "bytes": size,
            "estimated_tokens": tokens,
            "status": status,
            "severity": severity,
            "sections": sections,
        }
    except OSError as e:
        return {
            "path": filepath,
            "exists": False,
            "error": str(e),
            "bytes": 0,
            "estimated_tokens": 0,
            "status": "ERROR",
            "severity": "critical",
            "sections": [],
        }


def audit_sections_for_paths(paths: List[str]) -> Dict[str, Any]:
    """Audits multiple files and aggregates total bytes, tokens, and file count."""
    files = [audit_sections(p) for p in paths]
    total_bytes = sum(f.get("bytes", 0) for f in files)
    total_tokens = sum(f.get("estimated_tokens", 0) for f in files)
    return {
        "files": files,
        "file_count": len(files),
        "total_bytes": total_bytes,
        "total_tokens": total_tokens,
    }
