<#
.SYNOPSIS
    Build an Intune .intunewin package of WritingTools, rebranded as
    "ACNR Intelligence" and preconfigured to use ACNR's internal Ollama server.

.DESCRIPTION
    Downloads the latest WritingTools Windows release, writes a correct
    config.json (native Ollama provider, nested under `providers`) next to the
    exe, bundles the ACNR logo for the shortcut icon, emits install / uninstall
    / detection scripts, and wraps everything into a ready-to-upload
    .intunewin.

    Install is system-wide, per-device (under Program Files). config.json lives
    next to "Writing Tools.exe", which is where the app actually reads it
    (WritingToolApp.py:165). No scheduled task, no APPDATA seed.

.PARAMETER OllamaUrl
    Base URL of the Ollama server. Default: http://192.168.203.100:11434.

.PARAMETER OllamaModel
    Ollama model tag. Default: cogito:32b.

.PARAMETER StagingDir
    Working directory. Default: .\WritingTools-Intune.

.PARAMETER Shortcut
    Global hotkey for the rewrite popup. Default: ctrl+space.

.PARAMETER LogoIco
    Path to a multi-size .ico to use for the Start Menu shortcut. Default:
    ..\branding\logo.ico relative to this script.

.EXAMPLE
    # Uses all ACNR defaults (lab Ollama, cogito:32b, bundled logo):
    .\Build-WritingToolsIntunePackage.ps1
#>
[CmdletBinding()]
param(
    [string]$OllamaUrl   = "http://192.168.203.100:11434",
    [string]$OllamaModel = "cogito:32b",
    [string]$StagingDir  = ".\ACNR-Intelligence-Intune",
    [string]$Shortcut    = "ctrl+space",
    [string]$LogoIco     = (Join-Path $PSScriptRoot "..\branding\logo.ico"),
    # Override the exe source - useful for testing before the first release:
    #   -ZipPath "C:\path\to\ACNR-Intelligence-Windows.zip"
    #   -ZipUrl  "https://.../ACNR-Intelligence-Windows.zip"
    [string]$ZipPath     = "",
    [string]$ZipUrl      = "",
    [string]$Repo        = "squirrelnuttz4u/WritingTools_ollamaFork"
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

$ProductName     = "ACNR Intelligence"
$InstallFolder   = "ACNR Intelligence"   # under %ProgramFiles%

function Write-Log {
    param([string]$Message)
    Write-Host "[$((Get-Date).ToString('HH:mm:ss'))] $Message"
}

# ------------------------------------------------------------------
# 1. Staging
# ------------------------------------------------------------------
$stagingRoot = (Resolve-Path -LiteralPath (New-Item -ItemType Directory -Path $StagingDir -Force)).Path
$sourceDir   = Join-Path $stagingRoot "source"
$appDir      = Join-Path $sourceDir   "app"
$outputDir   = Join-Path $stagingRoot "output"
$null = New-Item -ItemType Directory -Path $sourceDir, $appDir, $outputDir -Force
Write-Log "Staging: $stagingRoot"

# ------------------------------------------------------------------
# 2. Acquire the exe zip: local path, direct URL, or latest release on this fork
# ------------------------------------------------------------------
$headers = @{ "User-Agent" = "ACNR-Intelligence-Packager" }
$zipPath = Join-Path $sourceDir "app.zip"

if ($ZipPath) {
    if (-not (Test-Path -LiteralPath $ZipPath)) { throw "ZipPath not found: $ZipPath" }
    Write-Log "Using local zip: $ZipPath"
    Copy-Item -LiteralPath $ZipPath -Destination $zipPath -Force
}
elseif ($ZipUrl) {
    Write-Log "Downloading from $ZipUrl ..."
    Invoke-WebRequest -Uri $ZipUrl -OutFile $zipPath -Headers $headers
}
else {
    Write-Log "Querying GitHub for latest $Repo release..."
    try {
        $release = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest" -Headers $headers
    } catch {
        throw "Failed to query $Repo releases. No release published yet? Push a 'v*' tag to trigger the build workflow, or pass -ZipPath/-ZipUrl. Original error: $($_.Exception.Message)"
    }

    $asset = $release.assets | Where-Object {
        $_.name -like "ACNR-Intelligence-Windows*.zip" -or
        $_.name -like "ACNR*Windows*.zip"
    } | Select-Object -First 1

    if (-not $asset) {
        throw "No ACNR-Intelligence-Windows*.zip asset in release '$($release.tag_name)'. Available: $($release.assets.name -join ', ')"
    }

    Write-Log "Found asset: $($asset.name) ($([math]::Round($asset.size / 1MB, 1)) MB)"
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zipPath -Headers $headers
}

Expand-Archive -Path $zipPath -DestinationPath $appDir -Force
Remove-Item $zipPath -Force

# Flatten if the zip extracted into a nested folder.
$exe = Get-ChildItem -Path $appDir -Recurse -Filter "ACNR Intelligence.exe" | Select-Object -First 1
if (-not $exe) { throw "ACNR Intelligence.exe not found under $appDir." }
if ($exe.DirectoryName -ne $appDir) {
    $nested = $exe.Directory.FullName
    Get-ChildItem -LiteralPath $nested -Force | ForEach-Object {
        Move-Item -LiteralPath $_.FullName -Destination $appDir -Force
    }
    Remove-Item -LiteralPath $nested -Recurse -Force
}

# ------------------------------------------------------------------
# 3. config.json - native Ollama provider, nested shape, next to exe
# ------------------------------------------------------------------
$providerName = "Ollama (For Experts)"
$configObj = [ordered]@{
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
$configPath = Join-Path $appDir "config.json"
$configObj | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $configPath -Encoding UTF8
Write-Log "Wrote config.json next to ACNR Intelligence.exe (provider=$providerName)"

# ------------------------------------------------------------------
# 4. Copy branding .ico next to the exe
# ------------------------------------------------------------------
$logoStaged = Join-Path $appDir "acnr.ico"
if (Test-Path -LiteralPath $LogoIco) {
    Copy-Item -LiteralPath $LogoIco -Destination $logoStaged -Force
    Write-Log "Bundled logo: $LogoIco"
} else {
    Write-Log "WARNING: LogoIco not found at $LogoIco - shortcut will fall back to exe icon."
    $logoStaged = $null
}

# ------------------------------------------------------------------
# 5. install / uninstall / detection scripts
# ------------------------------------------------------------------
# Build install.ps1 as an expandable here-string so the product name,
# install folder, and logo flag are baked in at package time.
$logoFlag = if ($logoStaged) { "true" } else { "false" }

$installScript = @"
# install.ps1 - runs as SYSTEM via Intune
`$ErrorActionPreference = "Stop"

`$installDir    = Join-Path `$env:ProgramFiles "$InstallFolder"
`$productName   = "$ProductName"
`$haveLogo      = `$$logoFlag

if (Test-Path -LiteralPath `$installDir) {
    Remove-Item -LiteralPath `$installDir -Recurse -Force -ErrorAction SilentlyContinue
}
`$null = New-Item -ItemType Directory -Path `$installDir -Force

# Copy everything from the package root into the install dir except these scripts.
`$skip = @("install.ps1", "uninstall.ps1", "detection.ps1")
Get-ChildItem -LiteralPath `$PSScriptRoot -Force | Where-Object { `$skip -notcontains `$_.Name } | ForEach-Object {
    Copy-Item -LiteralPath `$_.FullName -Destination `$installDir -Recurse -Force
}

# All-users Start Menu shortcut.
`$exePath = Join-Path `$installDir "ACNR Intelligence.exe"
`$iconPath = if (`$haveLogo) { Join-Path `$installDir "acnr.ico" } else { `$exePath + ",0" }
`$shortcutPath = Join-Path `$env:ProgramData "Microsoft\Windows\Start Menu\Programs\`$productName.lnk"
`$shell = New-Object -ComObject WScript.Shell
`$link = `$shell.CreateShortcut(`$shortcutPath)
`$link.TargetPath       = `$exePath
`$link.WorkingDirectory = `$installDir
`$link.IconLocation     = `$iconPath
`$link.Description      = "`$productName - internal AI writing assistant"
`$link.Save()

# Detection marker
Set-Content -LiteralPath (Join-Path `$installDir ".installed") -Value (Get-Date -Format o) -Encoding UTF8
exit 0
"@

$uninstallScript = @"
# uninstall.ps1
`$ErrorActionPreference = "SilentlyContinue"

`$installDir    = Join-Path `$env:ProgramFiles "$InstallFolder"
`$shortcutPath  = Join-Path `$env:ProgramData "Microsoft\Windows\Start Menu\Programs\$ProductName.lnk"

Get-Process -Name "ACNR Intelligence" -ErrorAction SilentlyContinue | Stop-Process -Force
Remove-Item -LiteralPath `$installDir -Recurse -Force
Remove-Item -LiteralPath `$shortcutPath -Force
exit 0
"@

$detectionScript = @"
# detection.ps1 - Intune custom detection (exit 0 = installed)
`$marker = Join-Path `$env:ProgramFiles "$InstallFolder\.installed"
if (Test-Path -LiteralPath `$marker) { exit 0 } else { exit 1 }
"@

Set-Content -LiteralPath (Join-Path $appDir "install.ps1")   -Value $installScript   -Encoding UTF8
Set-Content -LiteralPath (Join-Path $appDir "uninstall.ps1") -Value $uninstallScript -Encoding UTF8
Set-Content -LiteralPath (Join-Path $appDir "detection.ps1") -Value $detectionScript -Encoding UTF8
Write-Log "Wrote install/uninstall/detection scripts."

# ------------------------------------------------------------------
# 6. IntuneWinAppUtil
# ------------------------------------------------------------------
$toolPath = Join-Path $stagingRoot "IntuneWinAppUtil.exe"
if (-not (Test-Path -LiteralPath $toolPath)) {
    Write-Log "Downloading IntuneWinAppUtil.exe..."
    Invoke-WebRequest `
        -Uri "https://github.com/microsoft/Microsoft-Win32-Content-Prep-Tool/raw/master/IntuneWinAppUtil.exe" `
        -OutFile $toolPath
}

Write-Log "Running IntuneWinAppUtil..."
& $toolPath -c $appDir -s "install.ps1" -o $outputDir -q
if ($LASTEXITCODE -ne 0) { throw "IntuneWinAppUtil.exe failed with exit code $LASTEXITCODE." }

$intunewin = Get-ChildItem -LiteralPath $outputDir -Filter "*.intunewin" | Select-Object -First 1
if (-not $intunewin) { throw "No .intunewin produced in $outputDir." }

# ------------------------------------------------------------------
# 7. Summary
# ------------------------------------------------------------------
Write-Host ""
Write-Host "==============================================================="
Write-Host "  $ProductName package built"
Write-Host "  File:  $($intunewin.FullName)"
Write-Host "  Size:  $([math]::Round($intunewin.Length / 1MB, 1)) MB"
Write-Host "==============================================================="
Write-Host ""
Write-Host "Intune > Apps > Windows > Add > Windows app (Win32):"
Write-Host ""
Write-Host "  Name:              $ProductName"
Write-Host "  Publisher:         American Consolidated Natural Resources, Inc."
Write-Host "  Install command:   powershell.exe -NoProfile -ExecutionPolicy Bypass -File install.ps1"
Write-Host "  Uninstall command: powershell.exe -NoProfile -ExecutionPolicy Bypass -File uninstall.ps1"
Write-Host "  Detection:         Custom script -> detection.ps1"
Write-Host "  Install behavior:  System"
Write-Host ""
Write-Host "Baked config:"
Write-Host "  api_base:   $($OllamaUrl.TrimEnd('/'))"
Write-Host "  api_model:  $OllamaModel"
Write-Host "  shortcut:   $Shortcut"
Write-Host ""
