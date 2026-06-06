# API Endpoints Production

Production endpoints:

- `POST /jobs/create-from-intake`
- `POST /jobs/{job_id}/confirm-spectrum`
- `POST /jobs/{job_id}/render-apdl`
- `POST /jobs/{job_id}/preflight`
- `POST /jobs/{job_id}/run-real`
- `POST /jobs/{job_id}/export-figures`
- `POST /jobs/{job_id}/import-real-outputs`
- `POST /jobs/{job_id}/evaluate-excel`
- `POST /jobs/{job_id}/report`
- `POST /jobs/{job_id}/compare-baseline`
- `GET /jobs/{job_id}/result`
- `GET /jobs/{job_id}/figures`
- `GET /jobs/{job_id}/figures/{figure_id}/file`
- `GET /jobs/{job_id}/report-audit`
- `GET /jobs/{job_id}/production-status`

Real-run remains guarded by config, preflight, spectrum confirmation, command hash, and explicit confirmation.

`POST /jobs/{job_id}/export-figures` runs ANSYS in post-only mode. It does not solve again; it opens the completed job database/results and exports modal, square-support, and cantilever stress PNG files from the audited `generated_post.mac` plotting logic.
