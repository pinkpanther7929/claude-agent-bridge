$ErrorActionPreference = "Stop"

codex plugin marketplace upgrade
codex plugin add claude-agent-bridge@claude-agent-bridge

Write-Host "Updated claude-agent-bridge. Start a new Codex session to load changed MCP tools or skills."
