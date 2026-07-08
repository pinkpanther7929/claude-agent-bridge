#!/usr/bin/env python3
"""Minimal stdio MCP server for bounded Claude delegation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DELEGATE_SCRIPT = PLUGIN_ROOT / "scripts" / "claude_delegate.py"


def emit(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def text_result(text: str, *, is_error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def run_delegate(args: list[str], *, cwd: str | None = None, timeout: int = 120) -> tuple[int, str, str]:
    command = [sys.executable, "-X", "utf8", str(DELEGATE_SCRIPT), *args]
    proc = subprocess.run(
        command,
        cwd=cwd or str(PLUGIN_ROOT),
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def maybe_json(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return text


def latest_result(root: Path) -> Path | None:
    if not root.exists():
        return None
    files = [path for path in root.glob("*.md") if path.is_file()]
    if not files:
        return None
    return max(files, key=lambda path: path.stat().st_mtime)


def delegate_output_root(cwd: str | None) -> Path:
    base = Path(cwd).resolve() if cwd else PLUGIN_ROOT
    return base / ".tmp" / "claude_delegate"


def resolve_workspace_path(path: str, cwd: str | None) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    base = Path(cwd).resolve() if cwd else PLUGIN_ROOT
    return base / candidate


TOOLS: list[dict[str, Any]] = [
    {
        "name": "claude_status",
        "description": "Check whether Claude delegation is enabled and reachable.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "claude_set_enabled",
        "description": "Enable or disable bounded Claude delegation.",
        "inputSchema": {
            "type": "object",
            "properties": {"enabled": {"type": "boolean"}},
            "required": ["enabled"],
            "additionalProperties": False,
        },
    },
    {
        "name": "claude_ask",
        "description": "Ask Claude for bounded read-only analysis using an optional file list.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "task": {
                    "type": "string",
                    "enum": ["review", "analyze", "second-opinion"],
                    "default": "second-opinion",
                },
                "files": {"type": "array", "items": {"type": "string"}, "default": []},
                "cwd": {"type": "string"},
                "timeout_seconds": {"type": "integer", "minimum": 10, "maximum": 600, "default": 120},
                "max_file_chars": {"type": "integer", "minimum": 1000, "maximum": 100000, "default": 12000},
            },
            "required": ["prompt"],
            "additionalProperties": False,
        },
    },
    {
        "name": "claude_review_diff",
        "description": "Ask Claude to review the current git diff or selected diff paths.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "cwd": {"type": "string"},
                "diff_paths": {"type": "array", "items": {"type": "string"}, "default": []},
                "timeout_seconds": {"type": "integer", "minimum": 10, "maximum": 600, "default": 120},
                "max_diff_chars": {"type": "integer", "minimum": 1000, "maximum": 200000, "default": 24000},
            },
            "required": ["prompt"],
            "additionalProperties": False,
        },
    },
    {
        "name": "claude_read_result",
        "description": "Read a Claude delegation output file, or the latest output when no path is provided.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "output_root": {"type": "string", "default": ".tmp/claude_delegate"},
                "cwd": {"type": "string"},
                "max_chars": {"type": "integer", "minimum": 1000, "maximum": 200000, "default": 20000},
            },
            "additionalProperties": False,
        },
    },
]


def handle_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "claude_status":
        code, out, err = run_delegate(["status", "--json"], timeout=30)
        payload = maybe_json(out)
        text = json.dumps(payload, ensure_ascii=False, indent=2) if not isinstance(payload, str) else (payload or err)
        return text_result(text, is_error=code != 0)

    if name == "claude_set_enabled":
        command = "on" if arguments["enabled"] else "off"
        code, out, err = run_delegate([command, "--json"], timeout=30)
        return text_result(out or err, is_error=code != 0)

    if name == "claude_ask":
        timeout_seconds = int(arguments.get("timeout_seconds", 120))
        args = [
            "--task",
            arguments.get("task") or "second-opinion",
            "--prompt",
            arguments["prompt"],
            "--json",
            "--timeout-seconds",
            str(timeout_seconds),
            "--output-root",
            str(delegate_output_root(arguments.get("cwd"))),
            "--max-file-chars",
            str(arguments.get("max_file_chars", 12000)),
        ]
        for file_path in arguments.get("files") or []:
            args.extend(["--file", file_path])
        code, out, err = run_delegate(args, cwd=arguments.get("cwd"), timeout=timeout_seconds + 20)
        return text_result(out or err, is_error=code != 0)

    if name == "claude_review_diff":
        timeout_seconds = int(arguments.get("timeout_seconds", 120))
        args = [
            "--task",
            "review",
            "--prompt",
            arguments["prompt"],
            "--diff",
            "--json",
            "--timeout-seconds",
            str(timeout_seconds),
            "--output-root",
            str(delegate_output_root(arguments.get("cwd"))),
            "--max-diff-chars",
            str(arguments.get("max_diff_chars", 24000)),
        ]
        for diff_path in arguments.get("diff_paths") or []:
            args.extend(["--diff-path", diff_path])
        code, out, err = run_delegate(args, cwd=arguments.get("cwd"), timeout=timeout_seconds + 20)
        return text_result(out or err, is_error=code != 0)

    if name == "claude_read_result":
        raw_path = arguments.get("path")
        root = (
            resolve_workspace_path(arguments["output_root"], arguments.get("cwd"))
            if arguments.get("output_root")
            else delegate_output_root(arguments.get("cwd"))
        )
        path = resolve_workspace_path(raw_path, arguments.get("cwd")) if raw_path else latest_result(root)
        if path is None:
            return text_result("No Claude delegation output found.", is_error=True)
        if not path.exists() or not path.is_file():
            return text_result(f"Claude delegation output not found: {path}", is_error=True)
        max_chars = int(arguments.get("max_chars", 20000))
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n\n[truncated at {max_chars} chars]"
        return text_result(f"### {path}\n\n{text}")

    return text_result(f"Unknown tool: {name}", is_error=True)


def handle(request: dict[str, Any]) -> None:
    method = request.get("method")
    req_id = request.get("id")

    if req_id is None:
        return

    if method == "initialize":
        emit(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "claude-delegate", "version": "0.1.0"},
                },
            }
        )
        return

    if method == "tools/list":
        emit({"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}})
        return

    if method == "tools/call":
        params = request.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        emit({"jsonrpc": "2.0", "id": req_id, "result": handle_tool(name, arguments)})
        return

    emit(
        {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }
    )


def main() -> int:
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    os.chdir(PLUGIN_ROOT)
    for line in sys.stdin:
        line = line.lstrip("\ufeff").strip()
        if not line:
            continue
        try:
            handle(json.loads(line))
        except Exception as exc:
            emit({"jsonrpc": "2.0", "id": None, "error": {"code": -32000, "message": str(exc)}})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
