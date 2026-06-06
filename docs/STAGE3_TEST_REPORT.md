# Stage 3 Test Report

## Commands

```powershell
pytest -q
```

Result:

```text
46 passed
```

```powershell
rg --pcre2 -n "1818|7\.5m|(?<![A-Za-z])NB(?![A-Za-z])" core apps templates
```

Result: no matches.

## New Test Areas

- ANSYS config parsing.
- ANSYS command generation.
- ANSYS preflight checks.
- Runner `mock`, `dry_run`, and guarded `real` behavior.
- S2 dry-run sample package builder.
- Formula registry completeness.
- Spectrum config-driven XLSM parsing.
- Stage 3 API endpoints.
- Formal report template structure and audit.
