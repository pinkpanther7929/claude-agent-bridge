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

`claude_status` also reports whether the local `claude` executable can be found
and queried for its version. Delegation runs Claude Code in non-interactive
print mode (`claude -p`) so Codex can capture stdout, but it now injects the
`claude-reviewer` custom agent with `--agents` and selects it with `--agent`.
Use `--no-agent` only for troubleshooting.

## Install Into Any Repo

### Codex CLI Plugin Install

For Codex CLI, add this repository as a marketplace first, then install the plugin
from that marketplace:

```powershell
codex plugin marketplace add https://github.com/pinkpanther7929/claude-agent-bridge
codex plugin add claude-agent-bridge@claude-agent-bridge
```

`codex plugin add claude-agent-bridge@https://github.com/...` does not work
because `plugin add` expects `plugin@marketplace-name`, not a Git URL.

The repository root is a marketplace. The plugin package lives under
`plugins/claude-agent-bridge`.

After install, open a new Codex session. The plugin manifest contributes the
Claude MCP server automatically; no separate setup script is required for normal
plugin use.

Update later with:

```powershell
codex plugin marketplace upgrade
codex plugin add claude-agent-bridge@claude-agent-bridge
```

Or from a local clone:

```powershell
.\scripts\update-codex.ps1
```

Start a new Codex session after updating so changed MCP tools and skills are
loaded.

### Codex Config Fallback

Use this only when you want to register the MCP server directly in
`~/.codex/config.toml` without using the plugin system:

```powershell
git clone https://github.com/pinkpanther7929/claude-agent-bridge D:\claude-agent-bridge
cd D:\claude-agent-bridge
.\scripts\install-codex.ps1
```

Restart Codex after registration. Codex will start the MCP server automatically.

### VS Code UI

For VS Code Agent Plugin source install, point the UI at the plugin package
folder:

1. Open the Command Palette.
2. Run `Chat: Install Plugin From Source`.
3. Enter or select `plugins/claude-agent-bridge` from a local clone.
4. Open a new chat/workspace session after the plugin installs.

The plugin contributes the `claude_delegate` MCP server and starts it with the
current workspace as the default working directory.

For one-off local setup without installing a plugin, use the Command Palette
flow `MCP: Add Server`, choose a stdio server, and point it at:

```text
python -X utf8 <path-to-this-repo>/mcp/claude_mcp_server.py
```

### Scripted Setup

Clone this bridge once, then install it into any repo/workspace with one command:

```powershell
git clone https://github.com/pinkpanther7929/claude-agent-bridge D:\claude-agent-bridge
python D:\claude-agent-bridge\scripts\install_mcp_config.py D:\your-repo
```

```bash
git clone https://github.com/pinkpanther7929/claude-agent-bridge ~/claude-agent-bridge
python ~/claude-agent-bridge/scripts/install_mcp_config.py ~/your-repo
```

The installer creates or updates `<your-repo>/.mcp.json` and preserves existing
MCP servers. If `claude_delegate` already exists with different settings, pass
`--force` to replace only that server entry. The file is written as UTF-8 without
a BOM so JSON parsers can read it reliably.

Open a new Codex session from `D:\your-repo` after installing. The Claude tools
will use that repo as their default workspace, including diff review and saved
outputs under `.tmp/claude_delegate`.

Dry-run and JSON output are available for automation:

```powershell
python D:\claude-agent-bridge\scripts\install_mcp_config.py D:\your-repo --dry-run --json
```

## Local Checks

```powershell
python -m py_compile scripts\claude_delegate.py scripts\install_mcp_config.py mcp\claude_mcp_server.py
python -X utf8 -m json.tool .agents\plugins\marketplace.json
python -X utf8 -m json.tool plugins\claude-agent-bridge\.mcp.json
powershell.exe -NoProfile -File scripts\install-codex.ps1 -ConfigPath .tmp\codex-test.toml
python -m unittest discover -s tests
python scripts\claude_delegate.py status --json
python scripts\claude_delegate.py --prompt "Build prompt only." --dry-run --json
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
