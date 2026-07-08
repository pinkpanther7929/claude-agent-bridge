# claude-agent-bridge

MCP bridge for using local Claude CLI as a bounded reviewer and analysis delegate for Codex.

## Goals

- Let Codex delegate small, bounded tasks to Claude.
- Keep Codex responsible for final decisions, file edits, commits, deploys, and verification.
- Redact sensitive-looking lines before sending context.
- Save Claude outputs for audit and follow-up review.
- Avoid mixing bridge infrastructure experiments into work repos.

## Tools

- `claude_status`: check delegation state.
- `claude_set_enabled`: enable or disable delegation.
- `claude_ask`: ask Claude for bounded analysis with optional files.
- `claude_review_diff`: ask Claude to review current git diff or selected paths.
- `claude_read_result`: read saved Claude output.

## Local Checks

```powershell
python -m py_compile scripts\claude_delegate.py mcp\claude_mcp_server.py
python -X utf8 -m json.tool .mcp.json
python -m unittest discover -s tests
python scripts\claude_delegate.py status --json
```

Plugin manifest validation uses the Codex plugin creator validator, which requires
`PyYAML` in the active Python environment.

Actual Claude delegation may need to run outside the managed Codex sandbox:

```powershell
python scripts\claude_delegate.py --task second-opinion --prompt "Reply with exactly: OK" --timeout-seconds 30 --json
```

## Safety Rules

- Do not send secrets, tokens, webhooks, passwords, API keys, or tickets.
- Do not ask Claude to edit files, run live operations, commit, push, or deploy.
- Pass only the smallest useful diff, file excerpt, or log excerpt.
- Treat Claude output as review input, not authority.
