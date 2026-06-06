from __future__ import annotations

import json
import base64
import html
import os
import re
import subprocess
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
except ModuleNotFoundError:  # pragma: no cover - local offline fallback
    import inspect

    from starlette.applications import Starlette
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
    from starlette.routing import Route

    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str):
            self.status_code = status_code
            self.detail = detail
            super().__init__(detail)

    class FastAPI(Starlette):
        def __init__(self, *args, **kwargs):
            super().__init__()

        def _add_route(self, path: str, func, methods: list[str]):
            signature = inspect.signature(func)

            async def endpoint(request):
                kwargs = dict(request.path_params)
                body = None
                if request.method in {"POST", "PUT", "PATCH"}:
                    try:
                        body = await request.json()
                    except Exception:
                        body = None
                for name, parameter in signature.parameters.items():
                    if name in kwargs:
                        continue
                    if name == "request":
                        kwargs[name] = request
                    elif name == "payload":
                        kwargs[name] = body
                    elif parameter.default is not inspect._empty:
                        kwargs[name] = parameter.default
                    elif body is not None:
                        kwargs[name] = body
                try:
                    result = func(**kwargs)
                except HTTPException as exc:
                    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
                if isinstance(result, Response):
                    return result
                return JSONResponse(result)

            self.routes.append(Route(path, endpoint, methods=methods))
            return func

        def get(self, *args, **kwargs):
            path = args[0]
            return lambda func: self._add_route(path, func, ["GET"])

        def post(self, *args, **kwargs):
            path = args[0]
            return lambda func: self._add_route(path, func, ["POST"])

        def middleware(self, middleware_type: str):
            def decorator(func):
                if middleware_type == "http":
                    async def dispatch(request, call_next):
                        return await func(request, call_next)

                    self.add_middleware(BaseHTTPMiddleware, dispatch=dispatch)
                return func

            return decorator

from core.ansys.config import load_ansys_config
from core.ansys.auto_config import ensure_ansys_config
from core.ansys.figure_export import run_figure_export
from core.ansys.preflight import run_preflight
from core.ansys.runner import run_ansys, run_mock_ansys, run_real_ansys
from core.apdl.standard_command_renderer import render_standard_command_package
from core.apdl.template_renderer import render_apdl_templates
from core.apdl.llm_orchestrated_renderer import render_llm_orchestrated_command_package
from core.audit.job_state import fail_job_state, read_job_state, update_job_state, write_job_state
from core.audit.feedback_store import read_feedback, record_feedback
from core.ai.model_client import ai_runtime_policy, audit_job_with_model, chat_with_model, model_presets, model_recommendations, model_task_routes, probe_model_endpoint, public_model_config, write_model_config
from core.evaluators.excel_authoritative import run_excel_authoritative_evaluation
from core.intake.intake_excel_reader import read_tabular_intake_rows
from core.intake.job_input_builder import create_job_from_intake
from core.intake.report_number_reconcile import reconcile_report_numbers_from_intake
from core.intake.tray_load_parser import parse_tray_load_description
from core.optimizer.square_section_workflow import SQUARE_SECTION_CACHE_VERSION
from core.pipeline.one_click import run_operator_one_click
from core.report.chapter6_display import build_chapter6_display_tables
from core.report.docx_builder import build_report
from core.report.template_injector import build_report_from_template
from core.results.output_workspace import DEFAULT_OUTPUT_ROOT, publish_result_outputs
from core.results.real_output_importer import import_real_outputs
from core.results.result_assembler import assemble_result
from core.schemas.input_models import CableTrayInput, model_to_dict
from core.schemas.job_models import JobState
from core.security.access_control import (
    add_allowed_ip,
    client_ip_from_headers,
    is_allowed_ip,
    load_access_config,
    local_server_ips,
    remove_allowed_ip,
)


def _atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(text, encoding=encoding)
    tmp.replace(path)


def _atomic_write_json(path: Path, payload) -> None:
    _atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
from core.security.auth import (
    COOKIE_NAME,
    SESSION_TTL_SECONDS,
    auth_enabled,
    create_session,
    delete_session,
    get_session,
    public_auth_path,
    verify_credentials,
)
from core.spectra.config_wizard import confirm_spectrum_config
from core.spectra.static_coefficients import describe_segmented_spectrum_workbook
from core.validation.manual_baseline import write_baseline_comparison
from core.validation.production_gate import production_status
from core.validation.report_baseline import write_report_baseline_comparison


app = FastAPI(title="电缆桥架智能力学分析平台 API")
def _resolve_app_root() -> Path:
    """Resolve the installed project root, not PyInstaller's temporary _MEI path."""
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        exe_parent = Path(sys.executable).resolve().parent
        candidates.extend([exe_parent, exe_parent.parent, exe_parent.parent.parent])
    file_root = Path(__file__).resolve().parents[3]
    candidates.extend([file_root, Path.cwd().resolve()])
    for candidate in candidates:
        candidate = candidate.resolve()
        if (candidate / "apps" / "web" / "index.html").exists():
            return candidate
        if (candidate / "templates").exists() and (candidate / "core").exists():
            return candidate
    return candidates[0].resolve()


APP_ROOT = _resolve_app_root()
JOBS_DIR = APP_ROOT / "jobs"
SERVICE_STARTED_AT = datetime.now(timezone.utc)
UPLOADS_DIR = Path("uploads")
UPLOADS_ROOT = APP_ROOT / UPLOADS_DIR
RUN_EXECUTOR = ThreadPoolExecutor(max_workers=1)
RUN_LOCK = threading.Lock()
RUNS: dict[str, dict] = {}
RUN_STAGE_RANK = {
    "queued": 0,
    "starting": 1,
    "creating_jobs": 5,
    "ansys_config": 10,
    "job_started": 12,
    "startup_cleanup": 15,
    "confirm_spectrum": 20,
    "write_spectrum": 25,
    "render_commands": 30,
    "select_square_section": 40,
    "running_ansys": 50,
    "ansys_output_monitor": 51,
    "ansys_startup_retry": 52,
    "ansys_resource_retry": 53,
    "exporting_connection_nodes": 60,
    "exporting_figures": 65,
    "ansys_post_exports_done": 70,
    "parsing_results": 75,
    "rerunning_ansys_after_modal_retry": 80,
    "upgrade_square_section": 82,
    "rerunning_ansys_after_section_reselection": 83,
    "rerunning_ansys_after_section_upgrade": 84,
    "reuse_exact_result": 86,
    "dry_run": 86,
    "publish_outputs": 90,
    "job_finished": 95,
    "completed": 100,
    "failed": 100,
    "cancelled": 100,
}
NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


def _optional_positive_int(value) -> int | None:
    """Treat missing/zero values from the web UI as an unspecified option."""
    if value in (None, "", False):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _project_path_from_client(value: object, *, require_existing: bool = False, label: str = "path") -> Path:
    text = str(value or "").strip().strip('"')
    if not text:
        raise HTTPException(status_code=400, detail=f"{label} is required")
    candidate = Path(text.replace("\\", "/"))
    if not candidate.is_absolute():
        candidate = APP_ROOT / candidate
    resolved = candidate.resolve()
    if require_existing and not resolved.exists():
        raise HTTPException(status_code=404, detail=f"{label} not found: {text}")
    return resolved


def _normalize_operator_payload_paths(payload: dict) -> dict:
    normalized = dict(payload)
    for key in ("intake_path", "spectrum_file", "spectrum_path"):
        if normalized.get(key):
            normalized[key] = str(_project_path_from_client(normalized[key], require_existing=True, label=key))
    return normalized


def _append_web_error_log(request: Request, exc: Exception) -> str:
    error_id = uuid4().hex[:12]
    (APP_ROOT / "docs").mkdir(parents=True, exist_ok=True)
    payload = {
        "error_id": error_id,
        "time": _now() if "_now" in globals() else datetime.now(timezone.utc).isoformat(),
        "method": getattr(request, "method", ""),
        "url": str(getattr(request, "url", "")),
        "client": request.client.host if getattr(request, "client", None) else "",
        "error_type": type(exc).__name__,
        "error": str(exc),
        "traceback": traceback.format_exc()[-6000:],
    }
    with (APP_ROOT / "docs" / "web_error_log.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return error_id


if hasattr(app, "exception_handler"):
    @app.exception_handler(Exception)
    async def _unhandled_exception_json(request: Request, exc: Exception):  # pragma: no cover - exercised by integration/UI
        error_id = _append_web_error_log(request, exc)
        return JSONResponse(
            {
                "status": "error",
                "error_id": error_id,
                "message": "服务器处理失败，已记录诊断日志。请把 error_id 提供给管理员-duxyb。",
                "detail": str(exc),
            },
            status_code=500,
        )


def _request_client_ip(request: Request) -> str:
    config = load_access_config()
    headers = {key.lower(): value for key, value in request.headers.items()} if hasattr(request, "headers") else {}
    remote = request.client.host if getattr(request, "client", None) else ""
    return client_ip_from_headers(remote, headers, config)


def _is_admin_client(client_ip: str) -> bool:
    config = load_access_config()
    decision = is_allowed_ip(client_ip, {"enabled": True, "allowed_ips": [], "admin_ips": config.get("admin_ips", [])})
    return decision.allowed


def _forbidden_access_response(client_ip: str, reason: str) -> HTMLResponse:
    safe_ip = html.escape(client_ip or "-")
    safe_reason = html.escape(reason or "not_in_allowlist")
    return HTMLResponse(
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
      code {{
        display: inline-block;
        padding: 2px 6px;
        border-radius: 5px;
        background: #f3f6f9;
        color: #102235;
      }}
    </style>
  </head>
  <body>
    <main>
      <h1>当前电脑未在访问白名单内</h1>
      <p>请联系管理员-duxyb 添加本机 IP 后再使用电缆桥架力学分析一体化平台。</p>
      <p>当前访问 IP：<code>{safe_ip}</code></p>
      <p>拦截原因：<code>{safe_reason}</code></p>
    </main>
  </body>
</html>""",
        status_code=403,
    )


def _expects_html(request: Request) -> bool:
    path = request.url.path if hasattr(request, "url") else ""
    if path in {"/", "/dashboard", "/review", "/ai-tools"}:
        return True
    accept = request.headers.get("accept", "") if hasattr(request, "headers") else ""
    return "text/html" in accept and not path.startswith(("/api/", "/jobs", "/runs", "/ai/", "/admin/"))


def _unauthenticated_response(request: Request):
    if _expects_html(request):
        next_url = quote(str(request.url.path or "/"), safe="/")
        return RedirectResponse(f"/login?next={next_url}", status_code=303)
    return JSONResponse({"status": "unauthenticated", "detail": "login_required"}, status_code=401)


def _html_file_response(path: Path) -> FileResponse:
    return FileResponse(path, headers=NO_CACHE_HEADERS)


if hasattr(app, "middleware"):
    @app.middleware("http")
    async def access_control_middleware(request: Request, call_next):
        config = load_access_config()
        client_ip = _request_client_ip(request)
        decision = is_allowed_ip(client_ip, config)
        request.state.client_ip = decision.client_ip
        request.state.access_decision = {"allowed": True, "reason": "auth_only"}
        if auth_enabled() and not public_auth_path(request.url.path):
            session = get_session(request.cookies.get(COOKIE_NAME))
            if not session:
                return _unauthenticated_response(request)
            request.state.user = session.get("username")
        return await call_next(request)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_stage_rank(stage: object) -> int:
    return RUN_STAGE_RANK.get(str(stage or ""), -1)


def _run_is_terminal(stage: object, status: object) -> bool:
    return str(stage or "") in {"completed", "failed", "cancelled"} or str(status or "") in {
        "pass",
        "dry_run",
        "fail",
        "cancelled",
    }


def _progress_cap(stage: object, status: object) -> int:
    if _run_is_terminal(stage, status):
        return 100
    caps = {
        "creating_jobs": 8,
        "ansys_config": 12,
        "job_started": 15,
        "startup_cleanup": 18,
        "confirm_spectrum": 24,
        "write_spectrum": 30,
        "render_commands": 38,
        "select_square_section": 55,
        "running_ansys": 82,
        "ansys_output_monitor": 82,
        "ansys_startup_retry": 82,
        "ansys_resource_retry": 82,
        "rerunning_ansys_after_modal_retry": 84,
        "rerunning_ansys_after_section_reselection": 84,
        "rerunning_ansys_after_section_upgrade": 84,
        "exporting_connection_nodes": 86,
        "exporting_figures": 88,
        "ansys_post_exports_done": 90,
        "parsing_results": 92,
        "reuse_exact_result": 92,
        "upgrade_square_section": 94,
        "dry_run": 90,
        "publish_outputs": 96,
        "job_finished": 99,
    }
    return caps.get(str(stage or ""), 95)


def _same_active_job(current: dict, updates: dict) -> bool:
    current_job = str(current.get("active_job_id") or "").strip()
    incoming_job = str(updates.get("active_job_id") or "").strip()
    return not current_job or not incoming_job or current_job == incoming_job


def _protect_run_stage_from_live_regression(current: dict, updates: dict) -> None:
    """Keep ANSYS live polling from moving the visible workflow stage backward."""

    incoming_stage = str(updates.get("stage") or "")
    current_stage = str(current.get("stage") or "")
    live_stages = {
        "running_ansys",
        "ansys_output_monitor",
        "ansys_startup_retry",
        "ansys_resource_retry",
    }
    if incoming_stage not in live_stages or not current_stage or not _same_active_job(current, updates):
        return
    if _run_stage_rank(current_stage) <= _run_stage_rank(incoming_stage):
        return
    updates["last_live_stage"] = incoming_stage
    if updates.get("message"):
        updates["last_live_message"] = updates.get("message")
    updates.pop("stage", None)
    updates.pop("status", None)
    updates.pop("progress", None)
    updates.pop("message", None)


def _set_run(run_id: str, **updates) -> dict:
    with RUN_LOCK:
        current = RUNS.setdefault(
            run_id,
            {
                "run_id": run_id,
                "status": "queued",
                "stage": "queued",
                "message": "等待开始",
                "progress": 0,
                "created_at": _now(),
                "updated_at": _now(),
            },
        )
        _protect_run_stage_from_live_regression(current, updates)
        incoming_stage = updates.get("stage", current.get("stage"))
        incoming_status = updates.get("status", current.get("status"))
        if "progress" in updates:
            try:
                incoming_progress = max(0, min(100, int(updates.get("progress") or 0)))
            except (TypeError, ValueError):
                incoming_progress = 0
            try:
                previous_progress = max(0, min(100, int(current.get("progress") or 0)))
            except (TypeError, ValueError):
                previous_progress = 0
            # ANSYS live callbacks can arrive after publishing/final callbacks.
            # For the same run, progress is a state indicator and must not move backwards.
            cap = _progress_cap(incoming_stage, incoming_status)
            updates["progress"] = min(max(previous_progress, incoming_progress), cap)
        current.update(updates)
        current["updated_at"] = _now()
        _atomic_write_json(APP_ROOT / "docs" / "web_runs" / f"{run_id}.json", current)
        return dict(current)


def _get_run(run_id: str) -> dict:
    with RUN_LOCK:
        if run_id in RUNS:
            run = dict(RUNS[run_id])
            run["output_snapshot"] = _run_output_snapshot(run)
            return run
    persisted = APP_ROOT / "docs" / "web_runs" / f"{run_id}.json"
    if persisted.exists():
        run = json.loads(persisted.read_text(encoding="utf-8-sig"))
        run = _mark_run_stale_if_needed(run)
        run["output_snapshot"] = _run_output_snapshot(run)
        return run
    raise HTTPException(status_code=404, detail="Run not found")


def _parse_datetime_utc(value) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _path_mtime_utc(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    except OSError:
        return None


def _run_activity_time(run: dict) -> datetime | None:
    for key in ("updated_at", "finished_at", "started_at", "created_at"):
        parsed = _parse_datetime_utc(run.get(key))
        if parsed:
            return parsed
    return None


def _run_is_current_session(run: dict) -> bool:
    if not isinstance(run, dict):
        return False
    run_id = str(run.get("run_id") or "")
    if run_id:
        with RUN_LOCK:
            if run_id in RUNS:
                return True
    if run.get("status") in {"queued", "running", "cancel_requested"}:
        return False
    activity_time = _run_activity_time(run)
    return bool(activity_time and activity_time >= SERVICE_STARTED_AT)


def _mark_run_stale_if_needed(run: dict) -> dict:
    if _run_is_current_session(run):
        return run
    stale = dict(run)
    stale["stale"] = True
    stale["current_session_started_at"] = SERVICE_STARTED_AT.isoformat()
    stale["message"] = "该运行记录来自服务启动前，已作为历史记录忽略；请重新选择提资并计算。"
    return stale


def _iter_persisted_runs(limit: int = 50) -> list[dict]:
    runs_dir = APP_ROOT / "docs" / "web_runs"
    if not runs_dir.exists():
        return []
    items: list[dict] = []
    for path in sorted(runs_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:limit]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            payload.setdefault("run_id", path.stem)
            items.append(payload)
    return items


def _recent_runs(limit: int = 10) -> list[dict]:
    merged: dict[str, dict] = {}
    for item in _iter_persisted_runs(limit=max(limit * 3, 30)):
        run_id = str(item.get("run_id") or "")
        if run_id:
            merged[run_id] = item
    with RUN_LOCK:
        for run_id, item in RUNS.items():
            merged[run_id] = dict(item)
    return sorted(
        merged.values(),
        key=lambda item: str(item.get("updated_at") or item.get("started_at") or item.get("created_at") or ""),
        reverse=True,
    )[:limit]


def _has_active_run() -> bool:
    with RUN_LOCK:
        return any(run.get("status") in {"queued", "running", "cancel_requested"} for run in RUNS.values())


def _cancel_stale_persisted_runs_before_new_run() -> list[dict]:
    """Close non-terminal persisted runs that no longer have an in-memory worker."""

    runs_dir = APP_ROOT / "docs" / "web_runs"
    if not runs_dir.exists():
        return []
    with RUN_LOCK:
        live_run_ids = set(RUNS)
    cancelled: list[dict] = []
    for path in runs_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        run_id = str(payload.get("run_id") or path.stem)
        if run_id in live_run_ids:
            continue
        if _run_is_terminal(payload.get("stage"), payload.get("status")):
            continue
        previous_stage = payload.get("stage")
        previous_status = payload.get("status")
        payload["run_id"] = run_id
        payload["status"] = "cancelled"
        payload["stage"] = "cancelled"
        try:
            payload["progress"] = max(0, min(100, int(payload.get("progress") or 0)))
        except (TypeError, ValueError):
            payload["progress"] = 0
        payload["stale_cancelled_at"] = _now()
        payload["message"] = (
            "Previous persisted run was closed before starting a new run because no live worker was attached."
        )
        try:
            _atomic_write_json(path, payload)
        except OSError:
            continue
        cancelled.append(
            {
                "run_id": run_id,
                "path": str(path.resolve()),
                "previous_stage": previous_stage,
                "previous_status": previous_status,
            }
        )
    return cancelled


class RunCancelled(RuntimeError):
    pass


def _run_cancel_requested(run_id: str) -> bool:
    with RUN_LOCK:
        run = RUNS.get(run_id) or {}
        return run.get("status") in {"cancel_requested", "cancelled"}


def _brief_file(path: Path) -> dict:
    stat = path.stat()
    return {
        "name": path.name,
        "path": str(path),
        "size_bytes": stat.st_size,
        "updated_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    }


def _brief_tree(path: Path, *, max_files: int = 6000) -> dict:
    if not path.exists():
        return {"path": str(path), "exists": False, "file_count": 0, "size_bytes": 0, "latest_files": []}
    file_count = 0
    total = 0
    latest: list[dict] = []
    newest_mtime = 0.0
    for child in path.rglob("*"):
        if not child.is_file():
            continue
        file_count += 1
        try:
            stat = child.stat()
        except OSError:
            continue
        total += stat.st_size
        newest_mtime = max(newest_mtime, stat.st_mtime)
        if child.suffix.lower() in {".out", ".err", ".rst", ".db", ".lis", ".oup", ".bmp", ".png", ".log"}:
            latest.append(_brief_file(child))
            latest = sorted(latest, key=lambda item: item["updated_at"], reverse=True)[:12]
        if file_count >= max_files:
            break
    return {
        "path": str(path),
        "exists": True,
        "file_count": file_count,
        "size_bytes": total,
        "size_mb": round(total / 1024 / 1024, 3),
        "latest_update": datetime.fromtimestamp(newest_mtime, timezone.utc).isoformat() if newest_mtime else None,
        "latest_files": latest,
        "truncated": file_count >= max_files,
    }


ANSYS_TERMINAL_STATUSES = {"success", "failed", "timeout", "startup_no_output_timeout", "output_stall_timeout", "rejected"}


def _terminal_ansys_live_status(job_dir: Path, current_live: dict | None = None, *, persist: bool = True) -> dict | None:
    """Correct stale live status when the final ANSYS audit is already terminal."""
    audit_path = job_dir / "ansys_run_audit.json"
    if not audit_path.exists():
        return None
    try:
        audit = json.loads(audit_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    audit_status = audit.get("status")
    if audit_status not in ANSYS_TERMINAL_STATUSES:
        return None
    live = dict(current_live or {})
    live.update(
        {
            "stage": "ansys_finished" if audit_status == "success" else "ansys_failed",
            "status": audit_status,
            "process_running": False,
            "returncode": audit.get("returncode"),
            "failure_reason": audit.get("failure_reason"),
            "failure_category": audit.get("failure_category"),
            "figure_count": audit.get("figure_count"),
            "terminal_source": "ansys_run_audit.json",
        }
    )
    if persist:
        try:
            (job_dir / "ansys_live_status.json").write_text(
                json.dumps(live, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass
    return live


def _parse_run_time(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _run_elapsed_seconds(run: dict) -> float:
    started = _parse_run_time(run.get("started_at") or run.get("created_at"))
    if not started:
        return 0.0
    finished = _parse_run_time(run.get("finished_at"))
    end = finished or datetime.now(timezone.utc)
    return max(0.0, (end - started).total_seconds())


def _run_output_snapshot(run: dict) -> dict:
    payload = run.get("payload") if isinstance(run.get("payload"), dict) else {}
    active_job_id = str(run.get("active_job_id") or "").strip()
    output_root = Path(str(payload.get("output_root") or DEFAULT_OUTPUT_ROOT))
    job_dir = JOBS_DIR / active_job_id if active_job_id else None
    output_job_dir = output_root / active_job_id if active_job_id else None
    snapshot = {
        "active_job_id": active_job_id or None,
        "working_job_dir": _brief_tree(job_dir) if job_dir else None,
        "published_job_dir": _brief_tree(output_job_dir) if output_job_dir else None,
        "output_root": str(output_root),
        "run_elapsed_seconds": _run_elapsed_seconds(run),
        "publish_policy": "Final output folders are published after parsing/report steps; during ANSYS execution watch working_job_dir/latest_files.",
    }
    live_path = job_dir / "ansys_live_status.json" if job_dir else None
    if live_path and live_path.exists():
        try:
            snapshot["ansys_live_status"] = json.loads(live_path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            snapshot["ansys_live_status"] = {"status": "unreadable", "error": str(exc)}
    audit_path = job_dir / "ansys_run_audit.json" if job_dir else None
    if audit_path and audit_path.exists():
        try:
            audit = json.loads(audit_path.read_text(encoding="utf-8-sig"))
            snapshot["ansys_run_audit_status"] = audit.get("status")
            live = snapshot.get("ansys_live_status") if isinstance(snapshot.get("ansys_live_status"), dict) else {}
            terminal_live = _terminal_ansys_live_status(job_dir, live) if job_dir else None
            if terminal_live:
                snapshot["ansys_live_status"] = terminal_live
        except Exception as exc:
            snapshot["ansys_run_audit_status"] = "unreadable"
            snapshot["ansys_run_audit_error"] = str(exc)
    working = snapshot.get("working_job_dir") or {}
    published = snapshot.get("published_job_dir") or {}
    snapshot["working_output_bytes"] = int(working.get("size_bytes") or 0)
    snapshot["published_output_bytes"] = int(published.get("size_bytes") or 0)
    live = snapshot.get("ansys_live_status") or {}
    if isinstance(live, dict):
        snapshot["current_ansys_output_bytes"] = int(live.get("total_output_bytes") or live.get("output_file_bytes") or 0)
    if active_job_id and working.get("exists") and not published.get("exists"):
        snapshot["operator_note"] = "ANSYS is expected to write first under jobs/<job_id>; the selected output folder can stay 0 MB until publish finishes."
    return snapshot


def _stop_ansys_batch_processes() -> dict:
    script = r"""
$workspaceMarker = 'CableTrayAI'
$stopped = @()
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | ForEach-Object {
  $cmd = [string]$_.CommandLine
  if ($cmd -and $_.Name -match '^(ANSYS\d*|ansys\d*|MAPDL|mapdl|mpiexec)\.exe$') {
    if ($cmd -like "*$workspaceMarker*" -and ($cmd -like "*\jobs\*" -or $cmd -like "*\\jobs\\*")) {
        $stopped += [PSCustomObject]@{
          id = $_.ProcessId
          name = $_.Name
          command_line = if ($cmd.Length -gt 260) { $cmd.Substring(0, 260) + '...' } else { $cmd }
        }
        Stop-Process -Id $_.ProcessId -Force
    }
  }
}
$stopped | ConvertTo-Json -Compress
"""
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=20,
    )
    stopped_text = completed.stdout.strip()
    stopped = []
    if stopped_text:
        try:
            parsed = json.loads(stopped_text)
            stopped = parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError:
            stopped = [{"raw": stopped_text}]
    return {"status": "pass" if completed.returncode == 0 else "fail", "stopped": stopped, "stderr": completed.stderr.strip()}


def _job_dir(job_id: str) -> Path:
    return JOBS_DIR / job_id


def _read_json(path: Path) -> dict | list:
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Missing file: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json_if_exists(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _read_text_if_exists(path: Path, max_chars: int = 240_000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        return text[:max_chars] + "\n! truncated for browser review"
    return text


def _last_modal_row(result: dict) -> dict:
    rows = result.get("modal_results") if isinstance(result, dict) else []
    if isinstance(rows, list) and rows:
        row = rows[-1]
        return row if isinstance(row, dict) else {}
    return {}


def _build_issue_fix_review(
    job_dir: Path,
    *,
    input_payload: dict,
    result_json: dict,
    formulas: list,
    analysis_scope: dict,
    result_validation: dict,
) -> dict:
    checks: list[dict] = []

    def add(check_id: str, status: str, title: str, message: str, evidence=None) -> None:
        checks.append(
            {
                "check_id": check_id,
                "status": status,
                "title": title,
                "message": message,
                "evidence": evidence,
            }
        )

    modal = _last_modal_row(result_json)
    mt_mode = modal.get("mt_mode")
    modal_status = modal.get("modal_cutoff_status")
    if mt_mode not in (None, ""):
        add(
            "mode_mt_cutoff",
            "pass",
            "MT 取值",
            "计算命令流中的 MT 已预先给定；Mode.oup 只用于确认提取模态已覆盖 50 Hz，记录最后一个大于 50 Hz 的 MODE 作为覆盖证据。",
            {
                "mt_mode": mt_mode,
                "cutoff_hz": modal.get("mt_cutoff_hz"),
                "first_above_cutoff_hz": modal.get("mt_mode_first_above_cutoff_hz"),
                "last_above_cutoff_hz": modal.get("mt_mode_last_above_cutoff_hz"),
                "source_ref": modal.get("source_ref"),
                "source_line": modal.get("source_line"),
            },
        )
    else:
        add(
            "mode_mt_cutoff",
            "fail" if modal else "warning",
            "MT 取值",
            "当前 Mode.oup 未解析到 50 Hz 以上模态，已阻断正式发布；应按预设加阶序列提高命令流 MT 后重新运行，而不是用旧输出倒推首轮 MT。",
            {
                "last_mode": modal.get("mode"),
                "last_frequency_hz": modal.get("frequency_hz"),
                "cutoff_hz": modal.get("mt_cutoff_hz", 50.0),
                "modal_cutoff_status": modal_status,
                "source_ref": modal.get("source_ref"),
            },
        )

    support = input_payload.get("support") if isinstance(input_payload, dict) else {}
    support = support if isinstance(support, dict) else {}
    tray_layers = input_payload.get("tray_layers") if isinstance(input_payload, dict) else []
    tray_layers = tray_layers if isinstance(tray_layers, list) else []
    metadata = input_payload.get("metadata") if isinstance(input_payload, dict) else {}
    metadata = metadata if isinstance(metadata, dict) else {}
    tray_text = metadata.get("tray_load_description") or metadata.get("tray_load_text") or ""
    parsed_tray = {}
    if tray_text:
        try:
            parsed_tray = parse_tray_load_description(tray_text)
        except Exception as exc:  # pragma: no cover - defensive API surface
            parsed_tray = {"status": "fail", "error": str(exc)}
    expected_front = parsed_tray.get("front_layers")
    expected_back = parsed_tray.get("back_layers")
    expected_third = parsed_tray.get("third_layers")
    actual_front = support.get("layers_front")
    actual_back = support.get("layers_back")
    actual_third = support.get("layers_third", 0)
    topology_pass = (
        expected_front in (None, actual_front)
        and expected_back in (None, actual_back)
        and expected_third in (None, actual_third)
        and len(tray_layers) == int((actual_front or 0) + (actual_back or 0) + (actual_third or 0))
    )
    add(
        "tray_topology",
        "pass" if topology_pass else "fail",
        "托盘层数/侧向",
        "托盘层数按提资描述重新解析并写入 input.json；双侧 2+2 应为两侧各 2 层，不应生成第三层。",
        {
            "tray_text": tray_text,
            "parsed": {
                "front_layers": expected_front,
                "back_layers": expected_back,
                "third_layers": expected_third,
                "layer_count": parsed_tray.get("layer_count"),
                "declared_layers": parsed_tray.get("declared_layers"),
            },
            "input_support": {
                "layers_front": actual_front,
                "layers_back": actual_back,
                "layers_third": actual_third,
                "side_count": support.get("side_count"),
            },
            "tray_layer_rows": len(tray_layers),
        },
    )

    compression_rows = [
        row
        for row in formulas
        if isinstance(row, dict) and str(row.get("check_id") or "").endswith("support_compression")
    ]
    compression_ok = any(
        "许用应力" in str(row.get("source_ref") or "")
        and ("equation4" in str(row.get("source_ref") or "") or "equation5" in str(row.get("source_ref") or ""))
        for row in compression_rows
    )
    add(
        "compression_allowable_excel_ai",
        "pass" if compression_ok else "fail",
        "压缩许用应力",
        "支架方钢压缩许用值应由评定 Excel 的 A/I 表和方程4/方程5计算，不再用固定常数代替。",
        [
            {
                "check_id": row.get("check_id"),
                "calculation_value": row.get("calculation_value"),
                "allowable_value": row.get("allowable_value"),
                "ratio": row.get("ratio"),
                "source_ref": row.get("source_ref"),
            }
            for row in compression_rows[:6]
        ],
    )

    requires = analysis_scope.get("requires") if isinstance(analysis_scope, dict) else {}
    requires = requires if isinstance(requires, dict) else {}
    coefficient = analysis_scope.get("cantilever_root_weld_equivalent_coefficient") if isinstance(analysis_scope, dict) else None
    equivalent_required = bool(requires.get("cantilever_root_weld_equivalent_stress_table"))
    equivalent_eval = bool(analysis_scope.get("cantilever_root_weld_equivalent_eval")) if isinstance(analysis_scope, dict) else False
    equivalent_ok = equivalent_required and equivalent_eval and abs(float(coefficient or 0) - 0.526) < 1e-9
    add(
        "weld_equivalent_stress_rule",
        "pass" if equivalent_ok else "fail",
        "托臂根部焊缝等效应力",
        "方钢截面不大于 120*120*10 时，应使用等效应力方式并要求等效应力表格，系数 0.526。",
        {
            "square_outer_width_mm": analysis_scope.get("square_outer_width_mm") if isinstance(analysis_scope, dict) else None,
            "square_thickness_mm": analysis_scope.get("square_thickness_mm") if isinstance(analysis_scope, dict) else None,
            "appendix_c_mode": analysis_scope.get("appendix_c_mode") if isinstance(analysis_scope, dict) else None,
            "equivalent_required": equivalent_required,
            "equivalent_eval": equivalent_eval,
            "coefficient": coefficient,
        },
    )

    zpa_text = _read_text_if_exists(job_dir / "ansys_zpa_parameters.mac", max_chars=20_000)
    static_coefficients = _read_json_if_exists(job_dir / "static_acceleration_coefficients.json", {})
    static_names = ("paox", "paoy", "paoz", "pasx", "pasy", "pasz")
    zpa_compact = zpa_text.replace(" ", "")
    present_names = [name for name in static_names if f"{name}=static_factor*" in zpa_compact]
    negative_names = [name for name in static_names if f"{name}=static_factor*-" in zpa_compact]
    static_ok = (
        static_coefficients.get("coefficient_source") == "frequency_100hz"
        and len(present_names) == len(static_names)
        and not negative_names
    )
    add(
        "static_correction_100hz_no_sign_inversion",
        "pass" if static_ok else "fail",
        "静力修正",
        "paox/paoy/paoz/pasx/pasy/pasz 应取反应谱 100 Hz 加速度，不取负号写入计算命令流。",
        {
            "coefficient_source": static_coefficients.get("coefficient_source"),
            "frequency_hz": static_coefficients.get("static_correction_frequency_hz", 100.0),
            "present_parameter_count": len(present_names),
            "present_parameters": present_names,
            "negative_parameter_count": len(negative_names),
            "negative_parameters": negative_names,
            "command_excerpt": "\n".join(
                line for line in zpa_text.splitlines() if any(line.strip().lower().startswith(name) for name in static_names)
            ),
        },
    )

    failed_gate = [
        {
            "check_id": item.get("check_id"),
            "message": item.get("message"),
            "evidence": item.get("evidence"),
        }
        for item in (result_validation.get("checks") or [])
        if isinstance(item, dict) and item.get("status") == "fail"
    ]
    add(
        "current_result_gate",
        "pass" if result_validation.get("status") == "pass" else "fail",
        "当前结果门禁",
        "专项逻辑修复不等于强行放行结果；真实输出缺文件、模态不足或图片缺失时必须继续阻断。",
        {
            "result_status": result_json.get("result_status"),
            "validation_status": result_validation.get("status"),
            "failed_checks": failed_gate[:8],
        },
    )

    fail_count = sum(1 for item in checks if item["status"] == "fail")
    warning_count = sum(1 for item in checks if item["status"] == "warning")
    return {
        "status": "fail" if fail_count else "warning" if warning_count else "pass",
        "fail_count": fail_count,
        "warning_count": warning_count,
        "checks": checks,
        "verification": _read_json_if_exists(job_dir / "issue_fix_verification_20260526.json", {}),
    }


def _historical_report_validation_context(path: Path | str | None = None) -> dict:
    report_path = (
        APP_ROOT / "docs" / "production_runs" / "full_intake_report_validation_after_compute.json"
        if path is None
        else Path(path)
    )
    if not report_path.is_absolute():
        report_path = APP_ROOT / report_path
    if not report_path.exists():
        return {"status": "not_available", "path": str(report_path), "failed_jobs": []}
    payload = _read_json_if_exists(report_path, {})
    if not isinstance(payload, dict):
        return {"status": "invalid", "path": str(report_path), "failed_jobs": []}
    failed_jobs = []
    for row in payload.get("results", []) or []:
        if not isinstance(row, dict) or row.get("status") != "fail":
            continue
        top_metrics = []
        for item in row.get("failed_metrics", []) or []:
            if not isinstance(item, dict):
                continue
            top_metrics.append(
                {
                    "name": item.get("name"),
                    "metric_type": item.get("metric_type"),
                    "gate_error": item.get("gate_error"),
                    "source": item.get("result_source_file"),
                }
            )
        failed_jobs.append(
            {
                "kind": "historical_report_validation",
                "job_id": row.get("report_no"),
                "job_dir": (row.get("selected_job") or {}).get("job_dir"),
                "failure_reason": "Historical report comparison exceeds 1% tolerance; review sources before changing production logic.",
                "max_gate_error": row.get("max_gate_error"),
                "failed_metric_count": row.get("failed_metric_count"),
                "top_metrics": top_metrics[:5],
            }
        )
    return {
        "status": payload.get("status"),
        "path": str(report_path),
        "report_case_count": payload.get("report_case_count"),
        "pass_count": payload.get("pass_count"),
        "fail_count": payload.get("fail_count"),
        "baseline_conflict_count": payload.get("baseline_conflict_count"),
        "blocked_count": payload.get("blocked_count"),
        "error_count": payload.get("error_count"),
        "max_gate_error": payload.get("max_gate_error"),
        "failed_jobs": failed_jobs,
        "analysis_json": str(APP_ROOT / "docs" / "HISTORICAL_BATCH_FAILURE_REVIEW_20260524.json"),
        "analysis_md": str(APP_ROOT / "docs" / "HISTORICAL_BATCH_FAILURE_REVIEW_20260524.md"),
    }


def _numeric_values_from_load(row: dict) -> list[float]:
    values = row.get("values") if isinstance(row.get("values"), dict) else {}
    numbers: list[float] = []
    for key in ("fx", "fy", "fz", "mx", "my", "mz", "force_n", "stress_mpa", "tension_mpa", "shear_mpa"):
        value = row.get(key, values.get(key))
        if isinstance(value, dict):
            value = value.get("normalized_value", value.get("value", value.get("raw_value")))
        try:
            numbers.append(float(value))
        except (TypeError, ValueError):
            continue
    return numbers


def _rows_all_zero(rows: list[dict]) -> bool:
    saw_number = False
    for row in rows:
        if not isinstance(row, dict):
            continue
        numbers = _numeric_values_from_load(row)
        if numbers:
            saw_number = True
        if any(abs(number) > 1e-9 for number in numbers):
            return False
    return saw_number


def _job_quality_summary(job_dir: Path, *, active_run: bool = False) -> dict:
    state = _read_json_if_exists(job_dir / "job_state.json", {})
    if active_run:
        live_status = _read_json_if_exists(job_dir / "ansys_live_status.json", {})
        terminal_live = _terminal_ansys_live_status(
            job_dir,
            live_status if isinstance(live_status, dict) else {},
        )
        if terminal_live:
            return _job_quality_summary(job_dir, active_run=False)
        state_status = str(state.get("status") or state.get("state") or "running") if isinstance(state, dict) else "running"
        return {
            "job_id": job_dir.name,
            "job_dir": str(job_dir),
            "last_write_time": datetime.fromtimestamp(job_dir.stat().st_mtime, timezone.utc).isoformat(),
            "status": "warning",
            "fail_count": 0,
            "warning_count": 1,
            "job_state": state_status,
            "result_status": None,
            "validation_status": None,
            "figure_count": None,
            "checks": [
                {
                    "status": "warning",
                    "check_id": "active_run_in_progress",
                    "message": "当前 job 正在运行，历史 result_validation/figures_manifest 不作为本轮结论。",
                    "evidence": {
                        "live_stage": live_status.get("stage") if isinstance(live_status, dict) else None,
                        "process_running": live_status.get("process_running") if isinstance(live_status, dict) else None,
                    },
                }
            ],
        }
    result = _read_json_if_exists(job_dir / "result.json", {})
    validation = _read_json_if_exists(job_dir / "result_validation.json", {})
    figures = _read_json_if_exists(job_dir / "figures_manifest.json", [])
    report_audit = _read_json_if_exists(job_dir / "template_report_audit.json", _read_json_if_exists(job_dir / "report_audit.json", {}))
    postprocess_ai_qc = _read_json_if_exists(job_dir / "postprocess_ai_qc.json", {})
    ansys_audit = _read_json_if_exists(job_dir / "ansys_run_audit.json", {})

    if isinstance(figures, dict):
        figures = figures.get("figures") or figures.get("items") or []
    if not isinstance(figures, list):
        figures = []
    if not isinstance(result, dict):
        result = {}
    if not isinstance(validation, dict):
        validation = {}
    checks: list[dict] = []

    def add(status: str, check_id: str, message: str, evidence=None):
        checks.append({"status": status, "check_id": check_id, "message": message, "evidence": evidence})

    state_status = str(state.get("status") or state.get("state") or "unknown") if isinstance(state, dict) else "unknown"
    if state_status == "failed":
        add("fail", "job_state_failed", "当前 job_state 为 failed。", state.get("failure_reason") if isinstance(state, dict) else None)
    elif state_status in {"running", "created", "apdl_rendered", "dry_run", "preflight_checked"}:
        add("warning", "job_incomplete", "当前 job 还没有完成到可发布状态。", state_status)

    ansys_status = str(ansys_audit.get("status") or ansys_audit.get("run_status") or "") if isinstance(ansys_audit, dict) else ""
    if ansys_status in {"fail", "failed", "rejected"}:
        add("fail", "ansys_run_not_successful", "ANSYS 运行审计未通过。", ansys_status)

    if result:
        if result.get("result_status") in {"blocked", "fail", "failed"}:
            add("fail", "result_status_blocked", "result.json 标记为 blocked/fail。", result.get("result_status"))
        validation_status = validation.get("status") or (result.get("result_validation") or {}).get("status")
        if validation_status == "fail":
            fail_checks = [
                {
                    "check_id": item.get("check_id"),
                    "message": item.get("message"),
                    "evidence": item.get("evidence"),
                }
                for item in ((validation.get("checks") or (result.get("result_validation") or {}).get("checks") or []))
                if isinstance(item, dict) and item.get("status") == "fail"
            ][:6]
            add("fail", "result_validation_failed", "结果有效性门禁未通过。", fail_checks)

        load_rows = []
        for key in ("foundation_loads", "bolt_force_results", "weld_force_results", "tray_arm_connection_loads"):
            rows = result.get(key) or []
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, dict):
                        load_rows.append({"scope": key, **row})
                if _rows_all_zero(rows):
                    add("fail", f"{key}_all_zero", f"{key} 关键载荷全零，不能进入正式结论。", key)
        unknown_rows = [
            {"scope": row.get("scope"), "load_case": row.get("load_case"), "source_file": row.get("source_file")}
            for row in load_rows
            if str(row.get("node") or row.get("keypoint") or row.get("node_display") or "").upper() == "UNKNOWN"
        ][:8]
        if unknown_rows:
            add("fail", "unknown_load_nodes", "载荷提取存在 UNKNOWN 节点或关键点。", unknown_rows)

        evaluation = result.get("evaluation_summary") or _read_json_if_exists(job_dir / "evaluation_summary.json", [])
        if isinstance(evaluation, list):
            pending = [
                item.get("check_id") or item.get("item") or item.get("name")
                for item in evaluation
                if isinstance(item, dict) and (item.get("formula_status") == "unconfirmed_todo" or item.get("pass_fail") == "待确认")
            ][:8]
            failed_eval = [
                item.get("check_id") or item.get("item") or item.get("name")
                for item in evaluation
                if isinstance(item, dict) and item.get("pass_fail") in {"不满足", "fail", "failed"}
            ][:8]
            if pending:
                add("warning", "pending_formula_items", "存在未确认公式或待确认评定项。", pending)
            if failed_eval:
                add("fail", "failed_evaluation_items", "存在不满足评定项。", failed_eval)

        if not figures:
            add("warning", "figures_missing", "当前 job 尚未登记 ANSYS 输出图片。", "figures_manifest.json")

    if isinstance(report_audit, dict) and report_audit:
        report_status = report_audit.get("status")
        if report_status in {"fail", "failed"}:
            add("fail", "report_audit_failed", "报告注入/审计未通过。", report_status)
        warnings = report_audit.get("warnings") or [
            item for item in (report_audit.get("replacements") or []) if isinstance(item, dict) and item.get("status") == "warning"
        ]
        if warnings:
            add("warning", "report_audit_warnings", "报告注入存在 warning。", warnings[:5])

    if isinstance(postprocess_ai_qc, dict) and postprocess_ai_qc.get("status") == "fail":
        add(
            "warning",
            "postprocess_ai_qc_findings",
            "后处理 AI/规则质控发现风险；正式阻断以 result_validation、确定性评定和报告审计为准。",
            postprocess_ai_qc.get("findings", [])[:5],
        )

    fail_count = sum(1 for item in checks if item["status"] == "fail")
    warning_count = sum(1 for item in checks if item["status"] == "warning")
    status = "fail" if fail_count else "warning" if warning_count else "pass" if result else "pending"
    return {
        "job_id": job_dir.name,
        "job_dir": str(job_dir),
        "last_write_time": datetime.fromtimestamp(job_dir.stat().st_mtime, timezone.utc).isoformat(),
        "status": status,
        "fail_count": fail_count,
        "warning_count": warning_count,
        "job_state": state_status,
        "result_status": result.get("result_status") if isinstance(result, dict) else None,
        "validation_status": validation.get("status") if isinstance(validation, dict) else None,
        "figure_count": len(figures),
        "checks": checks[:12],
    }


def _recent_job_quality_context(limit: int = 8, *, active_job_ids: set[str] | None = None) -> dict:
    if not JOBS_DIR.exists():
        return {"status": "not_available", "job_count": 0, "jobs": []}
    active_job_ids = active_job_ids or set()
    candidates: list[Path] = []
    for marker in ("job_state.json", "result.json", "result_validation.json", "ansys_run_audit.json"):
        candidates.extend(path.parent for path in JOBS_DIR.rglob(marker))
    unique = {path.resolve(): path for path in candidates}
    job_dirs: list[Path] = []
    stale_skipped_count = 0
    for path in sorted(unique.values(), key=lambda item: item.stat().st_mtime, reverse=True):
        if _job_dir_is_current_session(path, active_job_ids):
            job_dirs.append(path)
        else:
            stale_skipped_count += 1
        if len(job_dirs) >= limit:
            break
    jobs = [_job_quality_summary(path, active_run=path.name in active_job_ids) for path in job_dirs]
    fail_count = sum(1 for item in jobs if item["status"] == "fail")
    warning_count = sum(1 for item in jobs if item["status"] == "warning")
    return {
        "status": "fail" if fail_count else "warning" if warning_count else "pass" if jobs else "not_available",
        "job_count": len(jobs),
        "fail_count": fail_count,
        "warning_count": warning_count,
        "stale_skipped_count": stale_skipped_count,
        "scope": "current_service_session",
        "jobs": jobs,
        "policy": "This scans current/recent jobs for new-intake runtime quality gates; historical 47-case validation is only a secondary reference.",
    }


def _job_dir_is_current_session(job_dir: Path, active_job_ids: set[str]) -> bool:
    if job_dir.name in active_job_ids:
        return True
    for marker in ("job_state.json", "result.json", "result_validation.json", "ansys_run_audit.json"):
        marker_time = _path_mtime_utc(job_dir / marker)
        if marker_time and marker_time >= SERVICE_STARTED_AT:
            return True
    dir_time = _path_mtime_utc(job_dir)
    return bool(dir_time and dir_time >= SERVICE_STARTED_AT)


def _require_job(job_id: str) -> Path:
    job_dir = _job_dir(job_id)
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    return job_dir


def _safe_filename(value: str) -> str:
    name = Path(str(value or "upload.bin")).name
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip("._ ")
    return name or "upload.bin"


def _operator_config_path() -> Path:
    return APP_ROOT / "config" / "operator.local.json"


def _read_operator_config() -> dict:
    path = _operator_config_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def _write_operator_config(**updates) -> dict:
    current = _read_operator_config()
    current.update({key: value for key, value in updates.items() if value is not None})
    current.setdefault("launcher_mode", "local_desktop_app")
    path = _operator_config_path()
    _atomic_write_json(path, current)
    return current


@app.get("/login")
def login_page() -> FileResponse:
    login_path = APP_ROOT / "apps" / "web" / "login.html"
    if not login_path.exists():
        raise HTTPException(status_code=404, detail="Login file not found")
    return _html_file_response(login_path)


@app.get("/auth/session")
def auth_session(request: Request) -> dict:
    if not auth_enabled():
        return {"authenticated": True, "user": "auth_disabled"}
    session = get_session(request.cookies.get(COOKIE_NAME))
    return {
        "authenticated": bool(session),
        "user": session.get("username") if session else None,
    }


@app.post("/auth/login")
def auth_login(payload: dict, request: Request) -> JSONResponse:
    data = payload or {}
    username = str(data.get("username") or "").strip().lower()
    password = str(data.get("password") or "")
    if not verify_credentials(username, password):
        return JSONResponse({"status": "fail", "detail": "账号或密码错误"}, status_code=401)
    client_ip = _request_client_ip(request)
    session = create_session(username, client_ip=client_ip)
    response = JSONResponse({"status": "pass", "user": username})
    response.set_cookie(
        COOKIE_NAME,
        session["token"],
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
    )
    return response


@app.post("/auth/logout")
def auth_logout(request: Request) -> JSONResponse:
    delete_session(request.cookies.get(COOKIE_NAME))
    response = JSONResponse({"status": "pass"})
    response.delete_cookie(COOKIE_NAME)
    return response


@app.get("/")
def root() -> FileResponse:
    dashboard_path = APP_ROOT / "apps" / "web" / "index.html"
    if not dashboard_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard file not found")
    return _html_file_response(dashboard_path)


@app.get("/api/status")
def api_status() -> dict:
    return {"service": "CableTrayAI", "active_module": "CableTrayAI", "stage": "stage4", "status": "ok"}


@app.get("/api/version")
def api_version() -> dict:
    manifest_path = APP_ROOT / "release_manifest.json"
    manifest: dict = {}
    if manifest_path.exists():
        try:
            loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            manifest = {"manifest_error": "invalid_json"}
    return {
        "status": "pass",
        "service": "CableTrayAI",
        "release_version": manifest.get("release_version") or "2026.06.02-section-candidates-v2",
        "package_created_at": manifest.get("created_at") or "",
        "square_section_strategy": SQUARE_SECTION_CACHE_VERSION,
        "square_section_policy": "自动候选方钢截面必须来自提资计算说明允许列表；不得回退标准 SECT 全目录或历史缓存。应力比必须小于 1，低载荷时允许采用最小可行截面。",
        "source_bundle": manifest.get("source_materials_included") or "development_source_tree",
        "runtime_mode": manifest.get("compute_topology") or "development",
    }


@app.get("/operator/local-config")
def get_operator_local_config() -> dict:
    config = _read_operator_config()
    return {
        "status": "pass",
        "config": config,
        "output_root": config.get("output_root") or str(DEFAULT_OUTPUT_ROOT),
        "ansys_executable": config.get("ansys_executable") or "",
        "launcher_mode": config.get("launcher_mode") or "local_desktop_app",
    }


@app.get("/admin/access-control")
def get_access_control(request: Request) -> dict:
    config = load_access_config()
    client_ip = getattr(request.state, "client_ip", _request_client_ip(request))
    return {
        "status": "pass",
        "enabled": False,
        "auth_only": True,
        "client_ip": client_ip,
        "is_admin": bool(getattr(request.state, "user", None)),
        "local_server_ips": local_server_ips(),
        "server_ip": config.get("server_ip"),
        "allowed_ips": config.get("allowed_ips", []),
        "admin_ips": config.get("admin_ips", []),
        "manual_entries": config.get("manual_entries", []),
        "feedback_store": config.get("feedback_store", "docs/operator_feedback"),
    }


@app.post("/admin/access-control/allow-ip")
def allow_access_ip(payload: dict, request: Request) -> dict:
    client_ip = getattr(request.state, "client_ip", _request_client_ip(request))
    if not getattr(request.state, "user", None):
        raise HTTPException(status_code=403, detail="Login required")
    try:
        config = add_allowed_ip(
            str(payload.get("ip") or ""),
            note=str(payload.get("note") or ""),
            operator=str(payload.get("operator") or client_ip),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "status": "pass",
        "config_path": "config/access_control.local.json",
        "allowed_ips": config.get("allowed_ips", []),
    }


@app.post("/admin/access-control/remove-ip")
def remove_access_ip(payload: dict, request: Request) -> dict:
    client_ip = getattr(request.state, "client_ip", _request_client_ip(request))
    if not getattr(request.state, "user", None):
        raise HTTPException(status_code=403, detail="Login required")
    try:
        config = remove_allowed_ip(
            str(payload.get("ip") or ""),
            operator=str(payload.get("operator") or client_ip),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "status": "pass",
        "config_path": "config/access_control.local.json",
        "allowed_ips": config.get("allowed_ips", []),
    }


@app.post("/feedback")
def submit_operator_feedback(payload: dict, request: Request) -> dict:
    client_ip = getattr(request.state, "client_ip", _request_client_ip(request))
    try:
        item = record_feedback(payload, client_ip=client_ip)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "pass", "item": item, "store": "docs/operator_feedback"}


@app.get("/feedback")
def list_operator_feedback() -> dict:
    items = read_feedback()
    return {"status": "pass", "count": len(items), "items": items}


@app.get("/ai/config")
def get_ai_config() -> dict:
    return {"status": "pass", "config": public_model_config(), "presets": model_presets(), "routes": model_task_routes()}


@app.get("/ai/model-presets")
def get_ai_model_presets() -> dict:
    return {
        "status": "pass",
        "presets": model_presets(),
        "default_preset_id": "qwen3-coder-30b",
        "routes": model_task_routes(),
        "policy": "Operators can manually select vetted unit intranet presets; runtime tasks are routed automatically by mode.",
    }


@app.get("/ai/runtime-policy")
def get_ai_runtime_policy() -> dict:
    return ai_runtime_policy()


@app.get("/compute/topology")
def get_compute_topology(request: Request) -> dict:
    config = load_access_config()
    client_ip = getattr(request.state, "client_ip", _request_client_ip(request))
    return {
        "status": "pass",
        "public_url_policy": "每台使用电脑双击 CableTrayAI.exe，在本机打开 http://127.0.0.1:8000/。",
        "current_release_mode": "local_desktop_app",
        "current_release_behavior": "CableTrayAI.exe 在当前电脑自动查找 ANSYS、选择本机输出目录并启动本机网页服务。",
        "ansys_owner_rule": "ANSYS 所在电脑就是当前运行 CableTrayAI.exe 的电脑。",
        "output_folder_rule": "输出目录由当前电脑本机窗口选择，或在网页中填写本机可访问路径。",
        "feedback_rule": "错误备忘和修复意见保存在当前电脑 docs/operator_feedback；如需集中收集，可复制该目录。",
        "client_ip": client_ip,
        "server_ip": config.get("server_ip"),
        "allowed_ips": config.get("allowed_ips", []),
    }


@app.get("/ai/model-recommendations")
def get_ai_model_recommendations() -> dict:
    return {
        "status": "pass",
        "recommendations": model_recommendations(),
        "policy": "Use OpenAI-compatible /v1 endpoints. AI assists QA and internal tooling only; ANSYS, Excel and confirmed formulas remain authoritative.",
    }


@app.post("/ai/config")
def save_ai_config(payload: dict, request: Request) -> dict:
    client_ip = getattr(request.state, "client_ip", _request_client_ip(request))
    if not _is_admin_client(client_ip):
        raise HTTPException(status_code=403, detail="Only admin clients can edit AI model config")
    try:
        config = write_model_config(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "pass", "config": config}


@app.post("/ai/probe")
def probe_ai_config(payload: dict, request: Request) -> dict:
    client_ip = getattr(request.state, "client_ip", _request_client_ip(request))
    if not _is_admin_client(client_ip):
        raise HTTPException(status_code=403, detail="Only admin clients can probe AI model config")
    try:
        return probe_model_endpoint(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/ai/chat")
def ai_chat(payload: dict) -> dict:
    message = str(payload.get("message") or payload.get("question") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")
    job_id = str(payload.get("job_id") or "").strip()
    job_dir = _job_dir(job_id) if job_id else None
    if job_dir and not job_dir.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    return chat_with_model(
        message,
        job_dir=job_dir,
        mode=str(payload.get("mode") or "engineering_qc"),
        attachments=payload.get("attachments") or payload.get("file_paths"),
        conversation=payload.get("history") or payload.get("conversation"),
    )


@app.get("/ai/run-monitor")
def ai_run_monitor() -> dict:
    active_runs = []
    for item in _recent_runs(limit=20):
        if not _run_is_current_session(item):
            continue
        run_id = str(item.get("run_id") or "")
        if not run_id:
            continue
        active_runs.append(
            {
                "run_id": run_id,
                "status": item.get("status"),
                "started_at": item.get("started_at"),
                "finished_at": item.get("finished_at"),
                "current_stage": item.get("current_stage"),
                "progress": item.get("progress"),
                "active_job_id": item.get("active_job_id"),
                "failure_reason": item.get("failure_reason"),
            }
        )
    active_now = [run for run in active_runs if run.get("status") in {"queued", "running", "cancel_requested"}]
    active_job_ids = {
        str(run.get("active_job_id"))
        for run in active_now
        if run.get("active_job_id")
    }
    production = production_full_run_status()
    report_validation = _historical_report_validation_context()
    recent_job_quality = _recent_job_quality_context(active_job_ids=active_job_ids)
    failed_jobs: list[dict] = []
    result = production.get("result") if isinstance(production, dict) else None
    if isinstance(result, dict):
        for job in result.get("jobs", []) or []:
            if isinstance(job, dict) and job.get("status") == "fail":
                failed_jobs.append(
                    {
                        "job_id": job.get("job_id"),
                        "failure_reason": job.get("failure_reason"),
                        "job_dir": job.get("job_dir"),
                    }
                )
    production_status = production.get("status")
    if isinstance(production_status, dict):
        production_status_value = production_status.get("status")
    else:
        production_status_value = production_status
    recent_finished = [run for run in active_runs if run.get("status") not in {"queued", "running", "cancel_requested"}]
    current_status = active_now[0]["status"] if active_now else "idle"
    report_failed_jobs = report_validation.get("failed_jobs", []) if isinstance(report_validation, dict) else []
    historical_failed_jobs = failed_jobs + report_failed_jobs
    context = {
        "status": current_status,
        "current_state": "idle_no_active_run" if not active_now else "active_run",
        "active_runs": active_now,
        "recent_runs": recent_finished,
        "historical_production_status": production_status_value,
        "historical_production_status_detail": production_status if isinstance(production_status, dict) else None,
        "historical_report_validation_status": report_validation.get("status") if isinstance(report_validation, dict) else None,
        "historical_report_validation": report_validation,
        "historical_failed_jobs": historical_failed_jobs[:20],
        "recent_job_quality": recent_job_quality,
        "failed_jobs": [],
        "note": "Realtime QA is based on active/recent jobs for new-intake workflows. Historical full-batch failures are secondary review evidence, not the current running-task state.",
    }
    def _compact_failed_jobs(jobs: list[dict], limit: int = 5) -> list[dict]:
        compact: list[dict] = []
        for job in jobs[:limit]:
            if not isinstance(job, dict):
                continue
            compact.append(
                {
                    "job_id": job.get("job_id"),
                    "failure_reason": job.get("failure_reason"),
                    "max_gate_error": job.get("max_gate_error"),
                    "failed_metric_count": job.get("failed_metric_count"),
                    "top_metrics": [
                        {
                            "name": metric.get("name"),
                            "metric_type": metric.get("metric_type"),
                            "gate_error": metric.get("gate_error"),
                            "source": metric.get("source"),
                        }
                        for metric in (job.get("top_metrics") or [])[:3]
                        if isinstance(metric, dict)
                    ],
                }
            )
        return compact

    # Keep the full historical context in the API response for the page, while
    # sending only a compact status brief to the local 3B/7B model. Full 47-case
    # evidence can exceed the GGUF context window and force rule-based fallback.
    audit_context = {
        "status": current_status,
        "current_state": context["current_state"],
        "active_run_count": len(active_now),
        "active_runs": active_now[:3],
        "recent_run_count": len(recent_finished),
        "historical_production_status": production_status_value,
        "historical_report_validation_status": report_validation.get("status") if isinstance(report_validation, dict) else None,
        "historical_report_validation_summary": {
            "report_case_count": report_validation.get("report_case_count"),
            "pass_count": report_validation.get("pass_count"),
            "fail_count": report_validation.get("fail_count"),
            "baseline_conflict_count": report_validation.get("baseline_conflict_count"),
            "max_gate_error": report_validation.get("max_gate_error"),
        }
        if isinstance(report_validation, dict)
        else None,
        "historical_failed_jobs": _compact_failed_jobs(historical_failed_jobs),
        "recent_job_quality": {
            "status": recent_job_quality.get("status"),
            "job_count": recent_job_quality.get("job_count"),
            "fail_count": recent_job_quality.get("fail_count"),
            "warning_count": recent_job_quality.get("warning_count"),
            "jobs": [
                {
                    "job_id": job.get("job_id"),
                    "status": job.get("status"),
                    "job_state": job.get("job_state"),
                    "result_status": job.get("result_status"),
                    "validation_status": job.get("validation_status"),
                    "figure_count": job.get("figure_count"),
                    "checks": job.get("checks", [])[:5],
                }
                for job in (recent_job_quality.get("jobs") or [])[:5]
                if isinstance(job, dict)
            ],
        },
        "failed_jobs": [],
        "note": context["note"],
    }
    def _runtime_intervention_summary() -> dict:
        triggers: list[dict] = []
        for run in active_now[:3]:
            if run.get("failure_reason"):
                triggers.append(
                    {
                        "type": "run_failure",
                        "job_id": run.get("active_job_id"),
                        "message": run.get("failure_reason"),
                    }
                )
        for job in (recent_job_quality.get("jobs") or [])[:5]:
            if not isinstance(job, dict):
                continue
            for check in (job.get("checks") or [])[:5]:
                if not isinstance(check, dict):
                    continue
                status = str(check.get("status") or "").lower()
                if status in {"fail", "warning"}:
                    triggers.append(
                        {
                            "type": check.get("check_id") or "quality_check",
                            "job_id": job.get("job_id"),
                            "status": status,
                            "message": check.get("message") or check.get("suggested_fix") or "",
                        }
                    )
        failed_count = int(recent_job_quality.get("fail_count") or 0)
        warning_count = int(recent_job_quality.get("warning_count") or 0)
        if active_now:
            summary = f"正在巡检 {len(active_now)} 个运行任务；发现 {failed_count} 个失败、{warning_count} 个警告。"
        elif failed_count or warning_count:
            summary = f"最近任务存在 {failed_count} 个失败、{warning_count} 个警告；需要按日志、结果门禁和报告映射继续处理。"
        else:
            summary = "当前没有活动计算，最近任务未发现阻断项；后台继续巡检输出增长、全零载荷、UNKNOWN 节点、缺图和报告注入。"
        return {
            "summary": summary,
            "trigger_count": len(triggers),
            "failed_job_count": failed_count,
            "warning_count": warning_count,
            "triggers": triggers[:8],
            "safe_actions": [
                "刷新运行状态、定位 ANSYS stdout/stderr、OUT/ERR/LIS/BMP/OUP 文件和 result_validation.json。",
                "识别路径、权限、部署脚本、端口、网页显示、上传缓存和已验证解析防御类问题，并给出可审查修复建议。",
                "对全零载荷、UNKNOWN 节点、缺图、MT 截断不足和报告注入失败先阻断发布，再提示应回查的集合、命令流或源文件。",
            ],
            "blocked_actions": [
                "不得自动改 APDL/PIP 力学逻辑、材料许用值、Excel/RCC-M 公式或正式结论。",
                "不得把历史报告数值硬写进新提资结果；正式结论仍以 ANSYS、Excel、确定性公式和 source_ref 为准。",
            ],
            "compact_context": audit_context,
        }
    intervention = _runtime_intervention_summary()
    audit = chat_with_model(
        "请作为 CableTrayAI 运行质控助手，检查当前运行状态是否卡住、是否存在失败任务、下一步应该看哪些日志或审计文件。",
        mode="run_monitor",
        run_context=audit_context,
    )
    return {"status": "pass", "context": context, "audit": audit, "intervention": intervention}


@app.get("/production/full-run-status")
def production_full_run_status() -> dict:
    status_path = APP_ROOT / "docs" / "production_runs" / "full_intake_compute_status.json"
    progress_path = APP_ROOT / "docs" / "production_runs" / "full_intake_compute_progress.jsonl"
    result_path = APP_ROOT / "docs" / "production_runs" / "full_intake_compute_result.json"
    status = _read_json_if_exists(status_path, {"status": "not_started"})
    progress_tail: list[dict] = []
    if progress_path.exists():
        for line in progress_path.read_text(encoding="utf-8-sig").splitlines()[-80:]:
            if not line.strip():
                continue
            try:
                progress_tail.append(json.loads(line))
            except json.JSONDecodeError:
                progress_tail.append({"raw": line})
    result = _read_json_if_exists(result_path, None) if result_path.exists() else None
    if isinstance(result, dict) and isinstance(status, dict):
        status_jobs_root = str(status.get("jobs_root") or "")
        result_jobs_root = str(result.get("jobs_root") or "")
        if status_jobs_root and result_jobs_root and status_jobs_root != result_jobs_root:
            result = None
    current_counts = None
    if isinstance(status, dict) and status.get("jobs_root"):
        jobs_root = Path(str(status["jobs_root"]))
        if jobs_root.exists():
            job_dirs = [path for path in jobs_root.iterdir() if path.is_dir()]
            result_count = sum(1 for path in job_dirs if (path / "result.json").exists())
            failed_count = 0
            for path in job_dirs:
                state = _read_json_if_exists(path / "job_state.json", {})
                if isinstance(state, dict) and str(state.get("status") or "").lower() == "failed":
                    failed_count += 1
            current_counts = {
                "job_dir_count": len(job_dirs),
                "result_count": result_count,
                "failed_state_count": failed_count,
            }
    return {
        "status": status,
        "progress_tail": progress_tail,
        "current_counts": current_counts,
        "has_result": result is not None,
        "result_summary": {
            "status": result.get("status"),
            "job_count": result.get("job_count"),
            "failed_count": len([item for item in result.get("jobs", []) if item.get("status") == "fail"]),
            "passed_count": len([item for item in result.get("jobs", []) if item.get("status") == "pass"]),
        }
        if isinstance(result, dict)
        else None,
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/dashboard")
def dashboard() -> FileResponse:
    dashboard_path = APP_ROOT / "apps" / "web" / "index.html"
    if not dashboard_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard file not found")
    return _html_file_response(dashboard_path)


@app.get("/ai-tools")
def ai_tools() -> FileResponse:
    ai_tools_path = APP_ROOT / "apps" / "web" / "ai_tools.html"
    if not ai_tools_path.exists():
        raise HTTPException(status_code=404, detail="AI tools page not found")
    return _html_file_response(ai_tools_path)


@app.get("/review")
def review_page() -> FileResponse:
    review_path = APP_ROOT / "apps" / "web" / "review.html"
    if not review_path.exists():
        raise HTTPException(status_code=404, detail="Review page not found")
    return _html_file_response(review_path)


@app.get("/dashboard-data")
def dashboard_data() -> FileResponse:
    dashboard_data_path = APP_ROOT / "docs/precision_gate/precision_dashboard_data.json"
    if not dashboard_data_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard data not found; run scripts/build_precision_dashboard.ps1 first")
    return FileResponse(dashboard_data_path)


@app.get("/dashboard/published/{workspace_id}/{file_path:path}")
def dashboard_published_file(workspace_id: str, file_path: str) -> FileResponse:
    relative = Path(file_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise HTTPException(status_code=400, detail="Invalid published file path")
    target = DEFAULT_OUTPUT_ROOT / _safe_filename(workspace_id) / relative
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Published file not found")
    return FileResponse(target)


@app.post("/files/upload")
def upload_file(payload: dict) -> dict:
    filename = _safe_filename(payload.get("filename") or "upload.bin")
    kind = re.sub(r"[^A-Za-z0-9_-]", "_", str(payload.get("kind") or "files"))
    content_b64 = payload.get("content_base64")
    if not content_b64:
        raise HTTPException(status_code=400, detail="content_base64 is required")
    target_dir = UPLOADS_ROOT / kind
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename
    target.write_bytes(base64.b64decode(content_b64))
    relative_target = UPLOADS_DIR / kind / filename
    return {"status": "pass", "path": str(relative_target), "filename": filename, "kind": kind}


def _upload_file_exists(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    candidate = Path(text.replace("\\", "/"))
    if candidate.is_absolute():
        return False
    try:
        resolved_uploads = UPLOADS_ROOT.resolve()
        resolved_candidate = (APP_ROOT / candidate).resolve()
        resolved_candidate.relative_to(resolved_uploads)
    except Exception:
        return False
    return resolved_candidate.is_file()


@app.post("/files/exists")
def uploaded_files_exist(payload: dict) -> dict:
    raw_paths = payload.get("paths")
    if raw_paths is None:
        raw_paths = [payload.get("path")]
    if not isinstance(raw_paths, list):
        raise HTTPException(status_code=400, detail="paths must be a list")
    files = {str(path): _upload_file_exists(path) for path in raw_paths if path}
    return {"status": "pass", "files": files}


@app.post("/folders/select-output")
def select_output_folder(payload: dict | None = None) -> dict:
    payload = payload or {}
    initial = str(payload.get("initial") or DEFAULT_OUTPUT_ROOT)
    script = r"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$owner = New-Object System.Windows.Forms.Form
$owner.Text = "CableTrayAI"
$owner.StartPosition = "CenterScreen"
$owner.Size = New-Object System.Drawing.Size(1, 1)
$owner.ShowInTaskbar = $false
$owner.TopMost = $true
$owner.Opacity = 0
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = "请选择 CableTrayAI 结果输出文件夹"
$dialog.ShowNewFolderButton = $true
if ($env:CABLETRAYAI_INITIAL_DIR -and (Test-Path -LiteralPath $env:CABLETRAYAI_INITIAL_DIR)) {
    $dialog.SelectedPath = $env:CABLETRAYAI_INITIAL_DIR
}
try {
    $owner.Show()
    $owner.Activate()
    $result = $dialog.ShowDialog($owner)
}
finally {
    $owner.Close()
    $owner.Dispose()
}
if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
    Write-Output $dialog.SelectedPath
}
"""
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            timeout=300,
            env={**os.environ, "CABLETRAYAI_INITIAL_DIR": initial},
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=408, detail="Folder selection timed out") from exc
    if completed.returncode != 0:
        raise HTTPException(status_code=500, detail=(completed.stderr or "Folder selection failed").strip())
    selected = completed.stdout.strip()
    if not selected:
        return {"status": "cancelled", "path": None}
    _write_operator_config(output_root=selected)
    return {"status": "pass", "path": selected}


def _resolve_server_output_path(raw_path: str | None) -> Path | None:
    if not raw_path:
        return None
    value = str(raw_path).strip().strip('"')
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path

@app.post("/folders/apply-output")
def apply_output_folder(payload: dict | None = None) -> dict:
    payload = payload or {}
    target = _resolve_server_output_path(payload.get("path"))
    if target is None:
        raise HTTPException(status_code=400, detail="Output folder path is required")
    exists = target.exists()
    _write_operator_config(output_root=str(target))
    return {
        "status": "pass" if exists else "warning",
        "scope": "local_desktop",
        "path": str(target),
        "exists": exists,
        "message": "This path will be used by the local CableTrayAI calculation service.",
    }


@app.post("/ansys/auto-discover")
def ansys_auto_discover(payload: dict | None = None) -> dict:
    payload = payload or {}
    _, audit = ensure_ansys_config(
        preferred_executable=payload.get("preferred_executable"),
        force=bool(payload.get("force", False)),
        real_mode=bool(payload.get("real_mode", True)),
        output_dir=payload.get("output_dir") or str(DEFAULT_OUTPUT_ROOT),
    )
    return audit


@app.get("/jobs")
def list_jobs() -> dict:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    jobs = []
    for job_dir in sorted((path for path in JOBS_DIR.iterdir() if path.is_dir()), key=lambda item: item.stat().st_mtime, reverse=True):
        state = model_to_dict(read_job_state(job_dir, job_dir.name)) if (job_dir / "job_state.json").exists() else {"status": "unknown"}
        jobs.append(
            {
                "job_id": job_dir.name,
                "job_dir": str(job_dir),
                "status": state.get("status"),
                "has_result": (job_dir / "result.json").exists(),
                "has_baseline_comparison": (job_dir / "baseline_comparison.json").exists(),
            }
        )
    return {"jobs": jobs}


@app.post("/intake/preview")
def preview_intake(payload: dict) -> dict:
    intake_path = payload.get("intake_path")
    if not intake_path:
        raise HTTPException(status_code=400, detail="intake_path is required")
    resolved_intake_path = _project_path_from_client(intake_path, require_existing=True, label="intake_path")
    try:
        rows = read_tabular_intake_rows(resolved_intake_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"提资文件解析失败：{exc}") from exc
    enriched_rows = []
    for row in rows[:200]:
        item = dict(row)
        try:
            tray_parse = parse_tray_load_description(row.get("description") or "")
            item["tray_parse_status"] = tray_parse.get("status")
            item["tray_layers"] = tray_parse.get("layers") or []
            item["tray_equivalent_densities"] = [
                {
                    "side": layer.get("side"),
                    "layer_index": layer.get("layer_index"),
                    "tray_width_mm": layer.get("tray_width_mm"),
                    "cable_type": layer.get("cable_type"),
                    "load_kg_per_m": layer.get("load_kg_per_m"),
                    "tray_density_kg_m3": layer.get("tray_density_kg_m3"),
                    "tray_section_file": layer.get("tray_section_file"),
                }
                for layer in item["tray_layers"]
            ]
        except Exception as exc:
            item["tray_parse_status"] = "warning"
            item["tray_parse_warning"] = str(exc)
            item["tray_layers"] = []
            item["tray_equivalent_densities"] = []
        item["material_policy"] = {
            "default_structural_material": "Q355",
            "steel_platform_square_component_material": "Q235",
            "policy": "非钢平台默认 Q355；钢平台仅方钢立柱/方钢构件按 Q235 保守评定，其它部件按构件策略评定。",
        }
        enriched_rows.append(item)
    return {"status": "pass" if rows else "blocked", "row_count": len(rows), "rows": enriched_rows}


@app.post("/spectrum/preview")
def preview_spectrum(payload: dict) -> dict:
    spectrum_path = payload.get("spectrum_file") or payload.get("path")
    if not spectrum_path:
        raise HTTPException(status_code=400, detail="spectrum_file is required")
    resolved_spectrum_path = _project_path_from_client(spectrum_path, require_existing=True, label="spectrum_file")
    try:
        return describe_segmented_spectrum_workbook(resolved_spectrum_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"反应谱文件解析失败：{exc}") from exc


@app.post("/jobs")
def create_job(payload: CableTrayInput) -> dict:
    job_id = uuid4().hex
    job_dir = _job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=False)
    (job_dir / "input.json").write_text(
        json.dumps(model_to_dict(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    state = JobState(job_id=job_id, status="created")
    state.history.append({"status": "created", "message": "job input accepted"})
    write_job_state(job_dir, state)
    return {"job_id": job_id, "job_dir": str(job_dir), "status": "created"}


@app.post("/jobs/create-from-intake")
def create_job_from_intake_endpoint(payload: dict) -> dict:
    normalized_payload = _normalize_operator_payload_paths(payload)
    result = create_job_from_intake(
        normalized_payload["intake_path"],
        jobs_dir=JOBS_DIR,
        job_id=normalized_payload.get("job_id"),
        spectrum_file=normalized_payload.get("spectrum_file"),
        spectrum_confirmed=normalized_payload.get("spectrum_config_confirmed", False),
        intake_order_id=normalized_payload.get("intake_order_id"),
        report_number=normalized_payload.get("report_number"),
        row_number=normalized_payload.get("row_number"),
    )
    return {"job_id": result["job_id"], "job_dir": result["job_dir"], "status": "created"}


@app.post("/jobs/one-click")
def one_click_jobs(payload: dict) -> dict:
    intake_path = payload.get("intake_path")
    if not intake_path:
        raise HTTPException(status_code=400, detail="intake_path is required")
    normalized_payload = _normalize_operator_payload_paths(payload)
    try:
        return run_operator_one_click(
            intake_path=normalized_payload["intake_path"],
            spectrum_file=normalized_payload.get("spectrum_file"),
            output_root=normalized_payload.get("output_root") or DEFAULT_OUTPUT_ROOT,
            jobs_dir=JOBS_DIR,
            source_package_id=normalized_payload.get("source_package_id"),
            execute_real=bool(normalized_payload.get("execute_real", True)),
            confirm_user=normalized_payload.get("confirm_user") or "dashboard",
            preferred_ansys_executable=normalized_payload.get("preferred_ansys_executable"),
            limit=normalized_payload.get("limit"),
            selected_row_numbers=normalized_payload.get("selected_row_numbers"),
            selected_intake_order_ids=normalized_payload.get("selected_intake_order_ids"),
            row_overrides=normalized_payload.get("row_overrides"),
            square_section_candidate_limit=_optional_positive_int(normalized_payload.get("square_section_candidate_limit")),
            allow_exact_result_reuse=bool(normalized_payload.get("allow_exact_result_reuse", False)),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"计算流程启动失败：{exc}") from exc


def _run_one_click_background(run_id: str, payload: dict) -> None:
    def progress(event: dict) -> None:
        if _run_cancel_requested(run_id):
            raise RunCancelled("run_cancelled_by_operator")
        _set_run(
            run_id,
            status="running",
            stage=event.get("stage", "running"),
            message=event.get("message", ""),
            progress=int(event.get("progress", 0)),
            active_job_id=event.get("job_id"),
        )

    try:
        payload = _normalize_operator_payload_paths(payload)
        if _run_cancel_requested(run_id):
            raise RunCancelled("run_cancelled_by_operator")
        progress({"stage": "starting", "message": "后台计算已启动", "progress": 1})
        result = run_operator_one_click(
            intake_path=payload["intake_path"],
            spectrum_file=payload.get("spectrum_file"),
            output_root=payload.get("output_root") or DEFAULT_OUTPUT_ROOT,
            jobs_dir=JOBS_DIR,
            source_package_id=payload.get("source_package_id"),
            execute_real=bool(payload.get("execute_real", True)),
            confirm_user=payload.get("confirm_user") or "dashboard",
            preferred_ansys_executable=payload.get("preferred_ansys_executable"),
            limit=payload.get("limit"),
            selected_row_numbers=payload.get("selected_row_numbers"),
            selected_intake_order_ids=payload.get("selected_intake_order_ids"),
            row_overrides=payload.get("row_overrides"),
            square_section_candidate_limit=_optional_positive_int(payload.get("square_section_candidate_limit")),
            allow_exact_result_reuse=bool(payload.get("allow_exact_result_reuse", False)),
            progress_callback=progress,
        )
        active_job = collect_job_id_from_payload(result)
        _set_run(
            run_id,
            status=result.get("status", "fail"),
            stage="completed",
            message=summarize_one_click_result(result),
            progress=100,
            result=result,
            active_job_id=active_job,
            finished_at=_now(),
        )
    except RunCancelled:
        stopped = _stop_ansys_batch_processes()
        _set_run(
            run_id,
            status="cancelled",
            stage="cancelled",
            message="计算已停止；后台线程已退出，并终止当前 ANSYS 批处理进程。",
            stop_audit=stopped,
            finished_at=_now(),
        )
    except Exception as exc:
        if _run_cancel_requested(run_id):
            stopped = _stop_ansys_batch_processes()
            _set_run(
                run_id,
                status="cancelled",
                stage="cancelled",
                message="计算已停止；后台线程已退出，并终止当前 ANSYS 批处理进程。",
                stop_audit=stopped,
                finished_at=_now(),
            )
            return
        _set_run(run_id, status="fail", stage="failed", message=str(exc), progress=100, finished_at=_now())


def collect_job_id_from_payload(payload) -> str:
    if not isinstance(payload, dict):
        return ""
    if payload.get("job_id"):
        return payload["job_id"]
    for key in ("jobs", "results"):
        value = payload.get(key)
        if isinstance(value, list) and value and isinstance(value[0], dict) and value[0].get("job_id"):
            return value[0]["job_id"]
    for value in payload.values():
        found = collect_job_id_from_payload(value)
        if found:
            return found
    return ""


def summarize_one_click_result(result: dict) -> str:
    jobs = result.get("jobs") if isinstance(result.get("jobs"), list) else result.get("results")
    if not isinstance(jobs, list):
        return "计算流程结束" if result.get("status") != "fail" else "计算流程结束，但存在失败项"
    failed = [job for job in jobs if isinstance(job, dict) and job.get("status") == "fail"]
    passed_count = len([job for job in jobs if isinstance(job, dict) and job.get("status") != "fail"])
    if not failed:
        return "计算流程结束"
    examples = "；".join(
        f"{job.get('job_id') or '未知任务'}: {job.get('failure_reason') or '失败'}"
        for job in failed[:3]
    )
    return f"计算流程结束；{passed_count} 个通过，{len(failed)} 个失败。{examples}"


@app.post("/runs/start")
def start_one_click_run(payload: dict) -> dict:
    if not payload.get("intake_path"):
        raise HTTPException(status_code=400, detail="intake_path is required")
    payload = _normalize_operator_payload_paths(payload)
    stale_persisted_runs = _cancel_stale_persisted_runs_before_new_run()
    if _has_active_run():
        raise HTTPException(status_code=409, detail="已有计算正在运行，请先等待完成或停止当前计算。")
    stale_cleanup = _stop_ansys_batch_processes()
    run_id = uuid4().hex
    run = _set_run(
        run_id,
        status="queued",
        stage="queued",
        message="已加入后台队列；已清理本平台遗留 ANSYS 批处理进程。",
        progress=0,
        payload=payload,
        started_at=_now(),
        stale_process_cleanup=stale_cleanup,
        stale_persisted_runs_cancelled=stale_persisted_runs,
    )
    RUN_EXECUTOR.submit(_run_one_click_background, run_id, dict(payload))
    return run


@app.get("/runs/latest")
def get_latest_run_status() -> dict:
    runs = [item for item in _recent_runs(limit=20) if _run_is_current_session(item)]
    if not runs:
        return {"status": "not_started", "message": "No current-session run has been recorded."}
    run = dict(runs[0])
    run["output_snapshot"] = _run_output_snapshot(run)
    return run


@app.get("/runs/{run_id}")
def get_run_status(run_id: str) -> dict:
    return _get_run(run_id)


@app.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str) -> dict:
    run = _get_run(run_id)
    stopped = _stop_ansys_batch_processes()
    return _set_run(
        run_id,
        status="cancelled",
        stage="cancelled",
        message="已请求停止，并终止当前 ANSYS 批处理进程；许可证服务未停止。",
        progress=run.get("progress", 0),
        stop_audit=stopped,
        finished_at=_now(),
    )


@app.post("/intake/reconcile-report-numbers")
def reconcile_intake_report_numbers(payload: dict) -> dict:
    intake_path = payload.get("intake_path")
    if not intake_path:
        raise HTTPException(status_code=400, detail="intake_path is required")
    resolved_intake_path = _project_path_from_client(intake_path, require_existing=True, label="intake_path")
    return reconcile_report_numbers_from_intake(
        payload.get("jobs_dir") or JOBS_DIR,
        resolved_intake_path,
        dry_run=bool(payload.get("dry_run", False)),
        output_root=payload.get("output_root") or DEFAULT_OUTPUT_ROOT,
        publish_results=bool(payload.get("publish_results", True)),
        overwrite=bool(payload.get("overwrite", True)),
    )


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job_dir = _require_job(job_id)
    files = sorted(path.name for path in job_dir.iterdir() if path.is_file())
    return {"job_id": job_id, "files": files, "state": model_to_dict(read_job_state(job_dir, job_id))}


@app.post("/jobs/{job_id}/render-apdl")
def render_job_apdl(job_id: str) -> dict:
    job_dir = _require_job(job_id)
    input_path = job_dir / "input.json"
    if not input_path.exists():
        raise HTTPException(status_code=404, detail="Job input not found")
    try:
        result = render_apdl_templates(job_id, input_path, jobs_dir=JOBS_DIR)
        result["state"] = update_job_state(job_dir, "apdl_rendered", "APDL templates rendered")
        return result
    except Exception as exc:
        fail_job_state(job_dir, str(exc))
        raise


@app.post("/jobs/{job_id}/render-standard-commands")
def render_job_standard_commands(job_id: str, payload: dict | None = None) -> dict:
    job_dir = _require_job(job_id)
    payload = payload or {}
    try:
        result = render_standard_command_package(
            job_dir,
            package_id=payload.get("package_id"),
        )
        result["state"] = update_job_state(job_dir, "apdl_rendered", "standard command streams rendered from source package")
        return result
    except Exception as exc:
        fail_job_state(job_dir, str(exc))
        raise


@app.post("/jobs/{job_id}/render-llm-standard-commands")
def render_job_llm_standard_commands(job_id: str, payload: dict | None = None) -> dict:
    job_dir = _require_job(job_id)
    payload = payload or {}
    try:
        result = render_llm_orchestrated_command_package(
            job_dir,
            package_id=payload.get("package_id"),
            jobs_dir=JOBS_DIR,
            template_dir=Path("templates/apdl"),
            use_model=bool(payload.get("use_model", True)),
        )
        if result.get("status") == "fail":
            update_job_state(job_dir, "failed", "LLM command plan audit failed", failure_reason="command_plan_audit failed")
        else:
            update_job_state(job_dir, "apdl_rendered", "LLM-assisted standard command streams rendered")
        result["state"] = model_to_dict(read_job_state(job_dir, job_id))
        return result
    except Exception as exc:
        fail_job_state(job_dir, str(exc))
        raise


@app.post("/jobs/{job_id}/run-mock")
def run_job_mock(job_id: str) -> dict:
    job_dir = _require_job(job_id)
    if not (job_dir / "input.json").exists():
        raise HTTPException(status_code=404, detail="Job input not found")
    try:
        update_job_state(job_dir, "running", "mock ANSYS started")
        run_audit = run_mock_ansys(job_dir)
        result = assemble_result(job_dir)
        update_job_state(job_dir, "parsed", "LIS and figures parsed")
        state = update_job_state(job_dir, "evaluated", "evaluation summary written")
        return {
            "job_id": job_id,
            "ansys_run_audit": run_audit,
            "result_file": "result.json",
            "result_version": result["result_version"],
            "state": state,
        }
    except Exception as exc:
        fail_job_state(job_dir, str(exc))
        raise


@app.post("/jobs/{job_id}/preflight")
def create_job_preflight(job_id: str) -> dict:
    job_dir = _require_job(job_id)
    preflight = run_preflight(job_dir)
    preflight["state"] = update_job_state(job_dir, "preflight_checked", f"preflight {preflight['status']}")
    return preflight


@app.get("/jobs/{job_id}/preflight")
def get_job_preflight(job_id: str) -> dict:
    return _read_json(_job_dir(job_id) / "ansys_preflight.json")


@app.post("/jobs/{job_id}/confirm-spectrum")
def confirm_job_spectrum(job_id: str, payload: dict | None = None) -> dict:
    job_dir = _require_job(job_id)
    payload = payload or {}
    audit = confirm_spectrum_config(job_dir, confirmed_by=payload.get("confirmed_by", "api"))
    audit["state"] = update_job_state(job_dir, "spectrum_selected", "spectrum configuration confirmed")
    return audit


@app.post("/jobs/{job_id}/run-dry")
def run_job_dry(job_id: str) -> dict:
    job_dir = _require_job(job_id)
    audit = run_ansys(job_dir, mode="dry_run")
    audit["state"] = update_job_state(job_dir, "dry_run", "dry-run command generated")
    return audit


@app.post("/jobs/{job_id}/run-real")
def run_job_real(job_id: str, payload: dict | None = None) -> dict:
    job_dir = _require_job(job_id)
    config = load_ansys_config("config/ansys.local.toml")
    payload = payload or {}
    audit = run_real_ansys(
        job_dir,
        config=config,
        confirm_real_run=bool(payload.get("confirm_real_run")),
        confirm_user=payload.get("confirm_user"),
    )
    if audit.get("status") == "rejected":
        update_job_state(job_dir, "failed", "real run rejected", failure_reason="; ".join(audit.get("rejection_reasons", [])))
        raise HTTPException(status_code=400, detail=audit.get("rejection_reasons", ["Real run rejected"]))
    if audit["status"] == "success":
        audit["state"] = update_job_state(job_dir, "parsed", "real ANSYS finished; parse outputs next")
    else:
        audit["state"] = update_job_state(job_dir, "failed", "real ANSYS failed", failure_reason=str(audit))
    return audit


@app.post("/jobs/{job_id}/export-figures")
def export_job_figures(job_id: str, payload: dict | None = None) -> dict:
    job_dir = _require_job(job_id)
    payload = payload or {}
    config = load_ansys_config("config/ansys.local.toml")
    audit = run_figure_export(job_dir, config=config, timeout_minutes=int(payload.get("timeout_minutes", 30)))
    if audit.get("status") != "success":
        update_job_state(job_dir, "failed", "ANSYS figure export failed", failure_reason=str(audit))
        raise HTTPException(status_code=400, detail=audit)
    if (job_dir / "input.json").exists():
        assemble_result(job_dir)
    audit["state"] = update_job_state(job_dir, "parsed", "ANSYS cloud figures exported and manifest updated")
    return audit


@app.post("/jobs/{job_id}/import-real-outputs")
def import_job_real_outputs(job_id: str, payload: dict) -> dict:
    job_dir = _require_job(job_id)
    source_dir = payload.get("source_dir")
    manifest = import_real_outputs(
        source_dir,
        job_dir,
        parse=payload.get("parse", True),
        build_report_doc=payload.get("build_report", False),
        overwrite=payload.get("overwrite", True),
    )
    if manifest["validation_status"] != "pass":
        manifest["state"] = update_job_state(job_dir, "failed", "real output import validation failed", failure_reason="real output validation failed")
        raise HTTPException(status_code=400, detail="Real output validation failed")
    if manifest["report_audit_file"]:
        manifest["state"] = update_job_state(job_dir, "reported", "real outputs imported, parsed, and reported")
    elif manifest["result_file"]:
        manifest["state"] = update_job_state(job_dir, "evaluated", "real outputs imported and parsed")
    else:
        manifest["state"] = update_job_state(job_dir, "parsed", "real outputs imported")
    return manifest


@app.get("/jobs/{job_id}/ansys-command")
def get_job_ansys_command(job_id: str) -> dict:
    return _read_json(_job_dir(job_id) / "ansys_command.json")


@app.get("/jobs/{job_id}/figures")
def get_job_figures(job_id: str) -> list:
    return _read_json(_job_dir(job_id) / "figures_manifest.json")


@app.get("/jobs/{job_id}/figures/{figure_id}/file")
def get_job_figure_file(job_id: str, figure_id: str) -> FileResponse:
    job_dir = _require_job(job_id)
    figures = _read_json(job_dir / "figures_manifest.json")
    if isinstance(figures, dict):
        figures = figures.get("figures") or figures.get("items") or []
    if not isinstance(figures, list):
        raise HTTPException(status_code=400, detail="Invalid figures manifest")
    match = next((item for item in figures if item.get("figure_id") == figure_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="Figure not found")
    relative = Path(match.get("target_file") or match.get("path") or "")
    if relative.is_absolute() or ".." in relative.parts:
        raise HTTPException(status_code=400, detail="Invalid figure path")
    path = job_dir / relative
    if not path.exists():
        raise HTTPException(status_code=404, detail="Figure file not found")
    return FileResponse(path)


@app.get("/jobs/{job_id}/report-audit")
def get_job_report_audit(job_id: str) -> dict:
    return _read_json(_job_dir(job_id) / "report_audit.json")


@app.get("/jobs/{job_id}/result")
def get_job_result(job_id: str) -> dict:
    return _read_json(_job_dir(job_id) / "result.json")


@app.get("/jobs/{job_id}/engineering-review")
def get_job_engineering_review(job_id: str) -> dict:
    job_dir = _require_job(job_id)
    command_files = [
        ("modeling", "generated_model.mac"),
        ("calculation", "generated_solve.mac"),
        ("result_extraction", "generated_post.mac"),
    ]
    formulas = _read_json_if_exists(job_dir / "evaluation_summary.json", [])
    figures = _read_json_if_exists(job_dir / "figures_manifest.json", [])
    result_json = _read_json_if_exists(job_dir / "result.json", {})
    result_validation = _read_json_if_exists(job_dir / "result_validation.json", {})
    job_state = _read_json_if_exists(job_dir / "job_state.json", {})
    input_payload = _read_json_if_exists(job_dir / "input.json", {})
    analysis_scope = _read_json_if_exists(job_dir / "analysis_scope.json", {})
    if isinstance(figures, dict):
        figures = figures.get("figures") or figures.get("items") or []
    if not isinstance(figures, list):
        figures = []
    load_files = [
        ("foundation", "foundation_loads.json"),
        ("bolt_connection", "bolt_force_results.json"),
        ("weld_root", "weld_force_results.json"),
    ]
    load_extractions = []
    for scope, name in load_files:
        rows = _read_json_if_exists(job_dir / name, [])
        if isinstance(rows, dict):
            rows = [rows]
        for row in rows:
            if not isinstance(row, dict):
                continue
            source_keypoints = row.get("source_keypoints")
            if not isinstance(source_keypoints, list):
                source_keypoints = []
            topology_selection = row.get("topology_selection") if isinstance(row.get("topology_selection"), dict) else {}
            selected_keypoints = topology_selection.get("selected_keypoints") if isinstance(topology_selection, dict) else []
            if isinstance(selected_keypoints, list):
                source_keypoints = [*source_keypoints, *selected_keypoints]
            source_keypoints = list(dict.fromkeys(str(item) for item in source_keypoints if item not in (None, "")))
            node = row.get("node") or row.get("keypoint") or row.get("node_id")
            node_text = str(node) if node not in (None, "") else ""
            if not node_text or node_text.upper() == "UNKNOWN":
                if source_keypoints:
                    node_text = "KP " + ", ".join(source_keypoints[:12])
                    if len(source_keypoints) > 12:
                        node_text += f" 等{len(source_keypoints)}点"
                elif row.get("source_block"):
                    node_text = str(row.get("source_block"))
                elif scope == "bolt_connection":
                    node_text = "托盘-托臂连接固定点包络"
                else:
                    node_text = "未解析到节点"
            load_extractions.append(
                {
                    "scope": scope,
                    "load_case": row.get("load_case"),
                    "node": node,
                    "node_display": node_text,
                    "source_keypoints": source_keypoints,
                    "topology_selection": topology_selection,
                    "highlight_nodes": source_keypoints,
                    "source_file": row.get("source_file") or name,
                    "source_ref": row.get("source_ref"),
                    "source_line": row.get("source_line"),
                    "fx": row.get("fx"),
                    "fy": row.get("fy"),
                    "fz": row.get("fz"),
                    "mx": row.get("mx"),
                    "my": row.get("my"),
                    "mz": row.get("mz"),
                }
            )
    report_chapter6_tables = build_chapter6_display_tables(
        input_payload=input_payload if isinstance(input_payload, dict) else {},
        result=result_json if isinstance(result_json, dict) else {},
        evaluation=formulas if isinstance(formulas, list) else [],
        scope=analysis_scope if isinstance(analysis_scope, dict) else {},
        load_extractions=load_extractions,
    )
    issue_fix_review = _build_issue_fix_review(
        job_dir,
        input_payload=input_payload if isinstance(input_payload, dict) else {},
        result_json=result_json if isinstance(result_json, dict) else {},
        formulas=formulas if isinstance(formulas, list) else [],
        analysis_scope=analysis_scope if isinstance(analysis_scope, dict) else {},
        result_validation=result_validation if isinstance(result_validation, dict) else {},
    )
    return {
        "job_id": job_id,
        "job_dir": str(job_dir),
        "command_streams": [
            {
                "role": role,
                "file": file_name,
                "exists": (job_dir / file_name).exists(),
                "text": _read_text_if_exists(job_dir / file_name),
            }
            for role, file_name in command_files
        ],
        "formulas": formulas if isinstance(formulas, list) else [],
        "load_extractions": load_extractions,
        "report_chapter6_tables": report_chapter6_tables,
        "figures": figures,
        "result": result_json if isinstance(result_json, dict) else {},
        "input": input_payload if isinstance(input_payload, dict) else {},
        "analysis_scope": analysis_scope if isinstance(analysis_scope, dict) else {},
        "result_validation": result_validation if isinstance(result_validation, dict) else {},
        "issue_fix_review": issue_fix_review,
        "job_state": job_state if isinstance(job_state, dict) else {},
        "review_memo": _read_json_if_exists(job_dir / "review_memo.json", {"items": []}),
    }


@app.get("/jobs/{job_id}/square-section-selection")
def get_job_square_section_selection(job_id: str) -> dict:
    job_dir = _require_job(job_id)
    selection = _read_json_if_exists(job_dir / "square_section_selection.json", {})
    trial_summary = _read_json_if_exists(job_dir / "square_section_trial_summary.json", {})
    applied = _read_json_if_exists(job_dir / "square_section_selection_applied.json", {})
    upgrade = _read_json_if_exists(job_dir / "square_section_upgrade_after_ratio_fail.json", {})
    return {
        "job_id": job_id,
        "exists": any(bool(item) for item in (selection, trial_summary, applied, upgrade)),
        "selection": selection if isinstance(selection, dict) else {},
        "trial_summary": trial_summary if isinstance(trial_summary, dict) else {},
        "selection_applied": applied if isinstance(applied, dict) else {},
        "upgrade_after_ratio_fail": upgrade if isinstance(upgrade, dict) else {},
        "policy": (
            "Square-section hints from identical or similar intake rows are audit aids only. "
            "Candidate status is the deterministic trial ratio status, not final acceptance. "
            "A production section still requires ANSYS output, final selection application, and deterministic ratio gates."
        ),
    }


@app.post("/jobs/{job_id}/review-memo")
def save_job_review_memo(job_id: str, payload: dict) -> dict:
    job_dir = _require_job(job_id)
    items = payload.get("items")
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="items must be a list")
    target = job_dir / "review_memo.json"
    target.write_text(json.dumps({"items": items}, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "pass", "job_id": job_id, "file": str(target), "count": len(items)}


@app.post("/jobs/{job_id}/report")
def create_job_report(job_id: str) -> dict:
    job_dir = _require_job(job_id)
    if not (job_dir / "result.json").exists():
        raise HTTPException(status_code=404, detail="Job result not found")
    try:
        audit = build_report(job_dir)
        audit["state"] = update_job_state(job_dir, "reported", "report generated")
        return audit
    except Exception as exc:
        fail_job_state(job_dir, str(exc))
        raise


@app.post("/jobs/{job_id}/template-report")
def create_job_template_report(job_id: str, payload: dict | None = None) -> dict:
    job_dir = _require_job(job_id)
    payload = payload or {}
    if not (job_dir / "result.json").exists():
        raise HTTPException(status_code=404, detail="Job result not found")
    try:
        audit = build_report_from_template(job_dir, output_path=payload.get("output_path"))
        audit["state"] = update_job_state(job_dir, "reported", "template report generated")
        return audit
    except Exception as exc:
        fail_job_state(job_dir, str(exc))
        raise


@app.get("/jobs/{job_id}/template-report")
def get_job_template_report(job_id: str) -> FileResponse:
    job_dir = _require_job(job_id)
    audit = _read_json(job_dir / "template_report_audit.json")
    report_file = audit.get("report_file")
    if not report_file:
        raise HTTPException(status_code=404, detail="Template report not generated")
    path = job_dir / report_file
    if not path.exists():
        raise HTTPException(status_code=404, detail="Template report file not found")
    return FileResponse(path)


@app.post("/jobs/{job_id}/ai-audit")
def create_job_ai_audit(job_id: str, payload: dict | None = None) -> dict:
    job_dir = _require_job(job_id)
    payload = payload or {}
    return audit_job_with_model(job_dir, question=payload.get("question"))


@app.post("/jobs/{job_id}/evaluate-excel")
def evaluate_job_excel(job_id: str, payload: dict | None = None) -> dict:
    job_dir = _require_job(job_id)
    payload = payload or {}
    result = run_excel_authoritative_evaluation(job_dir, source_workbook=payload.get("source_workbook"))
    result["state"] = update_job_state(job_dir, "evaluated", f"excel evaluation {result['status']}")
    return result


@app.post("/jobs/{job_id}/compare-baseline")
def compare_job_baseline(job_id: str, payload: dict | None = None) -> dict:
    job_dir = _require_job(job_id)
    payload = payload or {}
    return write_baseline_comparison(job_dir, baseline_path=payload.get("baseline_path"))


@app.post("/jobs/{job_id}/compare-report-baseline")
def compare_job_report_baseline(job_id: str, payload: dict) -> dict:
    job_dir = _require_job(job_id)
    report_path = payload.get("report_path")
    if not report_path:
        raise HTTPException(status_code=400, detail="report_path is required")
    tolerance = float(payload.get("tolerance", 0.01))
    result = write_report_baseline_comparison(job_dir, report_path, tolerance=tolerance)
    update_job_state(job_dir, "baseline_compared", f"baseline comparison {result['status']}")
    return result


@app.post("/jobs/{job_id}/publish-results")
def publish_job_results(job_id: str, payload: dict | None = None) -> dict:
    job_dir = _require_job(job_id)
    payload = payload or {}
    result = publish_result_outputs(
        job_dir,
        output_root=payload.get("output_root") or DEFAULT_OUTPUT_ROOT,
        intake_order_id=payload.get("intake_order_id"),
        overwrite=payload.get("overwrite", True),
    )
    result["state"] = update_job_state(job_dir, "results_published", f"results published to {result['target_dir']}")
    return result


@app.get("/jobs/{job_id}/production-status")
def get_job_production_status(job_id: str) -> dict:
    return production_status(_require_job(job_id))


@app.get("/jobs/{job_id}/audit")
def get_job_audit(job_id: str) -> dict:
    job_dir = _require_job(job_id)
    audit_files = [
        "job_state.json",
        "apdl_audit.json",
        "ansys_run_audit.json",
        "evaluation_summary.json",
        "audit_comments.json",
        "report_audit.json",
    ]
    return {name: _read_json(job_dir / name) for name in audit_files if (job_dir / name).exists()}
