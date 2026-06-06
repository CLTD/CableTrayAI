# CableTrayAI Stage 4 Summary

Stage 4 adds the controlled path for first real ANSYS integration while keeping the default behavior non-executing.

Completed items:

- Added real-run guard checks in `core/ansys/real_run_guard.py`.
- Updated `core/ansys/runner.py` so real ANSYS cannot run without explicit confirmation.
- Added PowerShell scripts for real-run preparation, one-time confirmed real run, output import, and self-check.
- Added real output directory validation and import in `core/results/real_output_validator.py` and `core/results/real_output_importer.py`.
- Added API support for confirmed real-run requests and importing already-completed output directories.
- Added report structure comparison in `core/report/reference_compare.py`.
- Preserved the rule that imported real outputs are explicitly marked as `external_real_output_import`.
- Added read-only ANSYS executable discovery and a default real-output import directory.
- Added explicit ANSYS candidate selection for writing a local dry-run `config/ansys.local.toml`.
- Strengthened real-run guard so spectrum configuration must be explicitly confirmed.
- Added Stage 4 unit and integration tests, bringing the suite to 91 collected tests after the candidate-selection patch.
- Generated `jobs/s2_real_run_candidate` as a dry-run real-run candidate package; ANSYS was not executed.
- Ran read-only ANSYS discovery on this workstation; 56 candidates were reported and no automatic selection was made.

Real ANSYS status:

- Real ANSYS was not run during development.
- The default path remains `mock` or `dry_run`.
- A real run requires `config/ansys.local.toml`, passing preflight, a valid executable, confirmed spectrum configuration, and explicit confirmation.

Validation commands:

```powershell
pytest -q
rg --pcre2 -n "1818|7\.5m|(?<![A-Za-z])NB(?![A-Za-z])" core apps templates
powershell -ExecutionPolicy Bypass -File scripts\stage4_self_check.ps1
```

Source material policy:

- `source_materials` remains read-only.
- No source material files are modified by Stage 4 tools.
