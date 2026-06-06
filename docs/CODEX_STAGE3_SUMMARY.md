# Codex Stage 3 Summary

Stage 3 prepares CableTrayAI for controlled real ANSYS integration while keeping default execution safe.

## Completed

- ANSYS config loader: `core/ansys/config.py`
- ANSYS command builder: `core/ansys/command_builder.py`
- Real-run preflight: `core/ansys/preflight.py`
- Runner modes: `mock`, `dry_run`, `real`
- Dry-run and real-run scripts: `scripts/run_ansys_dry_run.ps1`, `scripts/run_ansys_real.ps1`
- S2 dry-run sample builder: `core/jobs/sample_job_builder.py`
- Formula TODO resolver and candidate report: `core/evaluators/formula_resolver.py`
- Report template upgrade and `.docx` template: `templates/report/s2_report_template.docx`
- Spectrum XLSM config schema: `core/spectra/config_schema.py`
- API Stage 3 endpoints for preflight, dry-run, real-run gate, command, figures and report audit

## Verification

```powershell
pytest -q
```

Result: `46 passed`.

```powershell
rg --pcre2 -n "1818|7\.5m|(?<![A-Za-z])NB(?![A-Za-z])" core apps templates
```

Result: no matches.

## Real ANSYS Policy

Real execution is rejected unless:

- `config/ansys.local.toml` exists;
- `runner.mode = "real"`;
- `ansys.executable` exists;
- preflight passes;
- the real-run interface/script is explicitly called.
