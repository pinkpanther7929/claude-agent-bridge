#!/usr/bin/env python3
"""Run bounded read-only Claude CLI delegation from Codex."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = Path(".tmp") / "claude_delegate"
DEFAULT_STATE = Path(os.environ.get("CODEX_HOME", r"C:\Users\hsublee\.codex")) / "tmp" / "claude_delegate_state.json"
DEFAULT_AGENT = "claude-reviewer"
DEFAULT_AGENT_FILE = PLUGIN_ROOT / "agents" / "claude-reviewer.md"
SENSITIVE_MARKERS = (
    "password",
    "passwd",
    "secret",
    "token",
    "ticket",
    "webhook",
    "authorization",
    "api_key",
    "apikey",
)
SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"^\s*[A-Za-z0-9_.-]*(?:password|passwd|secret|token|ticket|webhook|authorization|api_?key)[A-Za-z0-9_.-]*\s*[:=]",
    re.IGNORECASE,
)


def load_state(path: Path = DEFAULT_STATE) -> dict[str, object]:
    if not path.exists():
        return {"enabled": True}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"enabled": True}
    except Exception:
        return {"enabled": True}


def save_state(state: dict[str, object], path: Path = DEFAULT_STATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def is_enabled(path: Path = DEFAULT_STATE) -> bool:
    if os.environ.get("CLAUDE_DELEGATE_DISABLED", "").strip().lower() in {"1", "true", "yes", "on"}:
        return False
    return bool(load_state(path).get("enabled", True))


def probe_claude_cli(claude: str = "claude") -> dict[str, object]:
    command = os.environ.get("CLAUDE_DELEGATE_CLI", claude)
    resolved = shutil.which(command)
    result: dict[str, object] = {
        "command": command,
        "resolved": resolved,
        "found": bool(resolved),
    }
    if not resolved:
        result["error"] = "not_found"
        return result

    try:
        proc = subprocess.run(
            [command, "--version"],
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
        )
    except Exception as exc:
        result.update({"reachable": False, "error": str(exc)})
        return result

    result.update(
        {
            "reachable": proc.returncode == 0,
            "returncode": proc.returncode,
            "version": (proc.stdout or proc.stderr).strip(),
        }
    )
    return result


def control(command: str, *, as_json: bool = False, path: Path = DEFAULT_STATE) -> int:
    state = load_state(path)
    if command == "on":
        state.update({"enabled": True, "updated_at": dt.datetime.now().isoformat(timespec="seconds")})
        save_state(state, path)
    elif command == "off":
        state.update({"enabled": False, "updated_at": dt.datetime.now().isoformat(timespec="seconds")})
        save_state(state, path)
    elif command != "status":
        raise ValueError(f"unknown control command: {command}")

    result = {
        "status": "enabled" if is_enabled(path) else "disabled",
        "state_path": str(path),
        "env_disabled": bool(os.environ.get("CLAUDE_DELEGATE_DISABLED")),
        "claude": probe_claude_cli(),
    }
    print(json.dumps(result, ensure_ascii=False) if as_json else result["status"])
    return 0


def run_git(args: list[str], cwd: Path) -> str:
    proc = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=15,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def redact(text: str) -> str:
    lines = []
    for line in text.splitlines():
        lower = line.casefold()
        looks_like_assignment = bool(SENSITIVE_ASSIGNMENT_RE.search(line)) or "authorization:" in lower or "bearer " in lower
        looks_like_code = lower.lstrip().startswith(("if ", "elif ", "def ", "class ", "return ", "#"))
        if looks_like_assignment and not looks_like_code and any(marker in lower for marker in SENSITIVE_MARKERS):
            lines.append("[redacted sensitive-looking line]")
        else:
            lines.append(line)
    return "\n".join(lines)


def read_file(path: Path, max_chars: int) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    text = redact(text)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n\n[truncated at {max_chars} chars]"


def resolve_context_path(path: str, cwd: Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else cwd / candidate


def file_blocks(paths: Iterable[Path], max_chars: int) -> str:
    blocks = []
    for path in paths:
        if not path.exists():
            blocks.append(f"### File: {path}\n\n[missing]")
            continue
        if not path.is_file():
            blocks.append(f"### File: {path}\n\n[not a file]")
            continue
        blocks.append(f"### File: {path}\n\n```text\n{read_file(path, max_chars)}\n```")
    return "\n\n".join(blocks)


def build_prompt(args: argparse.Namespace, cwd: Path) -> str:
    sections = [
        "Role: subordinate worker for Codex.",
        "Codex directs; you produce bounded output. Codex will verify/apply.",
        "No file edits, commands, deploys, commits, credential requests, or broad exploration.",
        "Be terse. Use evidence. Say 'insufficient evidence' when unsure.",
        "Output format: Findings / Patch suggestion / Risks / Verification.",
        f"Task: {args.task}",
        f"Request:\n{args.prompt.strip()}",
    ]

    if args.diff:
        diff_stat = redact(run_git(["diff", "--stat"], cwd))
        diff_text = redact(run_git(["diff", "--", *args.diff_path], cwd) if args.diff_path else run_git(["diff"], cwd))
        sections.append(f"Diff stat:\n```text\n{diff_stat or '(empty)'}\n```")
        sections.append(f"Diff:\n```diff\n{diff_text[:args.max_diff_chars] or '(empty)'}\n```")

    if args.file:
        sections.append("Files:\n" + file_blocks([resolve_context_path(p, cwd) for p in args.file], args.max_file_chars))

    return "\n\n".join(sections)


def output_path(root: Path, task: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_task = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in task.lower()).strip("-") or "delegate"
    return root / f"{stamp}-{safe_task}.md"


def agent_prompt(path: Path) -> str:
    if path.exists() and path.is_file():
        return path.read_text(encoding="utf-8", errors="replace")
    return (
        "You are a bounded read-only reviewer for Codex. "
        "Do not edit files, run commands, commit, deploy, or request credentials. "
        "Return concise findings, risks, and verification steps."
    )


def build_claude_command(args: argparse.Namespace) -> list[str]:
    claude = os.environ.get("CLAUDE_DELEGATE_CLI", args.claude)
    cmd = [
        claude,
        "-p",
        "--output-format",
        "text",
        "--permission-mode",
        "dontAsk",
        "--tools",
        "",
        "--no-session-persistence",
    ]
    if args.agent and not args.no_agent:
        agents = {
            args.agent: {
                "description": "Bounded read-only Claude reviewer for Codex.",
                "prompt": agent_prompt(args.agent_file),
            }
        }
        cmd.extend(["--agents", json.dumps(agents, ensure_ascii=False), "--agent", args.agent])
    if args.model:
        cmd.extend(["--model", args.model])
    if args.max_budget_usd:
        cmd.extend(["--max-budget-usd", str(args.max_budget_usd)])
    return cmd


def run_claude(args: argparse.Namespace, prompt: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        build_claude_command(args),
        cwd=str(cwd),
        input=prompt,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=args.timeout_seconds,
    )


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if argv and argv[0] in {"on", "off", "status"}:
        as_json = "--json" in argv[1:]
        return control(argv[0], as_json=as_json)

    parser = argparse.ArgumentParser(description="Delegate bounded read-only analysis to Claude CLI.")
    parser.add_argument("--task", default="review", choices=["review", "analyze", "second-opinion"])
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--file", action="append", help="File to include as bounded context. Repeatable.")
    parser.add_argument("--diff", action="store_true", help="Include current git diff.")
    parser.add_argument("--diff-path", action="append", default=[], help="Limit diff to a path. Repeatable.")
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--claude", default="claude")
    parser.add_argument("--agent", default=DEFAULT_AGENT, help="Claude Code agent name to run.")
    parser.add_argument("--agent-file", type=Path, default=DEFAULT_AGENT_FILE, help="Markdown prompt for the Claude Code agent.")
    parser.add_argument("--no-agent", action="store_true", help="Run Claude without injecting a custom agent.")
    parser.add_argument("--model")
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--max-file-chars", type=int, default=12000)
    parser.add_argument("--max-diff-chars", type=int, default=24000)
    parser.add_argument("--max-budget-usd", type=float)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if not is_enabled():
        result = {"status": "disabled", "reason": "claude_delegate_disabled"}
        print(json.dumps(result, ensure_ascii=False) if args.json else "disabled")
        return 0

    cwd = args.cwd.resolve()
    prompt = build_prompt(args, cwd)
    output_root = args.output_root if args.output_root.is_absolute() else cwd / args.output_root
    out_path = args.output or output_path(output_root, args.task)
    if not out_path.is_absolute():
        out_path = cwd / out_path

    if args.dry_run:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(prompt, encoding="utf-8", newline="\n")
        result = {"status": "dry-run", "output": str(out_path)}
        print(json.dumps(result, ensure_ascii=False) if args.json else f"wrote prompt: {out_path}")
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = run_claude(args, prompt, cwd)
    except subprocess.TimeoutExpired as exc:
        body = (
            "Claude delegation timed out.\n\n"
            "Likely causes:\n"
            "- Codex sandbox blocked Claude Code API access.\n"
            "- Claude Code is waiting on an external auth/API/network path.\n\n"
            f"Timeout seconds: {args.timeout_seconds}\n"
        )
        if exc.stdout:
            body += "\nClaude stdout before timeout:\n```text\n" + str(exc.stdout).strip() + "\n```\n"
        if exc.stderr:
            body += "\nClaude stderr before timeout:\n```text\n" + str(exc.stderr).strip() + "\n```\n"
        out_path.write_text(body.rstrip() + "\n", encoding="utf-8", newline="\n")
        result = {"status": "timeout", "returncode": None, "output": str(out_path)}
        print(json.dumps(result, ensure_ascii=False) if args.json else f"timeout: {out_path}")
        return 124

    body = proc.stdout.strip()
    if proc.returncode != 0:
        body = (body + "\n\n" if body else "") + "Claude stderr:\n```text\n" + proc.stderr.strip() + "\n```"
        if "ConnectionRefused" in body or "Unable to connect to API" in body:
            body = (
                "Claude delegation failed before model response.\n\n"
                "Likely cause: Claude Code API access is blocked in the current execution sandbox. "
                "Run this delegate command with escalated sandbox permissions.\n\n"
            ) + body
    out_path.write_text(body.rstrip() + "\n", encoding="utf-8", newline="\n")

    result = {"status": "ok" if proc.returncode == 0 else "failed", "returncode": proc.returncode, "output": str(out_path)}
    print(json.dumps(result, ensure_ascii=False) if args.json else f"{result['status']}: {out_path}")
    return 0 if proc.returncode == 0 else proc.returncode


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
