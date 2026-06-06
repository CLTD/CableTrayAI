# Stage 2 Test Report

## Commands

```powershell
pytest -q
```

Result:

```text
19 passed
```

```powershell
rg --pcre2 -n "1818|7\.5m|(?<![A-Za-z])NB(?![A-Za-z])" core apps templates
```

Result: no matches.

## Coverage Added

- APDL template source gap checks.
- PIP output manifest extraction.
- Realistic LIS parser edge cases.
- Formula registry golden tests.
- Spectrum interpolation selector.
- Report field mapping and report audit consistency.
- API job state persistence.
