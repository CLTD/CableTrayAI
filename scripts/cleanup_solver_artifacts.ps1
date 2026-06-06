param(
    [string]$JobsRoot = "jobs"
)

$ErrorActionPreference = "Stop"

@"
from pathlib import Path
import json

from core.ansys.artifact_cleanup import cleanup_heavy_solver_artifacts

root = Path(r"$JobsRoot")
if not root.exists():
    print(json.dumps({"status": "missing_jobs_root", "jobs_root": str(root)}, ensure_ascii=False, indent=2))
    raise SystemExit(0)

summaries = []
for job in sorted([p for p in root.rglob("*") if p.is_dir()]):
    if any((job / name).exists() for name in ("generated_model.mac", "ansys_run_audit.json", "result.json")):
        audit = cleanup_heavy_solver_artifacts(job)
        if audit.get("removed_count"):
            summaries.append({
                "job_dir": str(job),
                "removed_count": audit.get("removed_count"),
                "removed_gb": audit.get("removed_gb"),
            })

payload = {
    "status": "pass",
    "jobs_root": str(root),
    "cleaned_job_count": len(summaries),
    "removed_gb": round(sum(float(item.get("removed_gb") or 0) for item in summaries), 3),
    "cleaned_jobs": summaries,
}
print(json.dumps(payload, ensure_ascii=False, indent=2))
"@ | python -
