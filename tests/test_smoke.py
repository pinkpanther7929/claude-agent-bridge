import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.claude_delegate import redact  # noqa: E402
from scripts.install_mcp_config import install  # noqa: E402


class McpSmokeTests(unittest.TestCase):
    def test_install_mcp_config_creates_repo_local_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            result = install(target, server_name="claude_delegate", force=False, dry_run=False)
            config = json.loads((target / ".mcp.json").read_text(encoding="utf-8"))
            server = config["mcpServers"]["claude_delegate"]
            self.assertEqual(result["status"], "changed")
            self.assertEqual(server["command"], "python")
            self.assertEqual(server["cwd"], str(target.resolve()))
            self.assertTrue(server["args"][-1].endswith("mcp\\claude_mcp_server.py") or server["args"][-1].endswith("mcp/claude_mcp_server.py"))

    def test_install_mcp_config_preserves_existing_servers(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            (target / ".mcp.json").write_text(
                json.dumps({"mcpServers": {"other": {"command": "other"}}}),
                encoding="utf-8",
            )
            install(target, server_name="claude_delegate", force=False, dry_run=False)
            config = json.loads((target / ".mcp.json").read_text(encoding="utf-8"))
            self.assertEqual(config["mcpServers"]["other"], {"command": "other"})
            self.assertIn("claude_delegate", config["mcpServers"])

    def test_install_mcp_config_rejects_conflicting_server_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            (target / ".mcp.json").write_text(
                json.dumps({"mcpServers": {"claude_delegate": {"command": "old"}}}),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                install(target, server_name="claude_delegate", force=False, dry_run=False)

    def test_install_codex_registers_global_mcp_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "codex.toml"
            proc = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-File",
                    str(ROOT / "scripts" / "install-codex.ps1"),
                    "-RepoPath",
                    str(ROOT),
                    "-ConfigPath",
                    str(config),
                ],
                cwd=ROOT,
                text=True,
                encoding="utf-8",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
                check=True,
            )
            text = config.read_text(encoding="utf-8-sig")
            self.assertIn("[mcp_servers.claude_agent_bridge]", text)
            self.assertIn("mcp\\claude_mcp_server.py", text)
            self.assertIn(str(ROOT).replace("'", "''"), text)
            self.assertIn("Registered Codex MCP server", proc.stdout)

    def test_mcp_lists_claude_tools(self):
        payload = "\n".join([
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
            "",
        ])
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", "mcp/claude_mcp_server.py"],
            input=payload,
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            check=True,
        )
        lines = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        tool_names = {tool["name"] for tool in lines[1]["result"]["tools"]}
        self.assertTrue({
            "claude_status",
            "claude_set_enabled",
            "claude_ask",
            "claude_review_diff",
            "claude_read_result",
        }.issubset(tool_names))

    def test_mcp_status_tool_call_returns_json_text(self):
        payload = "\n".join([
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
            json.dumps({
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "claude_status", "arguments": {}},
            }),
            "",
        ])
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", "mcp/claude_mcp_server.py"],
            input=payload,
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            check=True,
        )
        lines = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        content = lines[1]["result"]["content"][0]["text"]
        status = json.loads(content)
        self.assertIn(status["status"], {"enabled", "disabled"})

    def test_redact_hides_sensitive_assignments_but_keeps_code(self):
        text = "\n".join([
            "api_token = abc123",
            "Authorization: Bearer abc123",
            "if token is None:",
            "    return token",
        ])
        redacted = redact(text)
        self.assertIn("[redacted sensitive-looking line]", redacted)
        self.assertNotIn("abc123", redacted)
        self.assertIn("if token is None:", redacted)
        self.assertIn("return token", redacted)

    def test_delegate_dry_run_writes_prompt_without_claude(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "prompt.md"
            proc = subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    "scripts/claude_delegate.py",
                    "--prompt",
                    "Check bounded context.",
                    "--dry-run",
                    "--json",
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                text=True,
                encoding="utf-8",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
                check=True,
            )
            result = json.loads(proc.stdout)
            self.assertEqual(result["status"], "dry-run")
            prompt = output.read_text(encoding="utf-8")
            self.assertIn("No file edits, commands, deploys, commits", prompt)
            self.assertIn("Check bounded context.", prompt)

    def test_delegate_resolves_relative_files_from_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work / "sample.txt").write_text("bounded file context", encoding="utf-8")
            output = work / "prompt.md"
            subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    "scripts/claude_delegate.py",
                    "--cwd",
                    str(work),
                    "--prompt",
                    "Review selected file.",
                    "--file",
                    "sample.txt",
                    "--dry-run",
                    "--json",
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                text=True,
                encoding="utf-8",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
                check=True,
            )
            prompt = output.read_text(encoding="utf-8")
            self.assertIn("bounded file context", prompt)
            self.assertNotIn("[missing]", prompt)

    def test_mcp_read_result_resolves_relative_output_root_from_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            output_root = work / ".tmp" / "claude_delegate"
            output_root.mkdir(parents=True)
            result_file = output_root / "result.md"
            result_file.write_text("saved result", encoding="utf-8")
            payload = "\n".join([
                json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
                json.dumps({
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "claude_read_result",
                        "arguments": {
                            "cwd": str(work),
                            "output_root": ".tmp/claude_delegate",
                            "max_chars": 1000,
                        },
                    },
                }),
                "",
            ])
            proc = subprocess.run(
                [sys.executable, "-X", "utf8", "mcp/claude_mcp_server.py"],
                input=payload,
                cwd=ROOT,
                text=True,
                encoding="utf-8",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
                check=True,
            )
            lines = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
            result = lines[1]["result"]
            self.assertFalse(result["isError"])
            self.assertIn("saved result", result["content"][0]["text"])

    def test_mcp_defaults_workspace_to_server_start_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            output_root = work / ".tmp" / "claude_delegate"
            output_root.mkdir(parents=True)
            (output_root / "result.md").write_text("default workspace result", encoding="utf-8")
            payload = "\n".join([
                json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
                json.dumps({
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "claude_read_result",
                        "arguments": {
                            "output_root": ".tmp/claude_delegate",
                            "max_chars": 1000,
                        },
                    },
                }),
                "",
            ])
            proc = subprocess.run(
                [sys.executable, "-X", "utf8", str(ROOT / "mcp" / "claude_mcp_server.py")],
                input=payload,
                cwd=work,
                text=True,
                encoding="utf-8",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
                check=True,
            )
            lines = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
            result = lines[1]["result"]
            self.assertFalse(result["isError"])
            self.assertIn("default workspace result", result["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
