param(
    [int]$Port = 8000,
    [string]$ExpectedIp = "10.102.15.203"
)

$ErrorActionPreference = "Continue"

function Get-LocalIPv4 {
    $items = @()
    if (Get-Command Get-NetIPAddress -ErrorAction SilentlyContinue) {
        $items = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -and $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
            ForEach-Object { $_.IPAddress }
    }
    if (-not $items -or $items.Count -eq 0) {
        $items = [System.Net.Dns]::GetHostAddresses([System.Net.Dns]::GetHostName()) |
            Where-Object { $_.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork } |
            ForEach-Object { $_.IPAddressToString } |
            Where-Object { $_ -notlike "127.*" -and $_ -notlike "169.254.*" }
    }
    return @($items | Select-Object -Unique)
}

function Test-Http {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 4
        return [ordered]@{ url = $Url; status = "pass"; code = $response.StatusCode }
    }
    catch {
        return [ordered]@{ url = $Url; status = "fail"; error = $_.Exception.Message }
    }
}

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
New-Item -ItemType Directory -Force -Path "docs" | Out-Null

$ips = @(Get-LocalIPv4)
$selectedIp = if ($ips -contains $ExpectedIp) { $ExpectedIp } elseif (($ips | Where-Object { $_ -like "10.*" } | Select-Object -First 1)) { ($ips | Where-Object { $_ -like "10.*" } | Select-Object -First 1) } elseif ($ips.Count) { $ips[0] } else { $ExpectedIp }
$localUrl = "http://127.0.0.1:$Port/"
$publicUrl = "http://$selectedIp`:$Port/"
$expectedUrl = "http://$ExpectedIp`:$Port/"

$listeners = @()
if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
    $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object LocalAddress, LocalPort, OwningProcess)
}

$firewallRule = ""
try {
    $firewallRule = (& netsh advfirewall firewall show rule name="CableTrayAI Web $Port" 2>&1) -join "`n"
}
catch {
    $firewallRule = $_.Exception.Message
}

$checks = @(
    (Test-Http -Url $localUrl),
    (Test-Http -Url $publicUrl)
)
if ($ExpectedIp -ne $selectedIp) {
    $checks += (Test-Http -Url $expectedUrl)
}

$payload = [ordered]@{
    status = if (($checks | Where-Object { $_.status -eq "pass" }).Count -gt 0) { "diagnosed" } else { "service_not_reachable" }
    root = $root
    port = $Port
    expected_ip = $ExpectedIp
    detected_ips = $ips
    selected_public_ip = $selectedIp
    listeners = $listeners
    checks = $checks
    firewall_rule_text = $firewallRule
    guidance = @(
        "If 127.0.0.1 works but the 10.x.x.x URL fails from other computers, the service is running and the blocker is Windows firewall, security software, VLAN routing, or unit network policy.",
        "Run this script as administrator, or ask IT to allow inbound TCP $Port on the deployment computer.",
        "If the browser shows forbidden JSON, add the client IP in config/access_control.local.json or from the web permission panel.",
        "If neither local nor public URL works, restart START_NO_POWERSHELL.cmd or INSTALL_AND_START.ps1 and inspect logs/internal_server.err.log."
    )
    checked_at = (Get-Date).ToString("s")
}

$jsonPath = "docs/intranet_access_diagnosis.json"
$payload | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $jsonPath

Write-Host "============================================================"
Write-Host "CableTrayAI intranet access diagnosis"
Write-Host "Root        : $root"
Write-Host "Detected IP : $($ips -join ', ')"
Write-Host "Local URL   : $localUrl"
Write-Host "Public URL  : $publicUrl"
Write-Host "Report      : $jsonPath"
Write-Host "============================================================"
Write-Host ""
foreach ($check in $checks) {
    if ($check.status -eq "pass") {
        Write-Host "[PASS] $($check.url) code=$($check.code)"
    }
    else {
        Write-Host "[FAIL] $($check.url) $($check.error)"
    }
}
Write-Host ""
Write-Host "If local URL passes but other computers cannot open the public URL, ask IT to allow inbound TCP $Port."
Write-Host "If the page says forbidden, add that client IP to the whitelist."
