# ─────────────────────────────────────────────────────
# OpenSentry MCP Client Setup (Windows)
# Automatically configure AI tools to connect to your
# OpenSentry cameras via the Model Context Protocol.
# ─────────────────────────────────────────────────────

param(
    [Parameter(Position=0)]
    [string]$ApiKey,
    [Parameter(Position=1)]
    [string]$ServerUrl
)

if (-not $ApiKey -or -not $ServerUrl) {
    Write-Host ""
    Write-Host "  Error: Missing arguments" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Usage (local):  .\mcp-setup.ps1 <api_key> <server_url>"
    Write-Host "  Usage (remote): & ([scriptblock]::Create((irm <url>/mcp-setup.ps1))) <api_key> <server_url>"
    Write-Host ""
    Write-Host "  Get your command from the OpenSentry MCP dashboard:"
    Write-Host "  https://opensentry-command.fly.dev/mcp" -ForegroundColor Cyan
    Write-Host ""
    exit 1
}

# ── Header ────────────────────────────────────────────

Write-Host ""
Write-Host "  OpenSentry MCP Setup" -ForegroundColor Green
Write-Host "  Configure AI tools to connect to your cameras" -ForegroundColor DarkGray
Write-Host ""

# ── Detect MCP Clients ────────────────────────────────

$clients = @()

# Claude Code
$claudeCodePath = Join-Path $env:USERPROFILE ".claude.json"
$claudeCodeDetected = (Test-Path $claudeCodePath) -or ($null -ne (Get-Command claude -ErrorAction SilentlyContinue))
$clients += @{
    Name = "Claude Code"
    Path = $claudeCodePath
    Detected = $claudeCodeDetected
}

# Claude Desktop
$claudeDesktopPath = Join-Path $env:APPDATA "Claude\claude_desktop_config.json"
$claudeDesktopDetected = Test-Path (Split-Path $claudeDesktopPath -Parent)
$clients += @{
    Name = "Claude Desktop"
    Path = $claudeDesktopPath
    Detected = $claudeDesktopDetected
}

# Cursor
$cursorPath = Join-Path $env:USERPROFILE ".cursor\mcp.json"
$cursorDetected = Test-Path (Split-Path $cursorPath -Parent)
$clients += @{
    Name = "Cursor"
    Path = $cursorPath
    Detected = $cursorDetected
}

# Windsurf
$windsurfPath = Join-Path $env:USERPROFILE ".codeium\windsurf\mcp_config.json"
$windsurfDetected = Test-Path (Split-Path $windsurfPath -Parent)
$clients += @{
    Name = "Windsurf"
    Path = $windsurfPath
    Detected = $windsurfDetected
}

# ── Display Detected Clients ─────────────────────────

Write-Host "  MCP Clients:" -ForegroundColor White
Write-Host ""

$detectedCount = 0
for ($i = 0; $i -lt $clients.Count; $i++) {
    $c = $clients[$i]
    $num = $i + 1
    if ($c.Detected) {
        Write-Host "    [$num] " -ForegroundColor Green -NoNewline
        Write-Host ([char]0x25CF) -ForegroundColor Green -NoNewline
        Write-Host " $($c.Name)" -ForegroundColor White
        Write-Host "        $($c.Path)" -ForegroundColor DarkGray
        $detectedCount++
    } else {
        Write-Host "    [$num] " -ForegroundColor DarkGray -NoNewline
        Write-Host ([char]0x25CB) -ForegroundColor DarkGray -NoNewline
        Write-Host " $($c.Name)" -ForegroundColor DarkGray
        Write-Host "        $($c.Path) (not found)" -ForegroundColor DarkGray
    }
}

Write-Host ""

if ($detectedCount -eq 0) {
    Write-Host "  No MCP clients detected." -ForegroundColor Yellow
    Write-Host "  You can still configure a client by entering its number." -ForegroundColor DarkGray
    Write-Host ""
}

# ── Prompt for Selection ──────────────────────────────

Write-Host "  Which clients would you like to configure?" -ForegroundColor White
Write-Host "  Enter numbers separated by commas (e.g. 1,3), 'all' for all detected, or 'q' to quit" -ForegroundColor DarkGray
Write-Host ""
$selection = Read-Host "  >"

if ($selection -eq "q" -or $selection -eq "Q") {
    Write-Host ""
    Write-Host "  Setup cancelled." -ForegroundColor DarkGray
    Write-Host ""
    exit 0
}

# Parse selection
$selected = @()
if ($selection -eq "all" -or $selection -eq "ALL") {
    for ($i = 0; $i -lt $clients.Count; $i++) {
        if ($clients[$i].Detected) {
            $selected += $i
        }
    }
    if ($selected.Count -eq 0) {
        Write-Host ""
        Write-Host "  No detected clients to configure." -ForegroundColor Yellow
        Write-Host ""
        exit 0
    }
} else {
    $nums = $selection -split "," | ForEach-Object { $_.Trim() }
    foreach ($num in $nums) {
        $idx = [int]$num - 1
        if ($idx -ge 0 -and $idx -lt $clients.Count) {
            $selected += $idx
        } else {
            Write-Host "  Skipping invalid selection: $num" -ForegroundColor Yellow
        }
    }
}

if ($selected.Count -eq 0) {
    Write-Host ""
    Write-Host "  No valid selections. Exiting." -ForegroundColor Yellow
    Write-Host ""
    exit 0
}

Write-Host ""

# ── Configure Selected Clients ────────────────────────

function Configure-Client {
    param(
        [string]$Name,
        [string]$ConfigPath
    )

    Write-Host "  Configuring $Name..." -ForegroundColor Blue

    # Create parent directory if needed
    $dir = Split-Path $ConfigPath -Parent
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "    Created directory: $dir" -ForegroundColor DarkGray
    }

    # Read existing config
    $config = @{}
    if (Test-Path $ConfigPath) {
        try {
            $content = Get-Content $ConfigPath -Raw -ErrorAction Stop
            if ($content.Trim()) {
                $config = $content | ConvertFrom-Json -AsHashtable -ErrorAction Stop
            }
        } catch {
            # Back up corrupted file
            $backup = "$ConfigPath.bak"
            try {
                Copy-Item $ConfigPath $backup -Force
                Write-Host "    Backed up existing config to $backup" -ForegroundColor DarkGray
            } catch {}
            $config = @{}
        }
    }

    # Ensure mcpServers exists
    if (-not $config.ContainsKey("mcpServers")) {
        $config["mcpServers"] = @{}
    }

    # Add/update OpenSentry entry
    $config["mcpServers"]["opensentry"] = @{
        type = "http"
        url = $ServerUrl
        headers = @{
            Authorization = "Bearer $ApiKey"
        }
    }

    # Write back
    try {
        $json = $config | ConvertTo-Json -Depth 10
        Set-Content -Path $ConfigPath -Value $json -Encoding UTF8
        Write-Host "    Done -> $ConfigPath" -ForegroundColor Green
    } catch {
        Write-Host "    Failed to configure $Name : $_" -ForegroundColor Red
    }

    Write-Host ""
}

foreach ($idx in $selected) {
    $c = $clients[$idx]
    Configure-Client -Name $c.Name -ConfigPath $c.Path
}

# ── Summary ───────────────────────────────────────────

Write-Host "  Setup Complete" -ForegroundColor Green
Write-Host ""
Write-Host "  Your AI tools can now access your OpenSentry cameras." -ForegroundColor DarkGray
Write-Host "  Try asking: `"List my cameras`" or `"Show me what the front door sees`"" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Manage your MCP keys at:" -ForegroundColor DarkGray
$dashUrl = $ServerUrl -replace "/mcp$", "/mcp"
Write-Host "  $dashUrl" -ForegroundColor Cyan
Write-Host ""
