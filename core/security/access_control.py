from __future__ import annotations

import ipaddress
import json
import re
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


LOCAL_CONFIG = Path("config/access_control.local.json")
EXAMPLE_CONFIG = Path("config/access_control.example.json")
DEFAULT_SERVER_IP = "10.102.15.203"
DEFAULT_ALLOWED_IPS = ["10.102.15.110", "10.102.15.102", "10.102.15.105"]
ALWAYS_ALLOWED = {"127.0.0.1", "::1", "localhost", "testclient"}


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    client_ip: str
    reason: str


def _clean_ip(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "," in text:
        text = text.split(",", 1)[0].strip()
    if text.startswith("[") and "]" in text:
        return text[1 : text.index("]")].strip()
    if text.count(":") == 1 and text.rsplit(":", 1)[1].isdigit():
        return text.rsplit(":", 1)[0].strip()
    return text


def _default_config() -> dict[str, Any]:
    return {
        "enabled": True,
        "server_ip": DEFAULT_SERVER_IP,
        "allowed_ips": [DEFAULT_SERVER_IP, *DEFAULT_ALLOWED_IPS, "127.0.0.1", "::1"],
        "admin_ips": [DEFAULT_SERVER_IP, "127.0.0.1", "::1"],
        "trusted_proxy_headers": False,
        "feedback_store": "docs/operator_feedback",
        "notes": [
            "Only the listed intranet clients may open the CableTrayAI service.",
            "Manual additions are written to config/access_control.local.json on the deployment server.",
        ],
    }


def local_server_ips() -> list[str]:
    addresses: set[str] = {"127.0.0.1", "::1"}

    def add_address(value: str) -> None:
        for address in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", value):
            try:
                parsed = ipaddress.ip_address(address)
            except ValueError:
                continue
            if parsed.version != 4:
                continue
            if address.startswith("169.254.") or address in {"0.0.0.0", "255.255.255.255"}:
                continue
            addresses.add(address)

    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            add_address(str(info[4][0]))
    except OSError:
        pass
    try:
        output = subprocess.check_output(["ipconfig"], text=True, encoding="gbk", errors="ignore")
        for line in output.splitlines():
            if "IPv4" not in line and "IP 地址" not in line and "IP Address" not in line:
                continue
            add_address(line)
    except Exception:
        pass
    try:
        output = subprocess.check_output(
            ["netsh", "interface", "ipv4", "show", "addresses"],
            text=True,
            encoding="gbk",
            errors="ignore",
        )
        for line in output.splitlines():
            if "IP Address" not in line and "IP 地址" not in line:
                continue
            add_address(line)
    except Exception:
        pass
    return sorted(addresses)


def load_access_config(path: Path | str | None = None) -> dict[str, Any]:
    candidate = Path(path) if path else (LOCAL_CONFIG if LOCAL_CONFIG.exists() else EXAMPLE_CONFIG)
    data: dict[str, Any] = {}
    if candidate.exists():
        data = json.loads(candidate.read_text(encoding="utf-8-sig"))
    merged = _default_config()
    merged.update(data)
    merged["allowed_ips"] = list(dict.fromkeys(str(item).strip() for item in merged.get("allowed_ips", []) if str(item).strip()))
    merged["admin_ips"] = list(dict.fromkeys(str(item).strip() for item in merged.get("admin_ips", []) if str(item).strip()))
    return merged


def save_access_config(config: dict[str, Any], path: Path | str = LOCAL_CONFIG) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _matches_rule(client_ip: str, rule: str) -> bool:
    rule = _clean_ip(rule)
    client_ip = _clean_ip(client_ip)
    if not rule or not client_ip:
        return False
    if rule == client_ip:
        return True
    try:
        return ipaddress.ip_address(client_ip) in ipaddress.ip_network(rule, strict=False)
    except ValueError:
        return False


def is_allowed_ip(client_ip: str, config: dict[str, Any] | None = None) -> AccessDecision:
    config = config or load_access_config()
    ip = _clean_ip(client_ip)
    if not bool(config.get("enabled", True)):
        return AccessDecision(True, ip, "access_control_disabled")
    if ip in ALWAYS_ALLOWED:
        return AccessDecision(True, ip, "local_or_test_client")
    if ip in local_server_ips():
        return AccessDecision(True, ip, "server_local_ip")
    rules = [*config.get("allowed_ips", []), *config.get("admin_ips", [])]
    if any(_matches_rule(ip, str(rule)) for rule in rules):
        return AccessDecision(True, ip, "matched_allowlist")
    return AccessDecision(False, ip, "not_in_allowlist")


def client_ip_from_headers(remote_host: str | None, headers: dict[str, str] | None, config: dict[str, Any] | None = None) -> str:
    config = config or load_access_config()
    if bool(config.get("trusted_proxy_headers", False)) and headers:
        for key in ("x-forwarded-for", "x-real-ip"):
            value = headers.get(key) or headers.get(key.title())
            if value:
                return _clean_ip(value)
    return _clean_ip(remote_host)


def add_allowed_ip(ip: str, *, note: str = "", operator: str = "", config_path: Path | str = LOCAL_CONFIG) -> dict[str, Any]:
    cleaned = _clean_ip(ip)
    if not cleaned:
        raise ValueError("IP address is required")
    try:
        ipaddress.ip_address(cleaned)
    except ValueError as exc:
        raise ValueError(f"Invalid IP address: {cleaned}") from exc
    config = load_access_config(config_path if Path(config_path).exists() else None)
    allowed = list(config.get("allowed_ips", []))
    if cleaned not in allowed:
        allowed.append(cleaned)
    config["allowed_ips"] = allowed
    entries = list(config.get("manual_entries", []))
    entries.append({"ip": cleaned, "note": note, "operator": operator})
    config["manual_entries"] = entries
    save_access_config(config, config_path)
    return config


def remove_allowed_ip(ip: str, *, operator: str = "", config_path: Path | str = LOCAL_CONFIG) -> dict[str, Any]:
    cleaned = _clean_ip(ip)
    if not cleaned:
        raise ValueError("IP address is required")
    config = load_access_config(config_path if Path(config_path).exists() else None)
    protected = set(config.get("admin_ips", [])) | ALWAYS_ALLOWED | set(local_server_ips())
    if cleaned in protected:
        raise ValueError(f"Cannot remove server/admin/local IP: {cleaned}")
    config["allowed_ips"] = [item for item in config.get("allowed_ips", []) if _clean_ip(str(item)) != cleaned]
    entries = list(config.get("manual_entries", []))
    entries.append({"ip": cleaned, "note": "removed from allowlist", "operator": operator})
    config["manual_entries"] = entries
    save_access_config(config, config_path)
    return config


def ensure_server_ip_allowed(server_ip: str, *, config_path: Path | str = LOCAL_CONFIG) -> dict[str, Any]:
    cleaned = _clean_ip(server_ip)
    if not cleaned:
        return load_access_config(config_path if Path(config_path).exists() else None)
    config = load_access_config(config_path if Path(config_path).exists() else None)
    allowed = list(config.get("allowed_ips", []))
    admin = list(config.get("admin_ips", []))
    if cleaned not in allowed:
        allowed.append(cleaned)
    if cleaned not in admin:
        admin.append(cleaned)
    config["server_ip"] = cleaned
    config["allowed_ips"] = allowed
    config["admin_ips"] = admin
    entries = list(config.get("manual_entries", []))
    entries.append({"ip": cleaned, "note": "auto-added deployment server IP", "operator": "installer"})
    config["manual_entries"] = entries
    save_access_config(config, config_path)
    return config
