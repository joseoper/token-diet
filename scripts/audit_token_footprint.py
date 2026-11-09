#!/usr/bin/env python3
"""
audit_token_footprint.py

Diagnostic tool to inspect and quantify token and byte footprint
of prompt directives, project files, and system configurations.
"""

import os
import sys

# Add src to sys.path if running directly from source checkout
src_path = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "src"))
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from token_diet.cli import (
    estimate_tokens,
    audit_file,
    resolve_target_paths,
    audit_known_prompts,
    summarize_footprint,
    main,
    DEFAULT_PROMPT_PATHS,
)

if __name__ == "__main__":
    main()
