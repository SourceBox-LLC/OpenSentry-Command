# -----------------------------------------------------
# SourceBox Sentry MCP Client Setup (Windows)
# Automatically configure AI tools to connect to your
# SourceBox Sentry cameras via the Model Context Protocol.
# -----------------------------------------------------

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
    Write-Host "  Get your command from the SourceBox Sentry MCP dashboard:"
    Write-Host "  https://opensentry-command.fly.dev/mcp" -ForegroundColor Cyan
    Write-Host ""
    exit 1
}

# -- Header --------------------------------------------

Write-Host ""
Write-Host "  SourceBox Sentry MCP Setup" -ForegroundColor Green
Write-Host "  Configure AI tools to connect to your cameras" -ForegroundColor DarkGray
Write-Host ""

# -- Helpers -------------------------------------------

# Tracks clients we refused to touch because they were running. Listed at the
# end so the user knows exactly which ones to quit and re-run for.
$script:SkippedClients = @()

# Process names to check per client. Claude Desktop ships a bundled Claude Code
# experience so the same `Claude.exe` process touches `.claude.json` too --
# detecting Claude.exe covers both client rows. A separate `claude` CLI (npm
# install) runs as a node process and we can't reliably fingerprint it, so the
# "Quit Claude Code before continuing" warning still has to carry that case.
$script:ClientProcesses = @{
    'Claude Code'    = @('Claude')
    'Claude Desktop' = @('Claude')
    'Cursor'         = @('Cursor')
    'Windsurf'       = @('Windsurf')
}

# Returns the PID of a running matching process, or $null. Returns $null when
# the env var OPENSENTRY_MCP_ALLOW_RUNNING=1 is set -- tests set that so they
# can run even while a real Claude Desktop is up on the dev machine.
function Test-ClientRunning {
    param([string]$ClientName)
    if ($env:OPENSENTRY_MCP_ALLOW_RUNNING -eq "1") { return $null }
    $names = $script:ClientProcesses[$ClientName]
    if (-not $names) { return $null }
    foreach ($n in $names) {
        $proc = Get-Process -Name $n -ErrorAction SilentlyContinue
        if ($proc) { return $proc[0].Id }
    }
    return $null
}

# Recursively convert ConvertFrom-Json output (PSCustomObject / arrays /
# primitives) into hashtables/arrays we can mutate. Works on PowerShell 5.1+ --
# we deliberately DON'T use ConvertFrom-Json -AsHashtable because that flag was
# only added in PowerShell 6.0 and silently throws on 5.1.
function ConvertTo-OscHashtable($obj) {
    if ($null -eq $obj) { return $null }
    if ($obj -is [System.Collections.IDictionary]) {
        $h = [ordered]@{}
        foreach ($k in $obj.Keys) { $h[$k] = ConvertTo-OscHashtable $obj[$k] }
        return $h
    }
    if ($obj -is [pscustomobject]) {
        $h = [ordered]@{}
        foreach ($p in $obj.PSObject.Properties) {
            $h[$p.Name] = ConvertTo-OscHashtable $p.Value
        }
        return $h
    }
    # Arrays -- but NOT strings, which PS treats as char-iterable.
    if ($obj -is [System.Collections.IEnumerable] -and -not ($obj -is [string])) {
        return @($obj | ForEach-Object { ConvertTo-OscHashtable $_ })
    }
    return $obj
}

# -- Detect MCP Clients --------------------------------

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

# -- Display Detected Clients -------------------------

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

# -- Warning: quit target apps ------------------------

Write-Host "  Important:" -ForegroundColor Yellow
Write-Host "  Quit Claude Code / Claude Desktop / Cursor / Windsurf before continuing." -ForegroundColor DarkGray
Write-Host "  Running clients may overwrite config changes while the setup is writing." -ForegroundColor DarkGray
Write-Host ""

# -- Prompt for Selection ------------------------------

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

# -- Configure Selected Clients ------------------------

function Configure-Client {
    param(
        [string]$Name,
        [string]$ConfigPath
    )

    Write-Host "  Configuring $Name..." -ForegroundColor Blue

    # Refuse to touch the config if the target client is currently running --
    # its own file-watcher will clobber our write with stale in-memory state.
    # That's exactly what happened in the original bug: a correctly-written
    # config got stomped back to defaults (and our mcpServers entry erased)
    # within a second of the write.
    $runningPid = Test-ClientRunning -ClientName $Name
    if ($runningPid) {
        Write-Host "    $Name is currently running (pid $runningPid)." -ForegroundColor Yellow
        Write-Host "    Skipping -- quit $Name completely and re-run this script." -ForegroundColor Yellow
        Write-Host "    Your config was NOT modified." -ForegroundColor DarkGray
        Write-Host ""
        $script:SkippedClients += $Name
        return
    }

    # Create parent directory if needed
    $dir = Split-Path $ConfigPath -Parent
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "    Created directory: $dir" -ForegroundColor DarkGray
    }

    # Read + parse existing config. If the file exists and is non-empty but
    # unparseable, we ABORT rather than clobber -- losing an existing
    # .claude.json full of session state is catastrophic.
    $config = $null
    if (Test-Path $ConfigPath) {
        $content = $null
        try {
            $content = Get-Content $ConfigPath -Raw -ErrorAction Stop
        } catch {
            Write-Host "    Failed to read $ConfigPath : $_" -ForegroundColor Red
            Write-Host "    Skipping $Name -- your file was not modified." -ForegroundColor Yellow
            Write-Host ""
            return
        }

        if ($content -and $content.Trim()) {
            try {
                $parsed = $content | ConvertFrom-Json -ErrorAction Stop
                $config = ConvertTo-OscHashtable $parsed
            } catch {
                Write-Host "    Could not parse $ConfigPath as JSON." -ForegroundColor Red
                Write-Host "    Error: $($_.Exception.Message)" -ForegroundColor DarkGray
                Write-Host "    Skipping $Name to avoid overwriting your existing data." -ForegroundColor Yellow
                Write-Host "    Fix the file manually (or delete it) and re-run." -ForegroundColor DarkGray
                Write-Host ""
                return
            }
        } else {
            $config = [ordered]@{}
        }
    } else {
        $config = [ordered]@{}
    }

    # Ensure mcpServers exists (preserving any other entries already there).
    if (-not $config.Contains("mcpServers") -or $null -eq $config["mcpServers"]) {
        $config["mcpServers"] = [ordered]@{}
    }

    # Add/update SourceBox Sentry entry.
    $config["mcpServers"]["opensentry"] = [ordered]@{
        type = "http"
        url = $ServerUrl
        headers = [ordered]@{
            Authorization = "Bearer $ApiKey"
        }
    }

    # ALWAYS back up the file before we overwrite it -- even when parsing
    # succeeded, because a disk write can fail halfway through.
    if (Test-Path $ConfigPath) {
        $backup = "$ConfigPath.bak"
        try {
            Copy-Item $ConfigPath $backup -Force
            Write-Host "    Backed up existing config to $backup" -ForegroundColor DarkGray
        } catch {
            Write-Host "    Warning: could not create backup at $backup : $_" -ForegroundColor Yellow
        }
    }

    # Write back. Use -Depth 100 -- Claude Code configs contain deeply nested
    # project state that truncates silently at the default depth of 2.
    #
    # Write UTF-8 *without* a BOM: PowerShell 5.1's `Set-Content -Encoding UTF8`
    # prepends a byte-order mark, and Claude Desktop's JSON parser rejects it
    # with "Unexpected token ''... is not valid JSON". Using .NET directly
    # behaves the same on PS 5.1 and 7+.
    try {
        $json = $config | ConvertTo-Json -Depth 100
        $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
        [System.IO.File]::WriteAllText($ConfigPath, $json, $utf8NoBom)
        Write-Host "    Done -> $ConfigPath" -ForegroundColor Green
    } catch {
        Write-Host "    Failed to configure $Name : $_" -ForegroundColor Red
        Write-Host "    Your backup is at $ConfigPath.bak" -ForegroundColor DarkGray
    }

    Write-Host ""
}

foreach ($idx in $selected) {
    $c = $clients[$idx]
    Configure-Client -Name $c.Name -ConfigPath $c.Path
}

# -- Summary -------------------------------------------

if ($script:SkippedClients.Count -gt 0) {
    Write-Host "  Skipped (still running):" -ForegroundColor Yellow
    foreach ($s in $script:SkippedClients) {
        Write-Host "    * $s" -ForegroundColor Yellow
    }
    Write-Host ""
    Write-Host "  Quit the above and re-run this script to configure them." -ForegroundColor DarkGray
    Write-Host ""
}

Write-Host "  Setup Complete" -ForegroundColor Green
Write-Host ""
Write-Host "  Your AI tools can now access your SourceBox Sentry cameras." -ForegroundColor DarkGray
Write-Host "  Restart the clients you configured so they pick up the new MCP server." -ForegroundColor DarkGray
Write-Host "  Try asking: `"List my cameras`" or `"Show me what the front door sees`"" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Manage your MCP keys at:" -ForegroundColor DarkGray
$dashUrl = $ServerUrl -replace "/mcp$", "/mcp"
Write-Host "  $dashUrl" -ForegroundColor Cyan
Write-Host ""
