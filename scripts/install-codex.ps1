param(
  [string]$RepoPath = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
  [string]$ConfigPath = (Join-Path $HOME ".codex\config.toml")
)

$ErrorActionPreference = "Stop"

$configDir = Split-Path -Parent $ConfigPath
if (-not (Test-Path -LiteralPath $configDir)) {
  New-Item -ItemType Directory -Path $configDir | Out-Null
}

if (-not (Test-Path -LiteralPath $ConfigPath)) {
  New-Item -ItemType File -Path $ConfigPath | Out-Null
}

$existing = Get-Content -LiteralPath $ConfigPath -Raw
$escapedRepoPath = $RepoPath -replace "'", "''"

$serverBlock = @"

[mcp_servers.claude_agent_bridge]
command = 'python'
args = ['-X', 'utf8', 'mcp\claude_mcp_server.py']
cwd = '$escapedRepoPath'
startup_timeout_sec = 30
"@

$pattern = "(?ms)^\[mcp_servers\.claude_agent_bridge\]\r?\n.*?(?=^\[|\z)"
if ($existing -match $pattern) {
  $updated = [regex]::Replace($existing, $pattern, $serverBlock.TrimStart(), 1)
  Set-Content -LiteralPath $ConfigPath -Value $updated -Encoding UTF8
  Write-Host "Updated Codex MCP server: claude_agent_bridge"
}
else {
  Add-Content -LiteralPath $ConfigPath -Value $serverBlock
  Write-Host "Registered Codex MCP server: claude_agent_bridge"
}

Write-Host "Restart Codex to load it."
