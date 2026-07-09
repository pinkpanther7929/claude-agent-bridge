#!/usr/bin/env python3
"""Install claude-agent-bridge into a target repo's .mcp.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


DEFAULT_SERVER_NAME = "claude_delegate"
BRIDGE_ROOT = Path(__file__).resolve().parents[1]
SERVER_SCRIPT = BRIDGE_ROOT / "mcp" / "claude_mcp_server.py"


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def server_config(target: Path) -> dict[str, Any]:
    return {
        "command": "python",
        "args": ["-X", "utf8", str(SERVER_SCRIPT)],
        "cwd": str(target),
        "startup_timeout_sec": 30,
    }


def install(target: Path, *, server_name: str, force: bool, dry_run: bool) -> dict[str, Any]:
    target = target.resolve()
    if not target.exists() or not target.is_dir():
        raise ValueError(f"target must be an existing directory: {target}")

    config_path = target / ".mcp.json"
    config = load_config(config_path)
    servers = config.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError(f"{config_path} field 'mcpServers' must be an object")

    desired = server_config(target)
    existing = servers.get(server_name)
    if existing is not None and existing != desired and not force:
        raise ValueError(f"server '{server_name}' already exists in {config_path}; use --force to replace")

    changed = existing != desired
    servers[server_name] = desired
    rendered = json.dumps(config, ensure_ascii=False, indent=2) + "\n"
    if changed and not dry_run:
        config_path.write_text(rendered, encoding="utf-8", newline="\n")

    return {
        "status": "would-change" if dry_run and changed else "changed" if changed else "unchanged",
        "target": str(target),
        "config": str(config_path),
        "server": server_name,
        "server_script": str(SERVER_SCRIPT),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install claude-agent-bridge into a repo-local .mcp.json.")
    parser.add_argument("target", nargs="?", type=Path, default=Path.cwd(), help="Target repo/workspace directory.")
    parser.add_argument("--server-name", default=DEFAULT_SERVER_NAME)
    parser.add_argument("--force", action="store_true", help="Replace an existing server entry with the same name.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = install(args.target, server_name=args.server_name, force=args.force, dry_run=args.dry_run)
    except Exception as exc:
        if args.json:
            print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"{result['status']}: {result['config']}")
    return 0


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
