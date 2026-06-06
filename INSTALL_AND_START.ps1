param(
    [string]$TargetRoot = "",
    [string]$PublicIp = "",
    [switch]$PreserveAnsysConfig,
    [switch]$SkipFirewall
)

$ErrorActionPreference = "Stop"

function Select-InstallFolder {
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = "请选择 CableTrayAI 正式部署目录"
    $dialog.ShowNewFolderButton = $true
    if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
        throw "Install folder was not selected."
    }
    return $dialog.SelectedPath
}

function Get-PreferredPublicIp {
    param([string]$Requested)
    if (-not [string]::IsNullOrWhiteSpace($Requested)) {
        return $Requested
    }
    $addresses = @()
    try {
        $addresses = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
            Where-Object {
                $_.IPAddress -and
                $_.IPAddress -notlike "127.*" -and
                $_.IPAddress -notlike "169.254.*" -and
                $_.IPAddress -ne "0.0.0.0"
            } |
            Select-Object -ExpandProperty IPAddress
    }
    catch {
        $addresses = @()
    }
    $tenNet = $addresses | Where-Object { $_ -like "10.*" } | Select-Object -First 1
    if ($tenNet) {
        return $tenNet
    }
    $first = $addresses | Select-Object -First 1
    if ($first) {
        return $first
    }
    return "10.102.15.203"
}

function Wait-Health {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 70
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastError = ""
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return @{ ok = $true; error = "" }
            }
        }
        catch {
            $lastError = $_.Exception.Message
        }
        Start-Sleep -Seconds 2
    }
    return @{ ok = $false; error = $lastError }
}

$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($TargetRoot)) {
    $TargetRoot = Select-InstallFolder
}
$TargetRoot = [System.IO.Path]::GetFullPath($TargetRoot)
$PublicIp = Get-PreferredPublicIp $PublicIp

Write-Host "============================================================"
Write-Host "CableTrayAI one-click deployment and start"
Write-Host "Package root: $PackageRoot"
Write-Host "Target root : $TargetRoot"
Write-Host "Public URL  : http://$PublicIp`:8000/"
Write-Host "============================================================"

New-Item -ItemType Directory -Force -Path $TargetRoot | Out-Null

$excludeNames = @(
    ".git",
    ".pytest_cache",
    ".pytest_tmp",
    "jobs",
    "outputs",
    "uploads",
    "source_materials",
    "logs"
)

$sameRoot = [System.IO.Path]::GetFullPath($PackageRoot).TrimEnd("\") -ieq [System.IO.Path]::GetFullPath($TargetRoot).TrimEnd("\")
if (-not $sameRoot) {
    Get-ChildItem -LiteralPath $PackageRoot -Force | ForEach-Object {
        if ($excludeNames -contains $_.Name) {
            return
        }
        $dst = Join-Path $TargetRoot $_.Name
        if ($_.PSIsContainer) {
            Copy-Item -LiteralPath $_.FullName -Destination $dst -Recurse -Force
        }
        else {
            Copy-Item -LiteralPath $_.FullName -Destination $dst -Force
        }
    }
}

foreach ($dir in @("source_materials", "jobs", "uploads", "outputs", "docs", "logs", "config")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $TargetRoot $dir) | Out-Null
}

$aiConfig = Join-Path $TargetRoot "config\ai.local.toml"
$aiExample = Join-Path $TargetRoot "config\ai.local.example.toml"
if (-not (Test-Path $aiConfig) -and (Test-Path $aiExample)) {
    Copy-Item -LiteralPath $aiExample -Destination $aiConfig -Force
    Write-Host "AI model config initialized from config\ai.local.example.toml"
}

if ($PreserveAnsysConfig -and (Test-Path (Join-Path $TargetRoot "config\ansys.local.toml"))) {
    Write-Host "Preserving existing config\ansys.local.toml"
}
elseif (Test-Path (Join-Path $TargetRoot "scripts\find_ansys.ps1")) {
    Write-Host "Finding ANSYS Mechanical APDL, preferred version 18.2 / v182 ..."
    $findArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $TargetRoot "scripts\find_ansys.ps1"), "-PreferredVersion", "182", "-AllowFallback")
    powershell @findArgs
}

if (-not $SkipFirewall) {
    try {
        netsh advfirewall firewall add rule name="CableTrayAI 8000" dir=in action=allow protocol=TCP localport=8000 | Out-Null
    }
    catch {
        Write-Host "Firewall rule was not added. Continue startup and check manually if LAN clients cannot open the page."
    }
}

$serverScript = Join-Path $TargetRoot "scripts\start_internal_server.ps1"
if (-not (Test-Path $serverScript)) {
    throw "Missing start script: $serverScript"
}

$logDir = Join-Path $TargetRoot "logs"
$serverLog = Join-Path $logDir "internal_server.log"
$serverErr = Join-Path $logDir "internal_server.err.log"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

Write-Host "Starting CableTrayAI web service in background ..."
$argLine = "-NoProfile -ExecutionPolicy Bypass -File `"$serverScript`" -HostAddress 0.0.0.0 -Port 8000 -PublicIp `"$PublicIp`""
Start-Process powershell -WorkingDirectory $TargetRoot -WindowStyle Minimized -ArgumentList $argLine -RedirectStandardOutput $serverLog -RedirectStandardError $serverErr | Out-Null

$health = Wait-Health "http://127.0.0.1:8000/health" 75
$deployRecord = [ordered]@{
    status = if ($health.ok) { "pass" } else { "fail" }
    target_root = $TargetRoot
    public_url = "http://$PublicIp`:8000/"
    local_url = "http://127.0.0.1:8000/"
    server_log = $serverLog
    server_err_log = $serverErr
    health_error = $health.error
    did_not_execute_ansys = $true
    started_at = (Get-Date).ToString("s")
}
$deployRecord | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $TargetRoot "docs\last_one_click_deploy.json")

if (-not $health.ok) {
    Write-Host ""
    Write-Host "CableTrayAI web service did not start."
    Write-Host "Health URL failed: http://127.0.0.1:8000/health"
    Write-Host "Server log: $serverLog"
    Write-Host "Error log : $serverErr"
    if (Test-Path $serverErr) {
        Write-Host ""
        Write-Host "Last error log lines:"
        Get-Content -Path $serverErr -Tail 40 -ErrorAction SilentlyContinue
    }
    throw "CableTrayAI web service failed to start."
}

Write-Host ""
Write-Host "CableTrayAI is running:"
Write-Host "  Local : http://127.0.0.1:8000/"
Write-Host "  LAN   : http://$PublicIp`:8000/"
Write-Host "  AI QC : http://127.0.0.1:8000/ai-tools"
Write-Host ""
Write-Host "Opening browser ..."
Start-Process "http://127.0.0.1:8000/"
