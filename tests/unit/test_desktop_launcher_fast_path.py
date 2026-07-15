from pathlib import Path

from scripts import desktop_launcher


def test_start_server_reuses_healthy_packaged_service(monkeypatch, tmp_path: Path) -> None:
    stopped: list[bool] = []
    monkeypatch.setattr(desktop_launcher, "health_ok", lambda: True)
    monkeypatch.setattr(desktop_launcher, "stop_stale_server", lambda: stopped.append(True))

    desktop_launcher.start_server(tmp_path, tmp_path)

    assert stopped == []


def test_main_opens_healthy_service_before_ansys_scan(monkeypatch, tmp_path: Path) -> None:
    opened: list[str] = []
    monkeypatch.delenv("CABLETRAYAI_NO_OPEN", raising=False)
    monkeypatch.setattr(desktop_launcher, "app_root", lambda: tmp_path)
    monkeypatch.setattr(desktop_launcher, "launch_access_allowed", lambda _root: (True, ["127.0.0.1"]))
    monkeypatch.setattr(desktop_launcher, "health_ok", lambda: True)
    monkeypatch.setattr(desktop_launcher.webbrowser, "open", lambda url: opened.append(url))
    monkeypatch.setattr(
        desktop_launcher,
        "scan_ansys",
        lambda: (_ for _ in ()).throw(AssertionError("healthy fast path must not scan ANSYS")),
    )

    assert desktop_launcher.main() == 0
    assert opened == [desktop_launcher.URL + "login"]
