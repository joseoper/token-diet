"""
mcp_audit.py

Discovery and accounting logic for Model Context Protocol (MCP) server configurations.
Audits tool definitions and server payload sizes to quantify context injection overhead.
"""

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from .metrics import (
    THRESHOLD_ALERT_BYTES,
    THRESHOLD_WARN_BYTES,
    classify_size,
    estimate_tokens,
)

MCP_CONFIG_CANDIDATES: List[str] = [
    "opencode.json",
    ".mcp.json",
    "mcp.json",
    ".cursor/mcp.json",
    ".vscode/mcp.json",
]


def discover_mcp_configs(base_dir: str = ".") -> List[str]:
    """
    Discovers existing MCP configuration files in candidate order within base_dir.

    Returns absolute paths of regular files, deduplicated preserving order.
    Returns an empty list if base_dir is missing or no candidates are found.
    """
    if not os.path.isdir(base_dir):
        return []

    abs_base = os.path.abspath(base_dir)
    discovered: List[str] = []
    seen = set()

    for candidate in MCP_CONFIG_CANDIDATES:
        full_path = os.path.abspath(os.path.join(abs_base, candidate))
        if os.path.isfile(full_path):
            real_path = os.path.realpath(full_path)
            if full_path not in seen and real_path not in seen:
                seen.add(full_path)
                seen.add(real_path)
                discovered.append(full_path)

    return discovered


def audit_mcp_config(filepath: str) -> Dict[str, Any]:
    """
    Audits a single MCP configuration file and calculates server payload footprints.

    Detects opencode and mcpServers formats, extracts declared servers, counts tools,
    computes UTF-8 byte sizes, estimated tokens, and assigns health status ratings.
    Never raises an exception on invalid or missing files.
    """
    if not os.path.exists(filepath):
        return {
            "path": filepath,
            "exists": False,
            "format": "unknown",
            "servers": [],
            "total_servers": 0,
            "total_bytes": 0,
            "total_tokens": 0,
            "status": "MISSING",
            "severity": "none",
        }

    try:
        st = os.stat(filepath)
        import stat
        if not stat.S_ISREG(st.st_mode):
            return {
                "path": filepath,
                "exists": False,
                "format": "unknown",
                "servers": [],
                "total_servers": 0,
                "total_bytes": 0,
                "total_tokens": 0,
                "error": f"Not a regular file: {filepath}",
                "status": "ERROR",
                "severity": "critical",
            }
        MAX_SAFE_BYTES = 10 * 1024 * 1024  # 10 MB
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read(MAX_SAFE_BYTES)
        data = json.loads(content)
    except Exception as e:
        return {
            "path": filepath,
            "exists": True,
            "format": "unknown",
            "servers": [],
            "total_servers": 0,
            "total_bytes": 0,
            "total_tokens": 0,
            "error": str(e),
            "status": "ERROR",
            "severity": "critical",
        }

    format_name = "unknown"
    servers_dict: Optional[Dict[str, Any]] = None

    if isinstance(data, dict):
        if isinstance(data.get("mcp"), dict):
            format_name = "opencode"
            servers_dict = data["mcp"]
        elif isinstance(data.get("mcpServers"), dict):
            format_name = "mcpServers"
            servers_dict = data["mcpServers"]

    servers: List[Dict[str, Any]] = []

    if servers_dict is not None:
        for name, server_value in servers_dict.items():
            if format_name == "opencode":
                if isinstance(server_value, dict) and isinstance(server_value.get("type"), str):
                    transport = server_value["type"]
                else:
                    transport = "unknown"
            elif format_name == "mcpServers":
                if isinstance(server_value, dict):
                    if "command" in server_value:
                        transport = "stdio"
                    elif "url" in server_value:
                        transport = "http"
                    else:
                        transport = "unknown"
                else:
                    transport = "unknown"
            else:
                transport = "unknown"

            tool_count = 0
            if isinstance(server_value, dict):
                tools = server_value.get("tools")
                if isinstance(tools, (dict, list)):
                    tool_count = len(tools)

            dumped = json.dumps(server_value, sort_keys=True, separators=(",", ":"), default=str)
            server_bytes = len(dumped.encode("utf-8"))
            server_tokens = estimate_tokens(server_bytes)
            status, severity = classify_size(server_bytes)

            servers.append({
                "name": name,
                "transport": transport,
                "tool_count": tool_count,
                "bytes": server_bytes,
                "estimated_tokens": server_tokens,
                "status": status,
                "severity": severity,
            })

    total_servers = len(servers)
    total_bytes = sum(s["bytes"] for s in servers)
    total_tokens = sum(s["estimated_tokens"] for s in servers)
    file_status, file_severity = classify_size(total_bytes)

    return {
        "path": filepath,
        "exists": True,
        "format": format_name,
        "servers": servers,
        "total_servers": total_servers,
        "total_bytes": total_bytes,
        "total_tokens": total_tokens,
        "status": file_status,
        "severity": file_severity,
    }


def audit_mcp_overhead(base_dir: str = ".") -> Dict[str, Any]:
    """
    Discovers all MCP configuration files under base_dir and computes aggregate overhead.
    """
    configs = [audit_mcp_config(p) for p in discover_mcp_configs(base_dir)]
    config_count = len(configs)
    total_servers = sum(c["total_servers"] for c in configs)
    total_bytes = sum(c["total_bytes"] for c in configs)
    total_tokens = sum(c["total_tokens"] for c in configs)

    return {
        "configs": configs,
        "config_count": config_count,
        "total_servers": total_servers,
        "total_bytes": total_bytes,
        "total_tokens": total_tokens,
    }
