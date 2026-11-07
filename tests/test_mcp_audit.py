import json
import os
import sys
import tempfile
import unittest

# Ensure src is in sys.path
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from token_diet.mcp_audit import (
    MCP_CONFIG_CANDIDATES,
    audit_mcp_config,
    audit_mcp_overhead,
    discover_mcp_configs,
)
from token_diet.metrics import (
    THRESHOLD_ALERT_BYTES,
    THRESHOLD_WARN_BYTES,
    classify_size,
    estimate_tokens,
)


class TestMcpAudit(unittest.TestCase):
    def test_opencode_format_servers_transports_totals(self):
        content = {
            "mcp": {
                "local_srv": {
                    "type": "local",
                    "command": ["echo", "test"],
                },
                "remote_srv": {
                    "type": "remote",
                    "url": "https://example.com/mcp",
                },
            }
        }
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            json.dump(content, f)
            filepath = f.name

        try:
            res = audit_mcp_config(filepath)
            self.assertTrue(res["exists"])
            self.assertEqual(res["format"], "opencode")
            self.assertEqual(res["path"], filepath)

            servers = res["servers"]
            self.assertEqual(len(servers), 2)

            # Order preservation and server entry contents
            self.assertEqual(servers[0]["name"], "local_srv")
            self.assertEqual(servers[0]["transport"], "local")
            self.assertEqual(servers[0]["tool_count"], 0)
            local_bytes = len(
                json.dumps(
                    content["mcp"]["local_srv"],
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                ).encode("utf-8")
            )
            self.assertEqual(servers[0]["bytes"], local_bytes)
            self.assertEqual(servers[0]["estimated_tokens"], estimate_tokens(local_bytes))
            self.assertEqual(servers[0]["status"], "OK")
            self.assertEqual(servers[0]["severity"], "optimal")

            self.assertEqual(servers[1]["name"], "remote_srv")
            self.assertEqual(servers[1]["transport"], "remote")
            self.assertEqual(servers[1]["tool_count"], 0)
            remote_bytes = len(
                json.dumps(
                    content["mcp"]["remote_srv"],
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                ).encode("utf-8")
            )
            self.assertEqual(servers[1]["bytes"], remote_bytes)
            self.assertEqual(servers[1]["estimated_tokens"], estimate_tokens(remote_bytes))
            self.assertEqual(servers[1]["status"], "OK")
            self.assertEqual(servers[1]["severity"], "optimal")

            # Totals
            self.assertEqual(res["total_servers"], 2)
            self.assertEqual(res["total_bytes"], local_bytes + remote_bytes)
            self.assertEqual(
                res["total_tokens"],
                estimate_tokens(local_bytes) + estimate_tokens(remote_bytes),
            )
            self.assertEqual(res["status"], "OK")
            self.assertEqual(res["severity"], "optimal")
        finally:
            if os.path.exists(filepath):
                os.remove(filepath)

    def test_mcp_servers_format_command_and_url_transports(self):
        content = {
            "mcpServers": {
                "stdio_srv": {
                    "command": "python",
                    "args": ["-m", "mcp_server"],
                },
                "http_srv": {
                    "url": "http://localhost:8000/mcp",
                },
                "unknown_transport_srv": {
                    "env": {"KEY": "VALUE"},
                },
            }
        }
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            json.dump(content, f)
            filepath = f.name

        try:
            res = audit_mcp_config(filepath)
            self.assertTrue(res["exists"])
            self.assertEqual(res["format"], "mcpServers")
            self.assertEqual(len(res["servers"]), 3)
            self.assertEqual(res["servers"][0]["transport"], "stdio")
            self.assertEqual(res["servers"][1]["transport"], "http")
            self.assertEqual(res["servers"][2]["transport"], "unknown")
            self.assertEqual(res["total_servers"], 3)
        finally:
            if os.path.exists(filepath):
                os.remove(filepath)

    def test_inline_tools_dict_and_list(self):
        content = {
            "mcpServers": {
                "srv_list": {
                    "command": "node",
                    "tools": [
                        {"name": "tool1", "description": "d1"},
                        {"name": "tool2", "description": "d2"},
                    ],
                },
                "srv_dict": {
                    "command": "node",
                    "tools": {
                        "toolA": {"description": "dA"},
                        "toolB": {"description": "dB"},
                        "toolC": {"description": "dC"},
                    },
                },
                "srv_no_tools": {
                    "command": "node",
                    "tools": "not-a-collection",
                },
            }
        }
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            json.dump(content, f)
            filepath = f.name

        try:
            res = audit_mcp_config(filepath)
            self.assertEqual(len(res["servers"]), 3)
            self.assertEqual(res["servers"][0]["tool_count"], 2)
            self.assertEqual(res["servers"][1]["tool_count"], 3)
            self.assertEqual(res["servers"][2]["tool_count"], 0)

            # Ensure tool bytes are included in the server bytes
            expected_bytes_0 = len(
                json.dumps(
                    content["mcpServers"]["srv_list"],
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                ).encode("utf-8")
            )
            self.assertEqual(res["servers"][0]["bytes"], expected_bytes_0)
        finally:
            if os.path.exists(filepath):
                os.remove(filepath)

    def test_malformed_json_error_shape(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            f.write("{\ninvalid json: [")
            filepath = f.name

        try:
            res = audit_mcp_config(filepath)
            self.assertTrue(res["exists"])
            self.assertEqual(res["path"], filepath)
            self.assertEqual(res["format"], "unknown")
            self.assertEqual(res["servers"], [])
            self.assertEqual(res["total_servers"], 0)
            self.assertEqual(res["total_bytes"], 0)
            self.assertEqual(res["total_tokens"], 0)
            self.assertEqual(res["status"], "ERROR")
            self.assertEqual(res["severity"], "critical")
            self.assertIn("error", res)
            self.assertIsInstance(res["error"], str)
        finally:
            if os.path.exists(filepath):
                os.remove(filepath)

    def test_unknown_top_level_shape(self):
        for payload in [{"other": 123}, [1, 2, 3], "just-a-string"]:
            with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
                json.dump(payload, f)
                filepath = f.name

            try:
                res = audit_mcp_config(filepath)
                self.assertTrue(res["exists"])
                self.assertEqual(res["path"], filepath)
                self.assertEqual(res["format"], "unknown")
                self.assertEqual(res["servers"], [])
                self.assertEqual(res["total_servers"], 0)
                self.assertEqual(res["total_bytes"], 0)
                self.assertEqual(res["total_tokens"], 0)
                self.assertEqual(res["status"], "OK")
                self.assertEqual(res["severity"], "optimal")
                self.assertNotIn("error", res)
            finally:
                if os.path.exists(filepath):
                    os.remove(filepath)

    def test_missing_file_missing_shape(self):
        missing_path = "/non/existent/mcp_config_missing_file.json"
        res = audit_mcp_config(missing_path)
        expected = {
            "path": missing_path,
            "exists": False,
            "format": "unknown",
            "servers": [],
            "total_servers": 0,
            "total_bytes": 0,
            "total_tokens": 0,
            "status": "MISSING",
            "severity": "none",
        }
        self.assertEqual(res, expected)

    def test_discover_mcp_configs_order_dedup_and_empty(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            # 1. Empty directory -> []
            self.assertEqual(discover_mcp_configs(tmp_dir), [])

            # 2. Missing directory -> []
            missing_dir = os.path.join(tmp_dir, "non_existent_subdir")
            self.assertEqual(discover_mcp_configs(missing_dir), [])

            # 3. Create candidates out of candidate order:
            # MCP_CONFIG_CANDIDATES = ["opencode.json", ".mcp.json", "mcp.json", ".cursor/mcp.json", ".vscode/mcp.json"]
            vscode_dir = os.path.join(tmp_dir, ".vscode")
            os.makedirs(vscode_dir)
            vscode_mcp = os.path.join(vscode_dir, "mcp.json")
            with open(vscode_mcp, "w") as f:
                f.write("{}")

            opencode_mcp = os.path.join(tmp_dir, "opencode.json")
            with open(opencode_mcp, "w") as f:
                f.write("{}")

            dot_mcp = os.path.join(tmp_dir, ".mcp.json")
            with open(dot_mcp, "w") as f:
                f.write("{}")

            discovered = discover_mcp_configs(tmp_dir)
            expected = [
                os.path.abspath(opencode_mcp),
                os.path.abspath(dot_mcp),
                os.path.abspath(vscode_mcp),
            ]
            self.assertEqual(discovered, expected)

            # 4. Deduplication: symlink or aliased path
            cursor_dir = os.path.join(tmp_dir, ".cursor")
            os.makedirs(cursor_dir)
            cursor_mcp = os.path.join(cursor_dir, "mcp.json")
            # Symlink cursor_mcp -> opencode_mcp
            try:
                os.symlink(opencode_mcp, cursor_mcp)
                discovered_symlink = discover_mcp_configs(tmp_dir)
                # opencode_mcp is already discovered, so cursor_mcp pointing to same file is deduplicated
                self.assertEqual(discovered_symlink, expected)
            except OSError:
                pass  # On systems where symlinks are restricted

    def test_audit_mcp_overhead_aggregation(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg1_path = os.path.join(tmp_dir, "opencode.json")
            cfg1_content = {
                "mcp": {
                    "srv1": {
                        "type": "local",
                        "command": ["echo", "1"],
                    }
                }
            }
            with open(cfg1_path, "w") as f:
                json.dump(cfg1_content, f)

            cfg2_path = os.path.join(tmp_dir, ".mcp.json")
            cfg2_content = {
                "mcpServers": {
                    "srv2": {
                        "command": "python",
                    },
                    "srv3": {
                        "url": "http://localhost:5000",
                    },
                }
            }
            with open(cfg2_path, "w") as f:
                json.dump(cfg2_content, f)

            overhead = audit_mcp_overhead(tmp_dir)
            self.assertEqual(overhead["config_count"], 2)
            self.assertEqual(len(overhead["configs"]), 2)
            self.assertEqual(overhead["total_servers"], 3)

            expected_bytes = overhead["configs"][0]["total_bytes"] + overhead["configs"][1]["total_bytes"]
            expected_tokens = overhead["configs"][0]["total_tokens"] + overhead["configs"][1]["total_tokens"]
            self.assertEqual(overhead["total_bytes"], expected_bytes)
            self.assertEqual(overhead["total_tokens"], expected_tokens)

    def test_server_and_file_size_thresholds(self):
        # Test server exceeding WARN and ALERT thresholds
        big_tools = [{"name": f"tool_{i}", "desc": "x" * 200} for i in range(100)]
        content = {
            "mcpServers": {
                "heavy_srv": {
                    "command": "node",
                    "tools": big_tools,
                }
            }
        }
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            json.dump(content, f)
            filepath = f.name

        try:
            res = audit_mcp_config(filepath)
            self.assertGreater(res["servers"][0]["bytes"], THRESHOLD_ALERT_BYTES)
            self.assertEqual(res["servers"][0]["status"], "ALERT")
            self.assertEqual(res["servers"][0]["severity"], "critical")
            self.assertEqual(res["status"], "ALERT")
            self.assertEqual(res["severity"], "critical")
        finally:
            if os.path.exists(filepath):
                os.remove(filepath)


if __name__ == "__main__":
    unittest.main()
