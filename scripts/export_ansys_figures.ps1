param(
    [string]$JobDir,
    [string]$BatchJson,
    [int]$TimeoutMinutes = 30
)

$ErrorActionPreference = "Stop"

if (-not $JobDir -and -not $BatchJson) {
    throw "Provide -JobDir <path> or -BatchJson <precision batch json>."
}

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$python = @'
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from core.ansys.config import load_ansys_config
from core.ansys.figure_export import run_figure_export
from core.results.result_assembler import assemble_result

job_dir_arg = "" if sys.argv[1] == "__NONE__" else sys.argv[1]
batch_json_arg = "" if sys.argv[2] == "__NONE__" else sys.argv[2]
timeout_minutes = int(sys.argv[3])

job_dirs: list[Path] = []
if job_dir_arg:
    job_dirs.append(Path(job_dir_arg))
if batch_json_arg:
    payload = json.loads(Path(batch_json_arg).read_text(encoding="utf-8"))
    for row in payload.get("results", []):
        value = row.get("job_dir")
        if value:
            job_dirs.append(Path(value))

seen: set[str] = set()
config = load_ansys_config()
summary = []
for job_dir in job_dirs:
    job_dir = job_dir.resolve()
    key = job_dir.as_posix().lower()
    if key in seen:
        continue
    seen.add(key)
    audit = run_figure_export(job_dir, config, timeout_minutes=timeout_minutes)
    if (job_dir / "input.json").exists():
        assemble_result(job_dir)
    summary.append(
        {
            "job_dir": str(job_dir),
            "status": audit.get("status"),
            "returncode": audit.get("returncode"),
            "figure_count": audit.get("figure_count"),
            "copied_named_pngs": (audit.get("naming") or {}).get("copied_named_pngs"),
        }
    )
    print(json.dumps(summary[-1], ensure_ascii=False))

if batch_json_arg:
    out = Path("docs/precision_gate") / f"figure_export_batch_{Path(batch_json_arg).stem}.json"
else:
    out = Path("docs/precision_gate/figure_export_batch_summary.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"summary={out}")
'@

$JobArg = if ($JobDir) { $JobDir } else { "__NONE__" }
$BatchArg = if ($BatchJson) { $BatchJson } else { "__NONE__" }
$TmpPy = Join-Path $env:TEMP "cabletray_export_ansys_figures.py"
Set-Content -Encoding UTF8 -Path $TmpPy -Value $python
& python $TmpPy $JobArg $BatchArg $TimeoutMinutes
