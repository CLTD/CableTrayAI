# Spectrum Config Confirmation Workflow

Real ANSYS is blocked until `input.json` records:

```json
{
  "metadata": {
    "spectrum_config_confirmed": true
  }
}
```

The confirmation can be written by:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\confirm_spectrum_config.ps1 -JobId <job_id>
```

This confirmation means a human has reviewed project, building, area, elevation, damping, level, direction, and interpolation behavior.
