$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$runtimeTarget = Join-Path $Root "runtime\CableTrayAI_Installer"

Remove-Item $runtimeTarget -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $runtimeTarget | Out-Null

$cscCandidates = @(
    "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
    "$env:WINDIR\Microsoft.NET\Framework\v4.0.30319\csc.exe",
    "$env:WINDIR\Microsoft.NET\Framework64\v3.5\csc.exe",
    "$env:WINDIR\Microsoft.NET\Framework\v3.5\csc.exe"
)
$csc = $cscCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $csc) {
    throw "Cannot find .NET Framework C# compiler csc.exe. The installer runtime cannot be built."
}

$source = Join-Path $Root "scripts\CableTrayAIInstaller.cs"
if (-not (Test-Path $source)) {
    throw "Missing installer source: $source"
}

$exe = Join-Path $runtimeTarget "CableTrayAI_Installer.exe"
$compileArgs = @(
    "/nologo",
    "/target:winexe",
    "/platform:anycpu",
    "/optimize+",
    "/out:$exe",
    "/reference:System.Windows.Forms.dll",
    "/reference:System.Drawing.dll",
    $source
)

& $csc @compileArgs
if ($LASTEXITCODE -ne 0) {
    throw "C# installer build failed with exit code $LASTEXITCODE"
}

if (-not (Test-Path $exe)) {
    throw "CableTrayAI_Installer.exe was not created."
}

$manifest = [ordered]@{
    status = "pass"
    runtime = "runtime\CableTrayAI_Installer\CableTrayAI_Installer.exe"
    mode = "native_windows_installer"
    compiler = $csc
    note = "Double-click the installer, select a local installation folder, and use the desktop CableTrayAI shortcut after installation. This installer does not depend on Python, PowerShell execution policy, Tk, or Tcl."
    created_at = (Get-Date).ToString("s")
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $Root "runtime\installer_runtime_manifest.json")

Write-Host "Installer runtime created:"
Write-Host (Join-Path $runtimeTarget "CableTrayAI_Installer.exe")
