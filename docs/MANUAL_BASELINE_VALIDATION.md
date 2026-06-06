# Manual Baseline Validation

Baseline comparison is required before claiming precision has been verified.

Supported baseline input:

- `result.json`-like manual result payloads
- hand-imported ANSYS result summaries converted to JSON

If no baseline is supplied, the comparison status is `blocked` and the report states that precision is awaiting baseline validation.

Default tolerance:

- modal frequency relative error <= 5%
- stress relative error <= 5%
- load relative error <= 5%
- stress ratio absolute difference <= 0.03 or relative error <= 5%
