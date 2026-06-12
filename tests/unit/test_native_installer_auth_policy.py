from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_native_installer_generates_local_auth_without_committed_password() -> None:
    source = (ROOT / "scripts" / "CableTrayAIInstaller.cs").read_text(encoding="utf-8")

    assert "EnsureAuthLocal" in source
    assert "auth.local.json" in source
    assert "CABLETRAYAI_INITIAL_PASSWORD" in source
    assert "config\", \"initial_password.txt" in source
    assert "BackupExistingAuthLocal" in source
    assert "initial_password" in source
    assert "CableTrayAI_LOGIN_INFO.txt" in source
    assert "login_info_path" in source
    assert "CABLETRAYAI_CLEAN_PREVIOUS_REGISTERED_INSTALL" in source
    assert "Previous registered install cleanup skipped by default" in source
    assert "CABLETRAYAI_RESET_RUNTIME_DATA" in source
    assert "PasswordHash(username, initialPassword)" in source
    assert '"CableTrayAI_Installer.exe"' in source
    assert "cnpe123" not in source.lower()


def test_release_packager_avoids_libreoffice_python_for_gate() -> None:
    source = (ROOT / "scripts" / "package_duxyb_intranet_release.ps1").read_text(encoding="utf-8")

    assert "Resolve-PackagePython" in source
    assert "CABLETRAYAI_PACKAGE_PYTHON" in source
    assert "$source -match 'LibreOffice'" in source
    assert "deployment_package_gate.py" in source
    assert '[string]$InitialPassword = "cnpe123"' in source
    assert "config\\initial_password.txt" in source
    assert "initial_password_policy" in source
    assert "Remove-GeneratedPythonCaches" in source
    assert "__pycache__" in source
    assert '".pyc"' in source
    assert "Remove-GeneratedPythonCaches -Path $PackageDir" in source
    assert "UTF8Encoding($false)" in source
    assert "[System.IO.File]::WriteAllText($initialPasswordPath" in source


def test_fallback_installers_honor_packaged_initial_password() -> None:
    python_source = (ROOT / "scripts" / "install_desktop_app.py").read_text(encoding="utf-8")
    ps_source = (ROOT / "scripts" / "install_desktop_app.ps1").read_text(encoding="utf-8")
    native_source = (ROOT / "scripts" / "CableTrayAIInstaller.cs").read_text(encoding="utf-8")

    assert "resolve_initial_password" in python_source
    assert "initial_password.txt" in python_source
    assert "utf-8-sig" in python_source
    assert ".bak_" in python_source
    assert "Resolve-InitialPassword" in ps_source
    assert "initial_password.txt" in ps_source
    assert "TrimStart([char]0xFEFF)" in ps_source
    assert ".bak_" in ps_source
    assert "TrimStart('\\uFEFF')" in native_source


def test_python_installer_strips_bom_from_packaged_initial_password(tmp_path, monkeypatch) -> None:
    from scripts.install_desktop_app import password_hash, resolve_initial_password

    monkeypatch.delenv("CABLETRAYAI_INITIAL_PASSWORD", raising=False)
    config = tmp_path / "config"
    config.mkdir()
    (config / "initial_password.txt").write_bytes(b"\xef\xbb\xbfcnpe123\r\n")

    password, source, fixed = resolve_initial_password(tmp_path)

    assert password == "cnpe123"
    assert fixed is True
    assert source == "deployment package config/initial_password.txt"
    assert password_hash("duxyb", password) == "45b2c902176b6064c5867523cb86a781337a2433b51d884aa6d8850a249b79a4"
