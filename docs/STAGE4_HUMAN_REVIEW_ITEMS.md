# Stage 4 Human Review Items

Before the first real ANSYS run, a human reviewer must confirm:

- The correct ANSYS executable has been selected from `docs/ansys_discovery.json`.
- `config/ansys.local.toml` has been created from the desired candidate with `scripts/select_ansys_candidate.ps1`; the generated config must remain `runner.mode = "dry_run"` until real-run review is complete.
- `runner.mode = "real"` is intentional.
- `ansys.executable` exists on this machine.
- `jobs/<job_id>/ansys_preflight.json` has no `fail` checks.
- `input.json` includes `metadata.spectrum_config_confirmed = true` or root `spectrum_config_confirmed = true`.
- The spectrum workbook/configuration has been reviewed for project, building, area, elevation, damping, level, and direction.
- The operator is prepared to pass the explicit `-IUnderstandThisWillRunANSYS` flag.

For imported outputs:

- Confirm `E:\CODEX\tray_platform\ANSYS Output` is the intended source directory, or override `-SourceDir`.
- Confirm the directory contains real ANSYS outputs, not CableTrayAI mock files.
- Review `real_output_validation.json` before relying on `result.json`.
