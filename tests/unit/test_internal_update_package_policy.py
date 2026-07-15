from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_mail_update_installer_verifies_payload_before_apply() -> None:
    source = (ROOT / "scripts" / "install_update_package.ps1").read_text(encoding="utf-8")

    assert "payload_file_manifest.json" in source
    assert "Get-FileHash" in source
    assert "Payload file hash mismatch" in source
    assert "Payload zip hash mismatch" in source
    assert "VerifyOnly" in source
    assert "@(\"jobs\", \"uploads\", \"outputs\", \"logs\")" in source
    assert "config\\\\.*\\.local" in source
    assert "runtime\\\\auth_sessions\\.json" in source
    assert "apply_internal_update.ps1" in source
    assert "Wait-CableTrayAIHealth" in source
    assert "Restore-BackupOverlay" in source
    assert "last_mail_update_apply.json" in source


def test_mail_update_packager_wraps_clean_deployment_payload() -> None:
    source = (ROOT / "scripts" / "package_internal_update.ps1").read_text(encoding="utf-8")

    assert "package_duxyb_intranet_release.ps1" in source
    assert "CableTrayAI_payload.zip" in source
    assert "payload_file_manifest.json" in source
    assert "payload_zip_sha256" in source
    assert "Assert-PayloadSafety" in source
    assert "@(\"jobs\", \"uploads\", \"outputs\", \"logs\")" in source
    assert "config\\\\.*\\.local" in source
    assert "runtime\\\\auth_sessions\\.json" in source
    assert "install_update.ps1" in source
    assert "-VerifyOnly" in source
    assert '"$UpdateZip.sha256.txt"' in source
    assert "update_zip_sha256=$updateZipHash" in source
