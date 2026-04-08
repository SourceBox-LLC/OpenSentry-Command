# OpenSentry CloudNode Installer for Windows
# Usage: irm https://opensentry-command.fly.dev/install.ps1 | iex

$ErrorActionPreference = "Stop"

$Repo = "SourceBox-LLC/opensentry-cloud-node"
$InstallDir = if ($env:OPENSENTRY_INSTALL_DIR) { $env:OPENSENTRY_INSTALL_DIR } else { "$env:LOCALAPPDATA\OpenSentry" }

Write-Host ""
Write-Host "  OpenSentry CloudNode Installer" -ForegroundColor Green
Write-Host "  ================================" -ForegroundColor DarkGray
Write-Host ""

# ── Detect architecture ────────────────────────────────────────────
$Arch = if ([Environment]::Is64BitOperatingSystem) { "x86_64" } else { "x86" }

Write-Host "  Platform:  windows-$Arch" -ForegroundColor Cyan
Write-Host "  Install:   $InstallDir" -ForegroundColor Cyan
Write-Host ""

# ── Try downloading pre-built binary ───────────────────────────────
$LatestUrl = "https://api.github.com/repos/$Repo/releases/latest"

Write-Host "  Checking for pre-built release..." -ForegroundColor DarkGray

$DownloadUrl = $null
$ReleaseTag = $null

try {
    $Release = Invoke-RestMethod -Uri $LatestUrl -ErrorAction Stop
    $ReleaseTag = $Release.tag_name

    $Asset = $Release.assets | Where-Object {
        $_.name -match "windows" -and $_.name -match $Arch
    } | Select-Object -First 1

    if ($Asset) {
        $DownloadUrl = $Asset.browser_download_url
    }
} catch {
    # No release found, will fall back to source build
}

if ($DownloadUrl) {
    Write-Host "  Found release $ReleaseTag" -ForegroundColor Green
    Write-Host "  Downloading..." -ForegroundColor DarkGray

    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    $TmpFile = Join-Path $env:TEMP "opensentry-cloudnode-download"

    try {
        Invoke-WebRequest -Uri $DownloadUrl -OutFile $TmpFile -UseBasicParsing

        if ($DownloadUrl -match "\.zip$") {
            Expand-Archive -Path $TmpFile -DestinationPath $InstallDir -Force
        } else {
            Copy-Item $TmpFile "$InstallDir\opensentry-cloudnode.exe" -Force
        }

        Remove-Item $TmpFile -Force -ErrorAction SilentlyContinue
        Write-Host "  Downloaded successfully." -ForegroundColor Green
    } catch {
        Write-Host "  Download failed. Falling back to source build..." -ForegroundColor Yellow
        $DownloadUrl = $null
    }
}

# ── Fall back to building from source ──────────────────────────────
if (-not $DownloadUrl) {
    Write-Host "  No pre-built binary available. Building from source..." -ForegroundColor Yellow
    Write-Host ""

    # Check for git
    $HasGit = Get-Command git -ErrorAction SilentlyContinue
    $HasCargo = Get-Command cargo -ErrorAction SilentlyContinue

    if (-not $HasGit -or -not $HasCargo) {
        if (-not $HasCargo) {
            Write-Host "  Missing: Rust toolchain" -ForegroundColor Red
            Write-Host "  Install:  https://rustup.rs" -ForegroundColor Cyan
        }
        if (-not $HasGit) {
            Write-Host "  Missing: git" -ForegroundColor Red
            Write-Host "  Install:  winget install Git.Git" -ForegroundColor Cyan
        }
        Write-Host ""
        exit 1
    }

    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    $CloneDir = "$InstallDir\source"

    if (Test-Path "$CloneDir\.git") {
        Write-Host "  Updating existing source..." -ForegroundColor DarkGray
        git -C $CloneDir pull --quiet 2>$null
    } else {
        Write-Host "  Cloning repository..." -ForegroundColor DarkGray
        git clone --quiet "https://github.com/$Repo.git" $CloneDir
    }

    Write-Host "  Building (this may take a few minutes)..." -ForegroundColor DarkGray
    Push-Location $CloneDir
    cargo build --release --quiet
    Pop-Location

    Copy-Item "$CloneDir\target\release\opensentry-cloudnode.exe" "$InstallDir\opensentry-cloudnode.exe" -Force
    Write-Host "  Build complete." -ForegroundColor Green
}

# ── Check for ffmpeg ───────────────────────────────────────────────
Write-Host ""
$HasFFmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue

if ($HasFFmpeg) {
    $FFmpegVersion = (ffmpeg -version 2>&1 | Select-Object -First 1) -replace '.*version\s+(\S+).*', '$1'
    Write-Host "  ffmpeg:    $FFmpegVersion (installed)" -ForegroundColor Green
} else {
    Write-Host "  ffmpeg:    not found" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  CloudNode requires ffmpeg for video processing." -ForegroundColor Yellow
    Write-Host "  Install:  winget install ffmpeg" -ForegroundColor Cyan
    Write-Host "       or:  https://ffmpeg.org/download.html" -ForegroundColor Cyan
}

# ── Add to PATH for current session ───────────────────────────────
if ($env:PATH -notlike "*$InstallDir*") {
    $env:PATH = "$InstallDir;$env:PATH"
}

# ── Done ──────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  CloudNode installed successfully." -ForegroundColor Green
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor White
Write-Host ""
Write-Host "  1. Run setup:        $InstallDir\opensentry-cloudnode.exe setup" -ForegroundColor Cyan
Write-Host "  2. Start streaming:  $InstallDir\opensentry-cloudnode.exe" -ForegroundColor Cyan
Write-Host ""

# Check if install dir is in user PATH permanently
$UserPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($UserPath -notlike "*$InstallDir*") {
    Write-Host "  Tip: Add to PATH permanently:" -ForegroundColor DarkGray
    Write-Host "  [Environment]::SetEnvironmentVariable('PATH', `"$InstallDir;`$env:PATH`", 'User')" -ForegroundColor Cyan
    Write-Host ""
}

Write-Host "  Get your API key at https://opensentry-command.fly.dev" -ForegroundColor DarkGray
Write-Host ""
