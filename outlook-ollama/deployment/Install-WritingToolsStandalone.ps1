<#
.SYNOPSIS
    Install ACNR Intelligence (branded WritingTools) on your own Windows box
    for immediate local testing against an internal Ollama server. No admin,
    no Intune, no Docker.

.DESCRIPTION
    Fetches the latest WritingTools Windows release from GitHub, extracts it
    into $env:LOCALAPPDATA\ACNRIntelligence, writes a config.json pointing at
    the specified Ollama server using the native Ollama provider, bundles the
    ACNR logo as the shortcut icon, creates Start Menu + Desktop shortcuts
    named "ACNR Intelligence", and optionally launches the app.

    Defaults are hardcoded for the current ACNR test environment:
        OllamaUrl   = http://192.168.203.100:11434
        OllamaModel = cogito:32b
        LogoIco     = ..\branding\logo.ico (relative to this script)
    Just run the script with no arguments.

.EXAMPLE
    # Quick test against the hardcoded ACNR lab Ollama server:
    .\Install-WritingToolsStandalone.ps1

.EXAMPLE
    # Different server / model:
    .\Install-WritingToolsStandalone.ps1 -OllamaUrl "http://10.0.0.5:11434" -OllamaModel "llama3.1:8b"

.EXAMPLE
    # Reinstall over an existing install without prompting:
    .\Install-WritingToolsStandalone.ps1 -Force

.NOTES
    Uninstall:  remove $env:LOCALAPPDATA\ACNRIntelligence and the two shortcuts.
    Config is kept next to Writing Tools.exe (which is where the app looks).
#>
[CmdletBinding()]
param(
    [string]$OllamaUrl   = "http://192.168.203.100:11434",
    [string]$OllamaModel = "cogito:32b",
    [string]$InstallDir  = (Join-Path $env:LOCALAPPDATA "ACNRIntelligence"),
    [string]$Shortcut    = "ctrl+space",
    [string]$LogoIco     = (Join-Path $PSScriptRoot "..\branding\logo.ico"),
    [switch]$Force,
    [switch]$NoLaunch
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

$ProductName = "ACNR Intelligence"

function Write-Log {
    param([string]$Message)
    Write-Host "[$((Get-Date).ToString('HH:mm:ss'))] $Message"
}

# ------------------------------------------------------------------
# 1. Handle existing install
# ------------------------------------------------------------------
if (Test-Path -LiteralPath $InstallDir) {
    $existingExe = Join-Path $InstallDir "Writing Tools.exe"
    if ((Test-Path -LiteralPath $existingExe) -and -not $Force) {
        Write-Host ""
        Write-Host "$ProductName already installed at: $InstallDir"
        $answer = Read-Host "Overwrite existing install? [y/N]"
        if ($answer -notmatch '^(y|yes)$') {
            Write-Host "Aborted. Use -Force to skip this prompt."
            exit 1
        }
    }
    # Kill any running instance so files aren't locked.
    Get-Process -Name "Writing Tools" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $InstallDir -Recurse -Force
}
$null = New-Item -ItemType Directory -Path $InstallDir -Force
Write-Log "Install dir: $InstallDir"

# ------------------------------------------------------------------
# 2. Download latest release
# ------------------------------------------------------------------
Write-Log "Querying GitHub for latest WritingTools release..."
$ghHeaders = @{ "User-Agent" = "WritingTools-Standalone-Installer" }
$release = Invoke-RestMethod -Uri "https://api.github.com/repos/theJayTea/WritingTools/releases/latest" -Headers $ghHeaders

$asset = $release.assets | Where-Object {
    $_.name -like "Writing.Tool.Windows*.zip" -or
    $_.name -like "Writing Tool Windows*.zip" -or
    $_.name -like "WritingTools-Windows*.zip" -or
    $_.name -like "*Windows*.zip"
} | Select-Object -First 1

if (-not $asset) {
    throw "No Windows zip asset in release $($release.tag_name). Available: $($release.assets.name -join ', ')"
}

$tempZip = Join-Path $env:TEMP ("writingtools-" + [guid]::NewGuid() + ".zip")
Write-Log "Downloading $($asset.name) ($([math]::Round($asset.size / 1MB, 1)) MB)..."
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $tempZip -Headers $ghHeaders

Write-Log "Extracting..."
Expand-Archive -Path $tempZip -DestinationPath $InstallDir -Force
Remove-Item -LiteralPath $tempZip -Force

# Flatten a single nested folder (e.g. "Writing Tools/Writing Tools.exe").
$exe = Get-ChildItem -LiteralPath $InstallDir -Recurse -Filter "Writing Tools.exe" | Select-Object -First 1
if (-not $exe) {
    throw "Writing Tools.exe not found after extract."
}
if ($exe.DirectoryName -ne $InstallDir) {
    Write-Log "Flattening nested folder: $($exe.DirectoryName)"
    $nested = $exe.Directory.FullName
    Get-ChildItem -LiteralPath $nested -Force | ForEach-Object {
        Move-Item -LiteralPath $_.FullName -Destination $InstallDir -Force
    }
    Remove-Item -LiteralPath $nested -Recurse -Force
}

# ------------------------------------------------------------------
# 3. Write config.json next to the exe
# ------------------------------------------------------------------
$providerName = "Ollama (For Experts)"
$config = [ordered]@{
    provider  = $providerName
    shortcut  = $Shortcut
    theme     = "gradient"
    providers = [ordered]@{
        $providerName = [ordered]@{
            api_base   = $OllamaUrl.TrimEnd('/')
            api_model  = $OllamaModel
            keep_alive = "5"
        }
    }
}

$configPath = Join-Path $InstallDir "config.json"
$config | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $configPath -Encoding UTF8
Write-Log "Wrote config: $configPath"

# ------------------------------------------------------------------
# 3b. Bundle the logo next to the exe so the shortcut icon survives moves.
# ------------------------------------------------------------------
$iconTarget = $null
if ($LogoIco -and (Test-Path -LiteralPath $LogoIco)) {
    $iconTarget = Join-Path $InstallDir "acnr.ico"
    Copy-Item -LiteralPath $LogoIco -Destination $iconTarget -Force
    Write-Log "Bundled logo: $LogoIco"
} else {
    Write-Log "No logo.ico found - shortcut will use the exe's default icon."
}

# ------------------------------------------------------------------
# 4. Start Menu + Desktop shortcuts (per-user, no admin)
# ------------------------------------------------------------------
$startMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$null = New-Item -ItemType Directory -Path $startMenuDir -Force
$shortcutPaths = @(
    (Join-Path $startMenuDir "$ProductName.lnk"),
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "$ProductName.lnk")
)

$shell = New-Object -ComObject WScript.Shell
$exePath = Join-Path $InstallDir "Writing Tools.exe"
$iconLocation = if ($iconTarget) { $iconTarget } else { "$exePath,0" }
foreach ($path in $shortcutPaths) {
    $link = $shell.CreateShortcut($path)
    $link.TargetPath       = $exePath
    $link.WorkingDirectory = $InstallDir
    $link.IconLocation     = $iconLocation
    $link.Description      = "$ProductName - internal AI writing assistant"
    $link.Save()
}
Write-Log "Created '$ProductName' Start Menu + Desktop shortcuts."

# ------------------------------------------------------------------
# 5. Sanity check: can the config reach Ollama?
# ------------------------------------------------------------------
try {
    Write-Log "Testing Ollama connectivity at $OllamaUrl ..."
    $tagsUrl = $OllamaUrl.TrimEnd('/') + "/api/tags"
    $tags = Invoke-RestMethod -Uri $tagsUrl -TimeoutSec 5
    $modelNames = $tags.models | ForEach-Object { $_.name }
    if ($modelNames -contains $OllamaModel) {
        Write-Log "  [OK] Reachable, model '$OllamaModel' is present."
    } else {
        Write-Log "  [WARN] Reachable, but model '$OllamaModel' not in tag list."
        Write-Log "         Available: $($modelNames -join ', ')"
        Write-Log "         Pull it with: ollama pull $OllamaModel"
    }
} catch {
    Write-Log "  [WARN] Could not reach $OllamaUrl : $($_.Exception.Message)"
    Write-Log "         Install will still complete - fix network/server, then relaunch."
}

# ------------------------------------------------------------------
# 6. Summary + launch
# ------------------------------------------------------------------
Write-Host ""
Write-Host "==========================================================="
Write-Host "  $ProductName installed."
Write-Host "  Location:  $InstallDir"
Write-Host "  Ollama:    $OllamaUrl"
Write-Host "  Model:     $OllamaModel"
Write-Host "  Hotkey:    $Shortcut"
Write-Host "==========================================================="
Write-Host ""
Write-Host "Select some text anywhere, press $Shortcut, pick an action."
Write-Host "To uninstall: delete $InstallDir and the two shortcuts."
Write-Host ""

if (-not $NoLaunch) {
    Write-Log "Launching $ProductName..."
    Start-Process -FilePath $exePath -WorkingDirectory $InstallDir
}
