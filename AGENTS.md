Use `claude-agent-bridge` only for bounded Claude delegation.

Claude is a subordinate reviewer/analyst. Codex keeps ownership of decisions,
file edits, commits, pushes, deployments, and verification.

Use Claude when an independent second opinion can help:
- review a focused diff
- analyze a bounded log excerpt
- compare a proposed fix
- identify risks in a narrow implementation plan

Do not send secrets, tokens, webhooks, API keys, tickets, or credentials.
Do not ask Claude to edit files, run commands, commit, push, deploy, or operate
live systems.

Prefer MCP tools when available:
- `claude_status`
- `claude_set_enabled`
- `claude_ask`
- `claude_review_diff`
- `claude_read_result`

Fallback if MCP is unavailable:
- `python scripts\claude_delegate.py --task second-opinion --prompt "..."`

Actual Claude CLI calls may need to run outside a managed sandbox.
