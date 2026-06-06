from __future__ import annotations

import hashlib
import json
import secrets
import time
from pathlib import Path
from typing import Any


COOKIE_NAME = "cabletrayai_session"
SESSION_TTL_SECONDS = 12 * 60 * 60

AUTH_CONFIG_PATH = Path("config/auth.local.json")
AUTH_EXAMPLE_PATH = Path("config/auth.example.json")
SESSION_STORE_PATH = Path("runtime/auth_sessions.json")


DEFAULT_USERS: dict[str, str] = {}


def password_hash(username: str, password: str) -> str:
    material = f"CableTrayAI:{username.strip().lower()}:{password}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def default_auth_config() -> dict[str, Any]:
    return {
        "enabled": True,
        "session_ttl_seconds": SESSION_TTL_SECONDS,
        "users": [
            {"username": username, "password_hash": digest}
            for username, digest in DEFAULT_USERS.items()
        ],
    }


def load_auth_config() -> dict[str, Any]:
    for path in (AUTH_CONFIG_PATH, AUTH_EXAMPLE_PATH):
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
                if isinstance(payload, dict):
                    return {**default_auth_config(), **payload}
            except Exception:
                continue
    return default_auth_config()


def auth_enabled() -> bool:
    return bool(load_auth_config().get("enabled", True))


def verify_credentials(username: str, password: str) -> bool:
    normalized = (username or "").strip().lower()
    if not normalized or password is None:
        return False
    expected = {
        str(item.get("username", "")).strip().lower(): str(item.get("password_hash", "")).strip().lower()
        for item in load_auth_config().get("users", [])
        if isinstance(item, dict)
    }
    return secrets.compare_digest(password_hash(normalized, password), expected.get(normalized, ""))


def _read_sessions() -> dict[str, Any]:
    if not SESSION_STORE_PATH.exists():
        return {}
    try:
        payload = json.loads(SESSION_STORE_PATH.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _write_sessions(payload: dict[str, Any]) -> None:
    SESSION_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SESSION_STORE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def create_session(username: str, client_ip: str = "") -> dict[str, Any]:
    now = time.time()
    ttl = int(load_auth_config().get("session_ttl_seconds") or SESSION_TTL_SECONDS)
    token = secrets.token_urlsafe(32)
    session = {
        "username": username.strip().lower(),
        "client_ip": client_ip,
        "created_at": now,
        "expires_at": now + max(ttl, 300),
    }
    sessions = {
        key: value
        for key, value in _read_sessions().items()
        if isinstance(value, dict) and float(value.get("expires_at", 0)) > now
    }
    sessions[token] = session
    _write_sessions(sessions)
    return {"token": token, **session}


def get_session(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    sessions = _read_sessions()
    session = sessions.get(token)
    if not isinstance(session, dict):
        return None
    if float(session.get("expires_at", 0)) <= time.time():
        sessions.pop(token, None)
        _write_sessions(sessions)
        return None
    return {**session, "token": token}


def delete_session(token: str | None) -> None:
    if not token:
        return
    sessions = _read_sessions()
    if token in sessions:
        sessions.pop(token, None)
        _write_sessions(sessions)


def public_auth_path(path: str) -> bool:
    normalized = path or "/"
    return normalized in {"/login", "/auth/login", "/auth/logout", "/auth/session", "/health", "/favicon.ico"}
