# Spectrum XLSM Configuration

Stage 3 strengthens spectrum parsing with `core/spectra/config_schema.py`.

The parser supports two modes:

1. Auto header detection for flat tables.
2. Explicit config-driven parsing for real XLSM formats.

## Config Shape

```json
{
  "workbook_pattern": "*.xlsm",
  "sheet": "Spectrum",
  "header_row": 1,
  "defaults": {
    "project_code": "CUSTOM",
    "building": "CUSTOM-BUILDING",
    "area": "CUSTOM-AREA",
    "elevation": 10.0,
    "damping": 0.1,
    "level": "SL-2"
  },
  "columns": {
    "project_code": "A",
    "building": "B",
    "area": "C",
    "elevation": "D",
    "damping": "E",
    "level": "F",
    "direction": "G",
    "frequency_hz": "H",
    "acceleration_g": "I",
    "acceleration_columns": {}
  }
}
```

For workbooks with one frequency column and one acceleration column per direction, use:

```json
{
  "columns": {
    "frequency_hz": "A",
    "acceleration_columns": {
      "X": "B",
      "Y": "C",
      "Z": "D"
    }
  }
}
```

The config is not a unique or final format. It is designed so other projects and workbook layouts can be added without changing core code.
