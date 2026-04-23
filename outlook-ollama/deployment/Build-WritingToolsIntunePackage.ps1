<#
.SYNOPSIS
    Build an Intune .intunewin package for WritingTools preseeded with your
    internal Ollama configuration.

.DESCRIPTION
    Downloads the latest WritingTools Windows release from GitHub, writes a
    config.template.json pointing at your Ollama endpoint, emits install /
    uninstall / detection scripts, and wraps everything up via
    IntuneWinAppUtil.exe into a ready-to-upload .intunewin.

.PARAMETER OllamaUrl
    Base URL of the Ollama server (e.g. https://llm.corp.example.com).

.PARAMETER OllamaModel
    Ollama model tag to use (e.g. llama3.1:8b).

.PARAMETER StagingDir
    Working directory (default .\WritingTools-Intune).

.PARAMETER ApiKey
    Bearer key (WritingTools requires a non-empty key field; Ollama ignores it).

.PARAMETER Shortcut
    WritingTools global hotkey (default ctrl+space).

.EXAMPLE
    .\Build-WritingToolsIntunePackage.ps1 -OllamaUrl "https://llm.corp.example.com" -OllamaModel "llama3.1:8b"
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OllamaUrl,

    [Parameter(Mandatory = $true)]
    [string]$OllamaModel,

    [string]$StagingDir = ".\WritingTools-Intune",

    [string]$ApiKey = "ollama",

    [string]$Shortcut = "ctrl+space"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Write-Log {
    param([string]$Message)
    $ts = (Get-Date).ToString("HH:mm:ss")
    Write-Host "[$ts] $Message"
}

# ------------------------------------------------------------------
# 1. Staging directories
# ------------------------------------------------------------------
$stagingRoot = (Resolve-Path -LiteralPath (New-Item -ItemType Directory -Path $StagingDir -Force)).Path
$sourceDir   = Join-Path $stagingRoot "source"
$appDir      = Join-Path $sourceDir   "app"
$outputDir   = Join-Path $stagingRoot "output"
$null = New-Item -ItemType Directory -Path $sourceDir, $appDir, $outputDir -Force
Write-Log "Staging: $stagingRoot"

# ------------------------------------------------------------------
# 2. Find latest WritingTools Windows release
# ------------------------------------------------------------------
Write-Log "Querying GitHub for latest WritingTools release..."
$headers = @{ "User-Agent" = "WritingTools-IntunePackager" }
$release = Invoke-RestMethod -Uri "https://api.github.com/repos/theJayTea/WritingTools/releases/latest" -Headers $headers

$asset = $release.assets | Where-Object {
    $_.name -like "Writing.Tool.Windows*.zip" -or
    $_.name -like "Writing Tool Windows*.zip" -or
    $_.name -like "WritingTools-Windows*.zip" -or
    $_.name -like "*Windows*.zip"
} | Select-Object -First 1

if (-not $asset) {
    throw "Could not find a Windows zip asset in release '$($release.tag_name)'. Available: $($release.assets.name -join ', ')"
}
Write-Log "Found asset: $($asset.name) ($([math]::Round($asset.size / 1MB, 1)) MB)"

# ------------------------------------------------------------------
# 3. Download + extract
# ------------------------------------------------------------------
$zipPath = Join-Path $sourceDir "app.zip"
Write-Log "Downloading $($asset.browser_download_url)..."
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zipPath -Headers $headers

Write-Log "Extracting..."
Expand-Archive -Path $zipPath -DestinationPath $appDir -Force
Remove-Item $zipPath -Force

# If the exe is nested inside a single subfolder, flatten.
$exe = Get-ChildItem -Path $appDir -Recurse -Filter "Writing Tools.exe" | Select-Object -First 1
if (-not $exe) {
    throw "Writing Tools.exe not found under $appDir."
}
if ($exe.DirectoryName -ne $appDir) {
    Write-Log "Flattening nested folder: $($exe.DirectoryName)"
    $nested = $exe.Directory
    Get-ChildItem -LiteralPath $nested.FullName -Force | ForEach-Object {
        Move-Item -LiteralPath $_.FullName -Destination $appDir -Force
    }
    Remove-Item -LiteralPath $nested.FullName -Recurse -Force
}

# ------------------------------------------------------------------
# 4. Write config template
# ------------------------------------------------------------------
$systemPrompt = "You are a concise, professional writing assistant. Improve clarity, grammar, and tone without changing meaning. Output only the rewritten text."

$config = [ordered]@{
    provider      = "OpenAI Compatible"
    api_key       = $ApiKey
    api_base      = ($OllamaUrl.TrimEnd('/') + "/v1")
    model_name    = $OllamaModel
    shortcut      = $Shortcut
    theme         = "gradient"
    streaming     = $true
    system_prompt = $systemPrompt
}
$configPath = Join-Path $appDir "config.template.json"
$config | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $configPath -Encoding UTF8
Write-Log "Wrote config template: $configPath"

# ------------------------------------------------------------------
# 5. Emit install / uninstall / detection scripts
# ------------------------------------------------------------------
$installScript = @'
# install.ps1 - runs as SYSTEM via Intune
$ErrorActionPreference = "Stop"

$installDir = Join-Path $env:ProgramFiles "WritingTools"
$dataDir    = Join-Path $env:ProgramData "WritingTools"
$null = New-Item -ItemType Directory -Path $installDir, $dataDir -Force

# Copy everything except the three management scripts.
$skip = @("install.ps1", "uninstall.ps1", "detection.ps1")
Get-ChildItem -LiteralPath $PSScriptRoot -Force | Where-Object { $skip -notcontains $_.Name } | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $installDir -Recurse -Force
}

# All-users Start Menu shortcut.
$shortcutPath = Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs\Writing Tools.lnk"
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($shortcutPath)
$link.TargetPath = Join-Path $installDir "Writing Tools.exe"
$link.WorkingDirectory = $installDir
$link.IconLocation = (Join-Path $installDir "Writing Tools.exe") + ",0"
$link.Save()

# Per-user seed-config script: copies config.template.json -> %APPDATA%\Writing Tools\config.json on first login.
$seedScript = @"
`$ErrorActionPreference = 'SilentlyContinue'
`$dest = Join-Path `$env:APPDATA 'Writing Tools'
`$destFile = Join-Path `$dest 'config.json'
if (-not (Test-Path `$destFile)) {
    New-Item -ItemType Directory -Path `$dest -Force | Out-Null
    Copy-Item -LiteralPath '$installDir\config.template.json' -Destination `$destFile -Force
}
"@
$seedPath = Join-Path $dataDir "seed-config.ps1"
Set-Content -LiteralPath $seedPath -Value $seedScript -Encoding UTF8

# Scheduled task that runs the seed script at each user logon.
$taskName = "WritingTools-SeedConfig"
$action   = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$seedPath`""
$trigger  = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -GroupId "S-1-5-32-545" -RunLevel Limited
$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null

# Detection marker
Set-Content -LiteralPath (Join-Path $installDir ".installed") -Value (Get-Date -Format o) -Encoding UTF8
exit 0
'@

$uninstallScript = @'
# uninstall.ps1
$ErrorActionPreference = "SilentlyContinue"

$taskName = "WritingTools-SeedConfig"
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$installDir   = Join-Path $env:ProgramFiles "WritingTools"
$dataDir      = Join-Path $env:ProgramData "WritingTools"
$shortcutPath = Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs\Writing Tools.lnk"

Remove-Item -LiteralPath $installDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $dataDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $shortcutPath -Force -ErrorAction SilentlyContinue
exit 0
'@

$detectionScript = @'
# detection.ps1 - Intune custom detection (exit 0 = installed, exit 1 = missing)
$marker = Join-Path $env:ProgramFiles "WritingTools\.installed"
if (Test-Path -LiteralPath $marker) { exit 0 } else { exit 1 }
'@

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
if ($LASTEXITCODE -ne 0) {
    throw "IntuneWinAppUtil.exe failed with exit code $LASTEXITCODE."
}

$intunewin = Get-ChildItem -LiteralPath $outputDir -Filter "*.intunewin" | Select-Object -First 1
if (-not $intunewin) {
    throw "No .intunewin produced in $outputDir."
}

# ------------------------------------------------------------------
# 7. Summary
# ------------------------------------------------------------------
Write-Host ""
Write-Host "================================================================"
Write-Host "  Package built: $($intunewin.FullName)"
Write-Host "  Size:          $([math]::Round($intunewin.Length / 1MB, 1)) MB"
Write-Host "================================================================"
Write-Host ""
Write-Host "Intune > Apps > Windows > Add > Windows app (Win32):"
Write-Host ""
Write-Host "  Install command:   powershell.exe -NoProfile -ExecutionPolicy Bypass -File install.ps1"
Write-Host "  Uninstall command: powershell.exe -NoProfile -ExecutionPolicy Bypass -File uninstall.ps1"
Write-Host "  Detection:         Custom script -> detection.ps1"
Write-Host "  Install behavior:  System"
Write-Host ""
Write-Host "Baked config:"
Write-Host "  api_base:   $($OllamaUrl.TrimEnd('/'))/v1"
Write-Host "  model_name: $OllamaModel"
Write-Host "  shortcut:   $Shortcut"
Write-Host ""
