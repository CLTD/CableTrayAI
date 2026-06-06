from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


RESULT_CACHE_VERSION = "2026-05-24.command-input-figure5-v2"

IDENTITY_METADATA_KEYS = {
    "report_number",
    "calculation_batch",
    "intake_order_id",
    "provisional_intake_id",
    "intake_identity_status",
    "intake_row_number",
    "intake_sheet",
    "raw_intake_row",
}

REUSABLE_OUTPUT_PATTERNS = (
    "*.LIS",
    "*.lis",
    "*.oup",
    "*.OUP",
    "*.bmp",
    "*.BMP",
    "*.png",
    "*.PNG",
    "*.out",
    "*.err",
)


def _json_clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_clean(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_json_clean(item) for item in value]
    return value


def _command_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalise_input(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned = json.loads(json.dumps(payload, ensure_ascii=False))
    metadata = cleaned.get("metadata")
    if isinstance(metadata, dict):
        for key in IDENTITY_METADATA_KEYS:
            metadata.pop(key, None)
    return _json_clean(cleaned)


def compute_exact_result_cache_key(job_dir: Path | str) -> dict[str, Any]:
    job_dir = Path(job_dir)
    input_payload = json.loads((job_dir / "input.json").read_text(encoding="utf-8"))
    signature_payload = {
        "version": RESULT_CACHE_VERSION,
        "input": _normalise_input(input_payload),
        "commands": {
            "generated_model.mac": _command_hash(job_dir / "generated_model.mac"),
            "generated_solve.mac": _command_hash(job_dir / "generated_solve.mac"),
            "generated_post.mac": _command_hash(job_dir / "generated_post.mac"),
            "ansys_spectrum.mac": _command_hash(job_dir / "ansys_spectrum.mac"),
        },
    }
    text = json.dumps(signature_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {"version": RESULT_CACHE_VERSION, "key": hashlib.sha256(text.encode("utf-8")).hexdigest()}


def _index_path(jobs_dir: Path) -> Path:
    return jobs_dir / "_exact_result_cache.json"


def _read_index(jobs_dir: Path) -> dict[str, Any]:
    path = _index_path(jobs_dir)
    if not path.exists():
        return {"version": RESULT_CACHE_VERSION, "entries": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": RESULT_CACHE_VERSION, "entries": {}}
    if payload.get("version") != RESULT_CACHE_VERSION:
        return {"version": RESULT_CACHE_VERSION, "entries": {}}
    entries = payload.get("entries")
    return {"version": RESULT_CACHE_VERSION, "entries": entries if isinstance(entries, dict) else {}}


def _write_index(jobs_dir: Path, payload: dict[str, Any]) -> None:
    path = _index_path(jobs_dir)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _result_is_usable(job_dir: Path) -> bool:
    validation = job_dir / "result_validation.json"
    result = job_dir / "result.json"
    if not validation.exists() or not result.exists():
        return False
    try:
        return json.loads(validation.read_text(encoding="utf-8")).get("status") == "pass"
    except Exception:
        return False


def find_exact_cached_result(job_dir: Path | str, jobs_dir: Path | str) -> dict[str, Any]:
    job_dir = Path(job_dir)
    jobs_dir = Path(jobs_dir)
    cache_key = compute_exact_result_cache_key(job_dir)
    index = _read_index(jobs_dir)
    entry = (index.get("entries") or {}).get(cache_key["key"])
    if not isinstance(entry, dict):
        return {"status": "miss", **cache_key}
    source_dir = Path(str(entry.get("job_dir") or ""))
    if not source_dir.exists() or source_dir.resolve() == job_dir.resolve():
        return {"status": "miss", **cache_key}
    if not _result_is_usable(source_dir):
        return {"status": "stale", "source_job_dir": str(source_dir), **cache_key}
    return {"status": "hit", "source_job_dir": str(source_dir), **cache_key}


def register_exact_cached_result(job_dir: Path | str, jobs_dir: Path | str) -> dict[str, Any]:
    job_dir = Path(job_dir)
    jobs_dir = Path(jobs_dir)
    if not _result_is_usable(job_dir):
        return {"status": "not_registered", "reason": "result_validation_not_pass"}
    cache_key = compute_exact_result_cache_key(job_dir)
    index = _read_index(jobs_dir)
    index.setdefault("entries", {})[cache_key["key"]] = {"job_dir": str(job_dir)}
    _write_index(jobs_dir, index)
    return {"status": "registered", **cache_key}


def copy_exact_cached_outputs(source_job_dir: Path | str, target_job_dir: Path | str) -> dict[str, Any]:
    source_job_dir = Path(source_job_dir)
    target_job_dir = Path(target_job_dir)
    copied: list[str] = []
    for pattern in REUSABLE_OUTPUT_PATTERNS:
        for source in source_job_dir.glob(pattern):
            if not source.is_file():
                continue
            destination = target_job_dir / source.name
            shutil.copy2(source, destination)
            copied.append(source.name)
    audit = {
        "status": "reused_exact_input_real_result",
        "source_job_dir": str(source_job_dir),
        "copied_files": sorted(set(copied)),
        "policy": "Only reused when normalized input and generated command streams are byte-identical; no report values are used.",
    }
    (target_job_dir / "ansys_run_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return audit
