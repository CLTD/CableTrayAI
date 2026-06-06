param(
    [switch]$NoRestart
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Port = 8000

Set-Location $Root

$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($existing -and -not $NoRestart) {
    foreach ($conn in $existing) {
        $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
        if ($proc -and $proc.ProcessName -match "python|uvicorn") {
            Stop-Process -Id $proc.Id -Force
        }
    }
    Start-Sleep -Seconds 1
    $existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
}

if (-not $existing) {
    Start-Process powershell -WindowStyle Hidden -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        "Set-Location '$Root'; python -m uvicorn apps.api.app.main:app --host 127.0.0.1 --port $Port"
    )
    Start-Sleep -Seconds 2
}

$url = "http://127.0.0.1:$Port/"
Write-Host "电缆桥架智能力学分析平台:"
Write-Host $url
