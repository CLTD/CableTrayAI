from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_backend_filters_stale_runs_and_jobs_to_current_service_session():
    text = (ROOT / "apps" / "api" / "app" / "main.py").read_text(encoding="utf-8")

    assert "SERVICE_STARTED_AT = datetime.now(timezone.utc)" in text
    assert "def _run_is_current_session" in text
    assert "def _mark_run_stale_if_needed" in text
    assert "stale_skipped_count" in text
    assert '"scope": "current_service_session"' in text
    assert "No current-session run has been recorded." in text


def test_frontend_clears_stale_persisted_run_state():
    text = (ROOT / "apps" / "web" / "index.html").read_text(encoding="utf-8")

    assert "payload.stale" in text
    assert "clearActiveRunId(storedActive)" in text
    assert "localStorage.removeItem(LATEST_RUN_STORAGE_KEY)" in text
