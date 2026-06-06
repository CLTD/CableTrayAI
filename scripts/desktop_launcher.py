from __future__ import annotations

import json
import os
import ipaddress
import re
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path


PORT = 8000
URL = f"http://127.0.0.1:{PORT}/"
COMMON_ANSYS_DIRS = [
    r"C:\Program Files\ANSYS Inc",
    r"C:\Program Files (x86)\ANSYS Inc",
    r"D:\Program Files\ANSYS Inc",
    r"E:\Program Files\ANSYS Inc",
    r"D:\ANSYS Inc",
    r"E:\ANSYS Inc",
]
DEFAULT_ALLOWED_IPS = ["10.102.15.203", "10.102.15.110", "10.102.15.102", "10.102.15.105", "127.0.0.1", "::1"]


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        exe_parent = Path(sys.executable).resolve().parent
        if exe_parent.name == "CableTrayAI_Desktop" and exe_parent.parent.name == "runtime":
            return exe_parent.parent.parent
        return exe_parent
    return Path(__file__).resolve().parents[1]


def is_mechanical_apdl(path: Path) -> bool:
    name = path.name.lower()
    if not path.is_file():
        return False
    if name != "ansys.exe" and not (name.startswith("ansys") and name.endswith(".exe") and name[5:-4].isdigit()):
        return False
    return "/ansys/bin/winx64/" in path.as_posix().lower()


def version_score(path: Path) -> tuple[int, str]:
    text = path.as_posix().lower()
    score = 0
    if "v182" in text or "ansys182.exe" in text:
        score = 100000
    numbers = [int(item) for item in re.findall(r"\d+", text)]
    return (score + max(numbers, default=0), text)


def scan_ansys() -> list[Path]:
    found: set[Path] = set()

    def add(path: Path) -> None:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if is_mechanical_apdl(resolved):
            found.add(resolved)

    for key, value in os.environ.items():
        if key.upper().startswith("AWP_ROOT") and value:
            root = Path(value)
            for pattern in ("ansys/bin/winx64/ANSYS*.exe", "ansys/bin/winx64/ansys*.exe"):
                for path in root.glob(pattern):
                    add(path)

    for item in os.environ.get("PATH", "").split(os.pathsep):
        path = Path(item)
        if path.is_dir():
            for exe in path.glob("ansys*.exe"):
                add(exe)
        elif path.is_file():
            add(path)

    for root_value in COMMON_ANSYS_DIRS:
        root = Path(root_value)
        if not root.exists():
            continue
        for pattern in ("ansys/bin/winx64/ANSYS*.exe", "ansys/bin/winx64/ansys*.exe", "v*/ansys/bin/winx64/ANSYS*.exe", "v*/ansys/bin/winx64/ansys*.exe"):
            try:
                for path in root.glob(pattern):
                    add(path)
            except OSError:
                continue

    return sorted(found, key=version_score, reverse=True)


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


def _matches_rule(client_ip: str, rule: str) -> bool:
    ip = _clean_ip(client_ip)
    rule = _clean_ip(rule)
    if not ip or not rule:
        return False
    if ip == rule:
        return True
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network(rule, strict=False)
    except ValueError:
        return False


def load_access_config(root: Path) -> dict:
    config_path = root / "config" / "access_control.local.json"
    example_path = root / "config" / "access_control.example.json"
    data: dict = {}
    for path in (config_path, example_path):
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8-sig"))
                break
            except Exception:
                data = {}
    return {
        "enabled": bool(data.get("enabled", True)),
        "allowed_ips": [str(item).strip() for item in data.get("allowed_ips", DEFAULT_ALLOWED_IPS) if str(item).strip()],
        "admin_ips": [str(item).strip() for item in data.get("admin_ips", []) if str(item).strip()],
    }


def local_machine_ips() -> list[str]:
    addresses: set[str] = set()

    def add(value: str) -> None:
        for address in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", value):
            try:
                parsed = ipaddress.ip_address(address)
            except ValueError:
                continue
            if parsed.is_loopback or parsed.is_link_local or address in {"0.0.0.0", "255.255.255.255"}:
                continue
            addresses.add(address)

    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            add(str(info[4][0]))
    except OSError:
        pass
    try:
        output = subprocess.check_output(["ipconfig"], text=True, encoding="gbk", errors="ignore")
        add(output)
    except Exception:
        pass
    return sorted(addresses)


def launch_access_allowed(root: Path) -> tuple[bool, list[str]]:
    return True, ["account login is the active access gate"]


def write_access_denied_page(root: Path, ips: list[str]) -> Path:
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    ip_text = "、".join(ips) if ips else "未识别到有效内网 IP"
    page = logs / "access_denied.html"
    page.write_text(
        f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>CableTrayAI 访问受限</title>
    <style>
      body {{
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background: #eef3f7;
        color: #102235;
        font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
      }}
      main {{
        width: min(560px, calc(100vw - 32px));
        border: 1px solid #cfdbe7;
        border-radius: 10px;
        background: #fff;
        padding: 28px 30px;
        box-shadow: 0 14px 32px rgba(16, 34, 53, .08);
      }}
      h1 {{ margin: 0 0 12px; font-size: 22px; }}
      p {{ margin: 8px 0; line-height: 1.7; color: #536675; }}
      code {{ padding: 2px 6px; border-radius: 5px; background: #f3f6f9; color: #102235; }}
    </style>
  </head>
  <body>
    <main>
      <h1>当前电脑未在访问白名单内</h1>
      <p>请联系管理员-duxyb 添加本机 IP 后再使用电缆桥架力学分析一体化平台。</p>
      <p>本机识别到的 IP：<code>{ip_text}</code></p>
    </main>
  </body>
</html>""",
        encoding="utf-8",
    )
    return page


def choose_output_dir(root: Path) -> Path:
    env_output = os.environ.get("CABLETRAYAI_OUTPUT_ROOT")
    if env_output:
        return Path(env_output)

    config_path = root / "config" / "operator.local.json"
    previous = root / "outputs"
    has_saved_output = False
    if config_path.exists():
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
            if payload.get("output_root"):
                previous = Path(str(payload["output_root"]))
                has_saved_output = True
        except Exception:
            pass

    if has_saved_output and os.environ.get("CABLETRAYAI_FORCE_OUTPUT_DIALOG") != "1":
        return previous

    if os.environ.get("CABLETRAYAI_NO_OUTPUT_DIALOG") == "1":
        return previous

    try:
        selected = choose_output_dir_native()
        if selected:
            return Path(selected)
    except Exception:
        pass
    return previous


def choose_output_dir_native() -> str:
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
    browse.lpszTitle = "请选择 CableTrayAI 结果输出文件夹。可在窗口中新建文件夹。"
    browse.ulFlags = 0x0001 | 0x0010 | 0x0040

    pidl = shell32.SHBrowseForFolderW(ctypes.byref(browse))
    if not pidl:
        ole32.CoUninitialize()
        return ""
    try:
        path_buffer = ctypes.create_unicode_buffer(32768)
        if not shell32.SHGetPathFromIDListW(pidl, path_buffer):
            return ""
        return path_buffer.value
    finally:
        ole32.CoTaskMemFree(pidl)
        ole32.CoUninitialize()


def toml_string(value: str) -> str:
    return value.replace("\\", "/").replace('"', '\\"')


def write_local_config(root: Path, ansys_exe: Path | None, output_dir: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "jobs").mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    if ansys_exe:
        ansys_text = "\n".join(
            [
                "[ansys]",
                f'executable = "{toml_string(str(ansys_exe))}"',
                f'default_workdir = "{toml_string(str((root / "jobs").resolve()))}"',
                "timeout_minutes = 120",
                "license_wait = true",
                'product = "ansys"',
                "nproc_percent = 0.35",
                "startup_no_output_timeout_seconds = 90",
                "output_stall_timeout_seconds = 300",
                'memory = "4096"',
                "extra_args = []",
                "",
                "[runner]",
                'mode = "real"',
                "",
                "[output_import]",
                f'default_source_dir = "{toml_string(str(output_dir.resolve()))}"',
                "",
            ]
        )
        (root / "config" / "ansys.local.toml").write_text(ansys_text, encoding="utf-8", newline="\n")
    operator = {
        "output_root": str(output_dir.resolve()),
        "ansys_executable": str(ansys_exe.resolve()) if ansys_exe else "",
        "launcher_mode": "local_desktop_app",
        "host": socket.gethostname(),
    }
    (root / "config" / "operator.local.json").write_text(json.dumps(operator, ensure_ascii=False, indent=2), encoding="utf-8")


def health_ok() -> bool:
    for suffix in ("health", "login"):
        try:
            with urllib.request.urlopen(URL + suffix, timeout=2) as response:
                if response.status != 200:
                    return False
        except Exception:
            return False
    return True


def _taskkill_pid(pid: int) -> None:
    try:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        pass


def stop_stale_server() -> None:
    """Stop a previous packaged server so a newer deployment is not shadowed."""
    if os.environ.get("CABLETRAYAI_KEEP_STALE_SERVER") == "1":
        return
    for image in ("CableTrayAI_Server.exe",):
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/IM", image],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            pass
    script = r"""
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object {
    $_.ProcessId -ne $PID -and
    $_.Name -match '^(python|pythonw|uvicorn)\.exe$' -and
    $_.CommandLine -match 'uvicorn|apps\.api\.app|portable_server\.py'
  } |
  Select-Object -ExpandProperty ProcessId
"""
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        for item in re.findall(r"\d+", completed.stdout or ""):
            _taskkill_pid(int(item))
    except Exception:
        pass


def start_server(root: Path, output_dir: Path) -> None:
    stop_stale_server()
    if health_ok():
        return
    server = root / "runtime" / "CableTrayAI_Server" / "CableTrayAI_Server.exe"
    if not server.exists():
        raise FileNotFoundError(f"Missing server runtime: {server}")
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["CABLETRAYAI_OUTPUT_ROOT"] = str(output_dir.resolve())
    stdout = (logs / "desktop_server.log").open("ab")
    stderr = (logs / "desktop_server.err.log").open("ab")
    subprocess.Popen(
        [str(server), "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=str(root),
        stdout=stdout,
        stderr=stderr,
        env=env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    for _ in range(40):
        if health_ok():
            return
        time.sleep(0.5)
    raise RuntimeError("CableTrayAI web service did not start. See logs/desktop_server.err.log.")


def show_error(message: str) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, "CableTrayAI", 0x00000010)
    except Exception:
        print(message)


def main() -> int:
    root = app_root()
    try:
        access_ok, ips = launch_access_allowed(root)
        if not access_ok:
            denied_page = write_access_denied_page(root, ips)
            if os.environ.get("CABLETRAYAI_NO_OPEN") != "1":
                webbrowser.open(denied_page.resolve().as_uri())
            show_error(f"当前电脑未在访问白名单内，请联系管理员-duxyb。\n本机 IP：{', '.join(ips) if ips else '未识别'}")
            return 2
        candidates = scan_ansys()
        ansys_exe = candidates[0] if candidates else None
        output_dir = choose_output_dir(root)
        write_local_config(root, ansys_exe, output_dir)
        start_server(root, output_dir)
        if os.environ.get("CABLETRAYAI_NO_OPEN") != "1":
            webbrowser.open(URL + "login")
        return 0
    except Exception as exc:
        show_error(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
