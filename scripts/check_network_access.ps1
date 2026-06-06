param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Continue"

function Get-LocalAddress {
    try {
        $items = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
            Where-Object {
                $_.IPAddress -and
                $_.IPAddress -notlike "127.*" -and
                $_.IPAddress -notlike "169.254.*" -and
                $_.IPAddress -ne "0.0.0.0"
            } |
            Select-Object -ExpandProperty IPAddress
        $preferred = $items | Where-Object { $_ -like "10.*" } | Select-Object -First 1
        if ($preferred) { return $preferred }
        $first = $items | Select-Object -First 1
        if ($first) { return $first }
    }
    catch {
    }
    return "10.102.15.203"
}

function Test-Url {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 5
        return @{
            url = $Url
            status = "pass"
            code = $response.StatusCode
            error = ""
        }
    }
    catch {
        return @{
            url = $Url
            status = "fail"
            code = 0
            error = $_.Exception.Message
        }
    }
}

$ip = Get-LocalAddress
$results = @(
    (Test-Url "http://127.0.0.1:$Port/health"),
    (Test-Url "http://$ip`:$Port/health")
)

Write-Host "============================================================"
Write-Host "CableTrayAI network access check"
Write-Host "Local URL : http://127.0.0.1:$Port/"
Write-Host "LAN URL   : http://$ip`:$Port/"
Write-Host "============================================================"

foreach ($item in $results) {
    Write-Host "$($item.status)  $($item.url)  code=$($item.code)  $($item.error)"
}

New-Item -ItemType Directory -Force -Path "docs" | Out-Null
$payload = [ordered]@{
    checked_at = (Get-Date).ToString("s")
    port = $Port
    server_ip = $ip
    results = $results
    guidance = @(
        "If 127.0.0.1 passes but LAN fails, ask IT to allow inbound TCP 8000 on this computer.",
        "If both fail, start CableTrayAI first with START_CABLETRAYAI.cmd or START_NO_POWERSHELL.cmd.",
        "If the page returns forbidden JSON, add the client IP to config/access_control.local.json or the web permissions panel."
    )
}
$payload | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 "docs\network_access_check.json"

Write-Host ""
Write-Host "Report written: docs\network_access_check.json"
