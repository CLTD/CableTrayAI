# ANSYS Real Run Preflight

真实 ANSYS 调用前必须先生成 `jobs/<job_id>/ansys_preflight.json`，并且所有 `fail` 项为零。默认流程仍是 `mock` 或 `dry_run`，不会调用 ANSYS。

## Checks

Preflight checks are implemented in `core/ansys/preflight.py`.

| Check group | Requirement |
| --- | --- |
| Job input | `input.json` exists and parses against the input schema. |
| APDL files | `generated_model.mac`, `generated_solve.mac`, `generated_post.mac` exist. |
| Template rendering | No unreplaced Jinja placeholders remain. |
| Sections | All `input.json:sections` SECT files exist in the job package. |
| Spectrum | `ansys_spectrum.mac` or declared spectrum source exists. |
| Output directories | Job directory and `figures/` directory exist. |
| Hardcoded sample tokens | Generated APDL must not contain sample project/building/elevation tokens. |
| APDL features | BEAM188, SECREAD, LATT, LMESH, CP/CPCYC, constraints, modal, spectrum and post-processing commands. |
| PIP outputs | Key result output names are registered in the manifest. |
| Materials | Material values and units are present. |
| Directions | Coordinate directions are declared. |
| Job state | Current state is not `running` or `failed`. |
| Real executable | For `runner.mode=real`, configured executable must exist. |

If any check returns `fail`, `run_real_ansys` writes a rejected audit and does not execute ANSYS.
