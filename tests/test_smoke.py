import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.claude_delegate import redact  # noqa: E402


class McpSmokeTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
