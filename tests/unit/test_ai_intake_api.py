from __future__ import annotations

import json
from pathlib import Path


def test_ai_intake_start_run_response_is_json_safe(tmp_path: Path, monkeypatch) -> None:
    from apps.api.app import main

    captured_payload = {}
    spectrum = tmp_path / "floor.xlsm"
    spectrum.write_text("placeholder", encoding="utf-8")
    monkeypatch.setattr(main, "APP_ROOT", tmp_path)

    def fake_start_one_click_run(payload: dict) -> dict:
        captured_payload.update(payload)
        return {
            "status": "queued",
            "run_id": "run-1",
            "payload": {"intake_path": Path(payload["intake_path"])},
        }

    monkeypatch.setattr(
        main,
        "start_one_click_run",
        fake_start_one_click_run,
    )

    response = main.ai_intake_start_run(
        {
            "message": "项目1818，NR厂房，标高8.5m，双侧2+2层600，支架间距2m，方钢长度1.8m，允许100x8、120x10、140x8",
            "spectrum_file": str(spectrum),
            "execute_real": True,
        }
    )

    json.dumps(response, ensure_ascii=False)
    assert response["status"] == "queued"
    assert isinstance(response["run"]["payload"]["intake_path"], str)
    assert captured_payload["source_package_id"] is None


def test_set_run_persists_path_payload_as_json(tmp_path: Path, monkeypatch) -> None:
    from apps.api.app import main

    monkeypatch.setattr(main, "APP_ROOT", tmp_path)
    main.RUNS.clear()

    run = main._set_run("run-json-safe", payload={"intake_path": tmp_path / "intake.xlsx"})

    json.dumps(run, ensure_ascii=False)
    saved = json.loads((tmp_path / "docs" / "web_runs" / "run-json-safe.json").read_text(encoding="utf-8"))
    assert isinstance(saved["payload"]["intake_path"], str)
