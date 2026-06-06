param(
    [string]$HostAddress = "0.0.0.0",
    [int]$Port = 8000,
    [string]$PublicIp = "10.102.15.203",
    [string]$Python = "python",
    [switch]$PreferPortableRuntime = $true
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$env:NO_COLOR = "1"
$env:PYTHONIOENCODING = "utf-8"

New-Item -ItemType Directory -Force -Path "docs", "logs", "config" | Out-Null

function Write-StartRecord {
    param(
        [string]$Status,
        [string]$Runner,
        [string]$Message
    )
    $payload = [ordered]@{
        status = $Status
        runner = $Runner
        public_url = "http://$PublicIp`:$Port/"
        local_url = "http://127.0.0.1`:$Port/"
        bind = "$HostAddress`:$Port"
        message = $Message
        started_at = (Get-Date).ToString("s")
        note = "Run this script on the intranet server. Other computers open the public_url in a browser."
    }
    $payload | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 "docs\internal_server_last_start.json"
}

$portable = Join-Path $Root "runtime\CableTrayAI_Server\CableTrayAI_Server.exe"
if ($PreferPortableRuntime -and (Test-Path $portable)) {
    Write-StartRecord "starting" "portable_exe" "Starting bundled CableTrayAI portable web runtime."
    Write-Host "CableTrayAI intranet server"
    Write-Host "Runner: portable runtime"
    Write-Host "Bind: $HostAddress`:$Port"
    Write-Host "Open locally: http://127.0.0.1`:$Port/"
    Write-Host "Open from intranet: http://$PublicIp`:$Port/"
    Write-Host ""
    Write-Host "Press Ctrl+C to stop."
    & $portable --root $Root --host $HostAddress --port $Port --public-ip $PublicIp
    exit $LASTEXITCODE
}

Write-StartRecord "starting" "python_uvicorn" "Starting with Python. This requires fastapi and uvicorn on the machine."
Write-Host "CableTrayAI intranet server"
Write-Host "Runner: Python uvicorn"
Write-Host "Bind: $HostAddress`:$Port"
Write-Host "Open locally: http://127.0.0.1`:$Port/"
Write-Host "Open from intranet: http://$PublicIp`:$Port/"
Write-Host ""
Write-Host "Press Ctrl+C to stop."

& $Python -m uvicorn apps.api.app.main:app --host $HostAddress --port $Port --no-access-log --no-use-colors
