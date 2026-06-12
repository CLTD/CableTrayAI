from __future__ import annotations

import json
import os
import hashlib
import shutil
import secrets
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime
from pathlib import Path


EXCLUDE_DIRS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "jobs",
    "uploads",
    "outputs",
    "logs",
    "_internal_update",
    "_review_pre_real",
}
EXCLUDE_FILES = {"CableTrayAI_Installer.exe"}
MANAGED_DIRS = {
    ".agents",
    "apps",
    "core",
    "data",
    "docs",
    "prompts",
    "runtime",
    "scripts",
    "source_materials",
    "templates",
    "tests",
}
RUNTIME_DATA_DIRS = {
    "jobs",
    "uploads",
    "outputs",
    "logs",
}
MANAGED_ROOT_FILES = {
    ".gitignore",
    "AGENTS.md",
    "CableTrayAI.exe",
    "README.md",
    "install_manifest.json",
    "pyproject.toml",
    "requirements.txt",
}
MANAGED_ROOT_SUFFIXES = {".cmd", ".ps1", ".toml"}


def log_path() -> Path:
    root = package_root()
    try:
        logs = root / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        return logs / "install_desktop_app.log"
    except Exception:
        return Path(tempfile.gettempdir()) / "CableTrayAI_install_desktop_app.log"


def install_log(message: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}"
    try:
        print(line, flush=True)
    except Exception:
        pass
    try:
        log_path().parent.mkdir(parents=True, exist_ok=True)
        with log_path().open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        pass


def package_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def default_install_dir() -> Path:
    return Path("D:/CableTrayAI") if Path("D:/").exists() else Path.home() / "CableTrayAI"


def choose_install_dir_native() -> Path:
    import ctypes
    from ctypes import wintypes

    shell32 = ctypes.windll.shell32
    ole32 = ctypes.windll.ole32
    ole32.CoInitialize(None)

    class BrowseInfo(ctypes.Structure):
        _fields_ = [
            ("hwndOwner", ctypes.c_void_p),
            ("pidlRoot", ctypes.c_void_p),
            ("pszDisplayName", ctypes.c_void_p),
            ("lpszTitle", wintypes.LPCWSTR),
            ("ulFlags", wintypes.UINT),
            ("lpfn", ctypes.c_void_p),
            ("lParam", ctypes.c_void_p),
            ("iImage", ctypes.c_int),
        ]

    shell32.SHBrowseForFolderW.argtypes = [ctypes.POINTER(BrowseInfo)]
    shell32.SHBrowseForFolderW.restype = ctypes.c_void_p
    shell32.SHGetPathFromIDListW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_wchar)]
    shell32.SHGetPathFromIDListW.restype = wintypes.BOOL
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole32.CoTaskMemFree.restype = None

    display_name = ctypes.create_unicode_buffer(260)
    browse = BrowseInfo()
    browse.pszDisplayName = ctypes.addressof(display_name)
    browse.lpszTitle = "请选择 CableTrayAI 安装目录。可在窗口中新建文件夹。"
    browse.ulFlags = 0x0001 | 0x0010 | 0x0040  # RETURNONLYFSDIRS | EDITBOX | NEWDIALOGSTYLE

    pidl = shell32.SHBrowseForFolderW(ctypes.byref(browse))
    if not pidl:
        ole32.CoUninitialize()
        raise RuntimeError("已取消安装")
    try:
        path_buffer = ctypes.create_unicode_buffer(32768)
        if not shell32.SHGetPathFromIDListW(pidl, path_buffer):
            raise RuntimeError("无法读取选择的安装目录")
        return Path(path_buffer.value)
    finally:
        ole32.CoTaskMemFree(pidl)
        ole32.CoUninitialize()


def choose_install_dir() -> Path:
    env_path = os.environ.get("CABLETRAYAI_INSTALL_DIR")
    if env_path:
        install_log(f"Using install dir from CABLETRAYAI_INSTALL_DIR: {env_path}")
        return Path(env_path).expanduser()

    try:
        install_log("Opening native Windows folder picker.")
        return choose_install_dir_native()
    except Exception as exc:
        if str(exc) == "已取消安装":
            raise
        install_log(f"Native folder picker failed: {exc}")
        raise RuntimeError("无法打开安装目录选择窗口，未执行安装。请联系管理员-duxyb。") from exc


def stop_existing_processes() -> None:
    install_log("Stopping old CableTrayAI processes.")
    for image in ("CableTrayAI.exe", "CableTrayAI_Server.exe"):
        subprocess.run(
            ["taskkill", "/F", "/T", "/IM", image],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    ps_script = r"""
$patterns = @("uvicorn", "apps.api.app.main", "portable_server.py", "CableTrayAI_Server")
Get-CimInstance Win32_Process |
  Where-Object { $_.Name -match "python|pythonw" -and ($patterns | Where-Object { $_.CommandLine -like "*$_*" }) } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    time.sleep(0.5)


def cleanup_existing_install(dst: Path, src: Path) -> None:
    if not dst.exists():
        return
    if dst.resolve() == src.resolve():
        return
    feedback_backup_root: Path | None = None
    feedback_backup: Path | None = None
    feedback_dir = dst / "docs" / "operator_feedback"
    if feedback_dir.exists():
        feedback_backup_root = Path(tempfile.mkdtemp(prefix="cabletrayai_feedback_"))
        feedback_backup = feedback_backup_root / "operator_feedback"
        shutil.copytree(feedback_dir, feedback_backup)
    cleanup_dirs = set(MANAGED_DIRS)
    if os.environ.get("CABLETRAYAI_RESET_RUNTIME_DATA") == "1":
        cleanup_dirs.update(RUNTIME_DATA_DIRS)
    for name in cleanup_dirs:
        target = dst / name
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
    if feedback_backup and feedback_backup.exists():
        shutil.copytree(feedback_backup, dst / "docs" / "operator_feedback", dirs_exist_ok=True)
    if feedback_backup_root:
        shutil.rmtree(feedback_backup_root, ignore_errors=True)
    for item in dst.iterdir():
        if item.is_file() and (item.name in MANAGED_ROOT_FILES or item.suffix.lower() in MANAGED_ROOT_SUFFIXES):
            try:
                item.unlink()
            except OSError:
                pass


def should_skip(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    if not rel.parts:
        return False
    if rel.parts[0] in EXCLUDE_DIRS:
        return True
    if len(rel.parts) >= 2 and rel.parts[0] == "data" and rel.parts[1] == "calibration":
        return True
    if path.name in EXCLUDE_FILES:
        return True
    if path.suffix.lower() in {".pyc", ".pyo"}:
        return True
    return False


def copy_package(src: Path, dst: Path) -> None:
    install_log(f"Copying package from {src} to {dst}.")
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if should_skip(item, src):
            continue
        target = dst / item.name
        if item.is_dir():
            if target.exists() and item.name in MANAGED_DIRS:
                shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(item, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        else:
            shutil.copy2(item, target)


def password_hash(username: str, password: str) -> str:
    material = f"CableTrayAI:{username.strip().lower()}:{password}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def ensure_auth_local(root: Path) -> dict[str, object]:
    config_dir = root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    auth_local = config_dir / "auth.local.json"
    users_env = os.environ.get("CABLETRAYAI_INITIAL_USERS", "")
    users = [item.strip().lower() for item in users_env.split(",") if item.strip()] or ["duxyb", "jianghl", "wanggangb"]
    initial_password, password_source, fixed_by_deployment = resolve_initial_password(root)
    if auth_local.exists() and not fixed_by_deployment:
        return {"created": False, "path": str(auth_local), "users": users}
    if auth_local.exists() and fixed_by_deployment:
        backup = auth_local.with_name(f"{auth_local.name}.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        shutil.copy2(auth_local, backup)

    payload = {
        "enabled": True,
        "session_ttl_seconds": 12 * 60 * 60,
        "users": [
            {"username": username, "password_hash": password_hash(username, initial_password)}
            for username in users
        ],
    }
    auth_local.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "created": True,
        "path": str(auth_local),
        "users": users,
        "initial_password": initial_password,
        "password_source": password_source,
    }


def resolve_initial_password(root: Path) -> tuple[str, str, bool]:
    env_password = os.environ.get("CABLETRAYAI_INITIAL_PASSWORD")
    if env_password and env_password.strip():
        return env_password.strip(), "environment CABLETRAYAI_INITIAL_PASSWORD", True
    packaged_password = root / "config" / "initial_password.txt"
    if packaged_password.exists():
        value = packaged_password.read_text(encoding="utf-8-sig").strip()
        if value:
            return value, "deployment package config/initial_password.txt", True
    return secrets.token_urlsafe(12), "generated random first-install password", False


def ensure_login_info(root: Path, auth_setup: dict[str, object]) -> Path:
    path = root / "CableTrayAI_LOGIN_INFO.txt"
    auth_setup["login_info_path"] = str(path)
    if not auth_setup.get("created") and path.exists():
        return path

    users = ", ".join(str(item) for item in auth_setup.get("users", []))
    lines = [
        "CableTrayAI Login Information",
        "================================",
        f"Install folder: {root}",
        "Login URL: http://127.0.0.1:8000/",
        f"Users: {users}",
    ]
    if auth_setup.get("created"):
        lines.extend(
            [
                f"Initial password: {auth_setup.get('initial_password')}",
                f"Password status: {auth_setup.get('password_source')}.",
            ]
        )
    else:
        lines.append("Password status: existing local auth was preserved; reinstall cannot recover the password.")
    lines.extend(
        [
            f"Auth config: {auth_setup.get('path')}",
            f"ANSYS config: {root / 'config' / 'ansys.local.toml'}",
            "",
            "Keep this file inside the unit machine. Do not publish, upload, or commit it.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def create_shortcut(install_dir: Path) -> Path:
    desktop = Path(os.environ.get("CABLETRAYAI_DESKTOP_DIR") or (Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"))
    desktop.mkdir(parents=True, exist_ok=True)
    shortcut = desktop / "CableTrayAI.lnk"
    target = install_dir / "CableTrayAI.exe"
    if not target.exists():
        raise FileNotFoundError(f"缺少启动程序：{target}")

    script = """
Set shell = CreateObject("WScript.Shell")
Set link = shell.CreateShortcut(WScript.Arguments(0))
link.TargetPath = WScript.Arguments(1)
link.WorkingDirectory = WScript.Arguments(2)
link.Description = "CableTrayAI 电缆桥架力学分析一体化平台"
link.IconLocation = WScript.Arguments(1)
link.Save
"""
    with tempfile.NamedTemporaryFile("w", suffix=".vbs", delete=False, encoding="gbk") as handle:
        handle.write(script)
        vbs = Path(handle.name)
    try:
        subprocess.run(
            ["cscript.exe", "//nologo", str(vbs), str(shortcut), str(target), str(install_dir)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    finally:
        try:
            vbs.unlink()
        except OSError:
            pass
    install_log(f"Desktop shortcut created: {shortcut}")
    return shortcut


def write_manifest(root: Path, package: Path, shortcut: Path, auth_setup: dict[str, object]) -> None:
    payload = {
        "status": "pass",
        "installed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "install_dir": str(root),
        "package_root": str(package),
        "shortcut": str(shortcut),
        "entry": "desktop shortcut -> CableTrayAI.exe",
        "auth_policy": "account_login_only",
        "auth_local_path": auth_setup.get("path"),
        "login_info_path": auth_setup.get("login_info_path"),
        "auth_local_created": auth_setup.get("created", False),
        "login_users": auth_setup.get("users", []),
    }
    if auth_setup.get("initial_password"):
        payload["initial_password"] = auth_setup["initial_password"]
        payload["initial_password_notice"] = "Local first-install password only. Rotate by rewriting config/auth.local.json."
    (root / "install_manifest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def show_message(title: str, message: str, error: bool = False) -> None:
    if os.environ.get("CABLETRAYAI_INSTALLER_QUIET") == "1":
        print(f"{title}: {message}")
        return
    try:
        import ctypes

        flags = 0x00000010 if error else 0x00000040
        ctypes.windll.user32.MessageBoxW(None, message, title, flags)
    except Exception:
        print(message)


def main() -> int:
    src = package_root()
    install_log("CableTrayAI installer started.")
    install_log(f"Package root: {src}")
    install_log("The installer will ask for an installation folder before copying files.")
    try:
        dst = choose_install_dir()
        install_log(f"Selected install dir: {dst}")
        stop_existing_processes()
        cleanup_existing_install(dst, src)
        copy_package(src, dst)
        auth_setup = ensure_auth_local(dst)
        login_info = ensure_login_info(dst, auth_setup)
        shortcut = create_shortcut(dst)
        write_manifest(dst, src, shortcut, auth_setup)
        message = (
            f"Installed to: {dst}\n"
            f"Desktop shortcut: {shortcut}\n"
            f"Login info: {login_info}\n"
            "Start CableTrayAI from the desktop shortcut."
        )
        show_message("CableTrayAI install completed", message)
        return 0
    except RuntimeError as exc:
        if str(exc) == "已取消安装":
            show_message("CableTrayAI 安装已取消", "未进行安装。")
            return 0
        show_message("CableTrayAI 安装失败", f"{exc}\n请联系管理员-duxyb。", error=True)
        return 1
    except Exception as exc:
        install_log("Unhandled installer error:")
        install_log(traceback.format_exc())
        show_message("CableTrayAI 安装失败", f"{exc}\n请联系管理员-duxyb。", error=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
