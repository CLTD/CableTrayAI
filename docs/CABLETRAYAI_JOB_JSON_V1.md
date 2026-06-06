# CableTrayAI Job JSON v1

## Purpose

`CableTrayAI Job JSON v1` is the handoff contract between the intake side, CableTrayAI, and the local ANSYS calculation chain.

The immediate target is still local ANSYS execution. The schema is designed so that another department can later provide structured intake data directly, instead of relying on variable Excel layouts.

Schema file:

```text
data/schemas/cabletray_job_v1.schema.json
```

Example file:

```text
data/schemas/cabletray_job_v1.example.json
```

## Non-Negotiable Rules

1. JSON is an engineering input contract, not a place to hide corrections.
2. Report numbers may be absent in first intake. Use `intake_id` / `calculation_batch` until the formal report number is added.
3. Spectrum configuration must be confirmed before real ANSYS execution.
4. If square tube size is not supplied, the section must be selected by candidate calculation: ratio `< 1.0` and closest to `1.0`.
5. Steel-platform rows use static method; non-steel-platform rows use response spectrum unless discipline review explicitly overrides.
6. Source references must be present. A JSON record without traceability cannot be released to ANSYS.
7. Report comparison may find historical conflicts, but must not rewrite JSON facts.

## Main Blocks

| Block | Owner | Purpose |
| --- | --- | --- |
| `job_identity` | Intake / CableTrayAI | Intake id, calculation batch, optional report number, source workbook row. |
| `project` | Intake / spectrum reviewer | Project code, building, area, elevation. |
| `analysis` | CableTrayAI + discipline rule | Static or response-spectrum method, classification, load levels and directions. |
| `support` | Intake parser | Support family, side type, layer counts, steel-platform contact. |
| `materials` | CableTrayAI evaluator | Q355/Q235 policy and allowable source reference. |
| `section` | Intake or optimizer | Square tube size or candidate-selection policy. |
| `tray_layers` | Intake parser | Tray width, load, equivalent density, side/layer identity. |
| `spectrum` | Spectrum selector | Workbook, building, elevation, damping, interpolation evidence. |
| `loads` | Command renderer | Dead weight/seismic load metadata. |
| `output` | Operator | Output root and folder naming policy. |
| `traceability` | All parties | Source refs, creator, review status. |

## Deployment Workflow

```text
Excel intake or direct JSON
  -> validate against cabletray_job_v1.schema.json
  -> confirm spectrum workbook/config
  -> render generated_model.mac / generated_solve.mac / generated_post.mac
  -> run local ANSYS
  -> parse result.json and figures_manifest.json
  -> deterministic evaluation / Excel authoritative evaluation
  -> report template injection
```

## Review Status

`traceability.review_status` has three levels:

- `draft`: parsed or hand-entered, not yet reviewed.
- `discipline_reviewed`: reviewed by the responsible discipline, but not necessarily released.
- `approved_for_ansys`: may be used for real local ANSYS execution.

The web UI should block real ANSYS if the JSON is missing required fields, has unconfirmed spectrum config, or is still `draft` where the site policy requires review.

## Why This Matters

Once multiple departments collaborate, unstructured Excel text becomes the main risk. The JSON contract makes every calculation input explicit and reviewable:

- no hidden row-number assumptions;
- no hard-coded project/building/elevation;
- no silent report-number dependency;
- no unclear square-section choice;
- no untraceable spectrum selection.
