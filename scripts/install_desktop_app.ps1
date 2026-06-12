param(
    [string]$InstallDir = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$PackageRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $PackageRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogPath = Join-Path $LogDir "install_desktop_app.log"

function Write-InstallLog {
    param([string]$Message)
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
    Write-Host $line
    Add-Content -Encoding UTF8 -Path $LogPath -Value $line
}

function Select-InstallFolder {
    param([string]$InitialPath)
    $fallback = if (Test-Path "D:\") { "D:\CableTrayAI" } else { Join-Path $env:USERPROFILE "CableTrayAI" }
    try {
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
        $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
        $dialog.Description = "Select CableTrayAI install folder"
        $dialog.ShowNewFolderButton = $true
        if ($InitialPath -and (Test-Path $InitialPath)) {
            $dialog.SelectedPath = $InitialPath
        }
        $result = $dialog.ShowDialog()
        if ($result -eq [System.Windows.Forms.DialogResult]::OK -and $dialog.SelectedPath) {
            return $dialog.SelectedPath
        }
    }
    catch {
        Write-InstallLog "Folder dialog unavailable: $($_.Exception.Message)"
    }
    if ($InitialPath) { return $InitialPath }
    return $fallback
}

function Stop-ExistingCableTrayAI {
    Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessName -like "CableTrayAI*" -or $_.Path -like "*CableTrayAI*" } |
        ForEach-Object {
            try {
                Write-InstallLog "Stopping process $($_.ProcessName) pid=$($_.Id)"
                Stop-Process -Id $_.Id -Force -ErrorAction Stop
            }
            catch {
                Write-InstallLog "Warning: could not stop pid=$($_.Id): $($_.Exception.Message)"
            }
        }
}

function Copy-Package {
    param([string]$Destination)
    $sourcePath = (Resolve-Path $PackageRoot).Path.TrimEnd("\")
    $destPath = [System.IO.Path]::GetFullPath($Destination).TrimEnd("\")
    if ($sourcePath.Equals($destPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        Write-InstallLog "Source and destination are the same; skip file copy."
        return
    }
    New-Item -ItemType Directory -Force -Path $destPath | Out-Null

    $excludeNames = @(".git", ".pytest_cache", "__pycache__", "jobs", "uploads", "outputs", "logs")
    $excludeFiles = @("*.pyc", "*.pyo")
    $items = Get-ChildItem -LiteralPath $sourcePath -Force
    foreach ($item in $items) {
        if ($excludeNames -contains $item.Name) { continue }
        if (-not $item.PSIsContainer -and ($excludeFiles | Where-Object { $item.Name -like $_ })) { continue }
        $target = Join-Path $destPath $item.Name
        Copy-Item -LiteralPath $item.FullName -Destination $target -Recurse -Force
    }

}

function Get-PasswordHash {
    param(
        [string]$Username,
        [string]$Password
    )
    $material = [System.Text.Encoding]::UTF8.GetBytes("CableTrayAI:$($Username.Trim().ToLowerInvariant()):$Password")
    $hash = [System.Security.Cryptography.SHA256]::Create().ComputeHash($material)
    return -join ($hash | ForEach-Object { $_.ToString("x2") })
}

function Ensure-AuthLocal {
    param([string]$Root)
    $configDir = Join-Path $Root "config"
    New-Item -ItemType Directory -Force -Path $configDir | Out-Null
    $authLocal = Join-Path $configDir "auth.local.json"
    $users = if ($env:CABLETRAYAI_INITIAL_USERS) {
        @($env:CABLETRAYAI_INITIAL_USERS.Split(",") | ForEach-Object { $_.Trim().ToLowerInvariant() } | Where-Object { $_ })
    } else {
        @("duxyb", "jianghl", "wanggangb")
    }
    $passwordChoice = Resolve-InitialPassword -Root $Root
    if ((Test-Path -LiteralPath $authLocal) -and -not $passwordChoice.fixed_by_deployment) {
        return [ordered]@{ created = $false; path = $authLocal; users = $users }
    }
    if ((Test-Path -LiteralPath $authLocal) -and $passwordChoice.fixed_by_deployment) {
        $backup = "$authLocal.bak_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
        Copy-Item -LiteralPath $authLocal -Destination $backup -Force
    }
    $initialPassword = $passwordChoice.password
    $payload = [ordered]@{
        enabled = $true
        session_ttl_seconds = 43200
        users = @($users | ForEach-Object {
            [ordered]@{ username = $_; password_hash = (Get-PasswordHash -Username $_ -Password $initialPassword) }
        })
    }
    $payload | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 -Path $authLocal
    return [ordered]@{ created = $true; path = $authLocal; users = $users; initial_password = $initialPassword; password_source = $passwordChoice.source }
}

function Resolve-InitialPassword {
    param([string]$Root)
    if ($env:CABLETRAYAI_INITIAL_PASSWORD) {
        return [ordered]@{ password = $env:CABLETRAYAI_INITIAL_PASSWORD.Trim(); source = "environment CABLETRAYAI_INITIAL_PASSWORD"; fixed_by_deployment = $true }
    }
    $packagedPassword = Join-Path $Root "config\initial_password.txt"
    if (Test-Path -LiteralPath $packagedPassword) {
        $value = (Get-Content -LiteralPath $packagedPassword -Raw).TrimStart([char]0xFEFF).Trim()
        if ($value) {
            return [ordered]@{ password = $value; source = "deployment package config/initial_password.txt"; fixed_by_deployment = $true }
        }
    }
    return [ordered]@{ password = [Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(18)).TrimEnd("="); source = "generated random first-install password"; fixed_by_deployment = $false }
}

function Ensure-LoginInfo {
    param(
        [string]$Root,
        [object]$AuthSetup
    )
    $path = Join-Path $Root "CableTrayAI_LOGIN_INFO.txt"
    $AuthSetup["login_info_path"] = $path
    if (-not $AuthSetup["created"] -and (Test-Path -LiteralPath $path)) {
        return $path
    }

    $lines = @(
        "CableTrayAI Login Information",
        "================================",
        "Install folder: $Root",
        "Login URL: http://127.0.0.1:8000/",
        "Users: $($AuthSetup["users"] -join ', ')"
    )
    if ($AuthSetup["created"]) {
        $lines += "Initial password: $($AuthSetup["initial_password"])"
        $lines += "Password status: $($AuthSetup["password_source"])."
    }
    else {
        $lines += "Password status: existing local auth was preserved; reinstall cannot recover the password."
    }
    $lines += "Auth config: $($AuthSetup["path"])"
    $lines += "ANSYS config: $(Join-Path $Root 'config\ansys.local.toml')"
    $lines += ""
    $lines += "Keep this file inside the unit machine. Do not publish, upload, or commit it."
    $lines | Set-Content -Encoding UTF8 -Path $path
    return $path
}

function New-DesktopShortcut {
    param([string]$InstallPath)
    $desktop = [Environment]::GetFolderPath("Desktop")
    $shortcutPath = Join-Path $desktop "CableTrayAI.lnk"
    $exePath = Join-Path $InstallPath "CableTrayAI.exe"
    $cmdPath = Join-Path $InstallPath "START_CABLETRAYAI.cmd"
    $target = if (Test-Path $exePath) { $exePath } else { $cmdPath }
    if (-not (Test-Path $target)) {
        throw "Missing startup entry: CableTrayAI.exe or START_CABLETRAYAI.cmd"
    }
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $target
    $shortcut.WorkingDirectory = $InstallPath
    $shortcut.Description = "CableTrayAI electric cable tray mechanical analysis platform"
    if (Test-Path $exePath) {
        $shortcut.IconLocation = $exePath
    }
    $shortcut.Save()
    return $shortcutPath
}

$defaultInstall = if (Test-Path "D:\") { "D:\CableTrayAI" } else { Join-Path $env:USERPROFILE "CableTrayAI" }
$target = if ($InstallDir) { $InstallDir } else { Select-InstallFolder -InitialPath $defaultInstall }
if (-not $target) {
    throw "No install folder selected."
}

Write-InstallLog "Package root: $PackageRoot"
Write-InstallLog "Install dir : $target"

Stop-ExistingCableTrayAI
Copy-Package -Destination $target
$authSetup = Ensure-AuthLocal -Root $target
$loginInfoPath = Ensure-LoginInfo -Root $target -AuthSetup $authSetup

$shortcutPath = New-DesktopShortcut -InstallPath $target
Write-InstallLog "Desktop shortcut: $shortcutPath"
Write-InstallLog "Login info: $loginInfoPath"

$manifest = [ordered]@{
    status = "pass"
    installed_at = (Get-Date).ToString("s")
    package_root = $PackageRoot
    install_dir = $target
    shortcut = $shortcutPath
    auth_policy = "account_login_only"
    auth_local_path = $authSetup.path
    login_info_path = $authSetup.login_info_path
    auth_local_created = $authSetup.created
    login_users = $authSetup.users
}
if ($authSetup.initial_password) {
    $manifest.initial_password = $authSetup.initial_password
    $manifest.initial_password_notice = "Local first-install password only. Rotate by rewriting config/auth.local.json."
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 -Path (Join-Path $target "install_manifest.json")

Write-InstallLog "Installation completed."
