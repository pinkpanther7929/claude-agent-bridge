---
name: claude-delegate
description: Use when the user asks Codex to ask Claude, consult Claude, delegate work to Claude, get a second opinion from Claude, compare Claude's analysis, or run a bounded read-only review/log-analysis task through the local Claude CLI. Also use for slash-style controls such as /claude on, /claude off, /claude status, /claude-delegate on, /claude-delegate off, or /claude-delegate status. Claude is a subordinate reviewer; Codex keeps final responsibility and applies any changes itself.
---

# Claude Delegate

Use `scripts/claude_delegate.py` to call the local Claude CLI from Codex for bounded read-only analysis.

When Codex runs in the managed sandbox, Claude Code API access can fail with
`ConnectionRefused` or hang until timeout. Run actual delegation commands with escalated sandbox
permissions. Dry-run/status commands can run inside the sandbox.

Default Claude CLI:

```text
claude
```

Override with `CLAUDE_DELEGATE_CLI`.

## Commands

Slash-style controls:

| Command | Action |
|---------|--------|
| `/claude` | Show status and intended usage. |
| `/claude status` | Show enabled/disabled state. |
| `/claude on` | Enable Claude delegation. |
| `/claude off` | Disable Claude delegation until turned on again. |
| `/claude-delegate status` | Same as `/claude status`. |
| `/claude-delegate on` | Same as `/claude on`. |
| `/claude-delegate off` | Same as `/claude off`. |

```powershell
python plugins\claude-delegate\scripts\claude_delegate.py on
python plugins\claude-delegate\scripts\claude_delegate.py off
python plugins\claude-delegate\scripts\claude_delegate.py status
```

Ask Claude for a second opinion:

```powershell
python plugins\claude-delegate\scripts\claude_delegate.py --prompt "Review this approach for risks." --diff
```

Review specific files:

```powershell
python plugins\claude-delegate\scripts\claude_delegate.py --task review --file jenkins\jenkinsfiles\vars\message.groovy --prompt "Find regressions or missing tests."
```

Analyze a log or note without allowing Claude to edit:

```powershell
python plugins\claude-delegate\scripts\claude_delegate.py --task analyze --file path\to\log.txt --prompt "Identify the primary failure signal."
```

## MCP Tools

When this plugin is installed with MCP enabled, prefer MCP tools over raw shell commands:

| Tool | Purpose |
|------|---------|
| `claude_status` | Check delegation enabled/reachable state. |
| `claude_set_enabled` | Enable or disable delegation. |
| `claude_ask` | Ask Claude for bounded analysis with optional files. |
| `claude_review_diff` | Ask Claude to review the current git diff or selected paths. |
| `claude_read_result` | Read the latest or specified Claude output file. |

Use MCP tools with the same safety rules: bounded context only, no secrets, no
live operations, no commits, no pushes, and Codex must verify the result.

## Rules

- Codex directs. Claude works on bounded analysis/patch drafts. Codex verifies and applies.
- Actual Claude delegation must run outside the Codex sandbox with escalation; otherwise treat `ConnectionRefused` as sandbox/network isolation, not a Claude task failure.
- Spend Claude tokens carefully. Pass only the smallest useful diff, file excerpt, or log excerpt.
- Keep delegate calls short. Default timeout is 60 seconds; retry at most once after fixing the execution environment.
- Honor `/claude off` and `claude_delegate.py off` for the current machine until turned on again.
- Do not ask Claude to edit files, run live operations, commit, push, deploy, or handle credentials.
- Prefer passing bounded context: a diff, selected files, or a log excerpt.
- Do not pass secrets, tokens, webhooks, passwords, tickets, or private credentials.
- Read Claude's output critically. Apply only changes Codex can defend.
- Keep delegation optional for narrow tasks; use it when independent analysis is likely to improve quality.

## Collaboration Model

- Codex is commander: define task, constraints, context budget, and success criteria.
- Claude is worker: return concise analysis, draft patch, risk list, or verification plan.
- Claude output is not authoritative. Codex decides what to accept.
- Prefer task prompts that ask for one output type: root cause, patch draft, risk review, or comparison.
- Avoid broad prompts like "review everything"; ask specific questions with bounded evidence.
