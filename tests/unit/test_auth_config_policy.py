from __future__ import annotations

import json

from core.security.auth import password_hash, verify_credentials


def test_auth_has_no_committed_default_credentials(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    assert not verify_credentials("duxyb", "configured-locally")


def test_auth_uses_local_config_credentials(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    password = "local-only-password"
    (config_dir / "auth.local.json").write_text(
        json.dumps(
            {
                "enabled": True,
                "users": [
                    {
                        "username": "operator",
                        "password_hash": password_hash("operator", password),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert verify_credentials("operator", password)
    assert not verify_credentials("operator", "wrong-password")
