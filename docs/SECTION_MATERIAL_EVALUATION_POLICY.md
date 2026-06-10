# Section And Material Evaluation Policy

## Intake Column I

The intake workbook column I is headed as 埋件/埋板 in the early forms, but its effective engineering meaning for this workflow is the square steel section size.

Policy:

- Treat column I as `square_section_spec`.
- Do not treat it as an embedded plate result.
- First-pass intake is expected to leave this value blank in future workflows.
- When blank, the job records `auto_selection_required`.
- CableTrayAI must run square steel section candidates from local `*.SECT` files and select a candidate whose controlling stress ratio is `<= 1.0`.
- Production economic target is `0.60 <= ratio <= 0.9999`. A passing candidate inside `0.60 <= ratio <= 0.75` is treated as potentially conservative, so the selector runs exactly one immediately lower intake-allowed section before final selection.
- The selected section must not be larger than necessary. Similar-intake learning and section-modulus estimates may choose the first candidate, but they cannot accept a result without current real ANSYS and deterministic evaluation.
- No production result may claim final section optimization until the selected candidate has been run through real ANSYS and deterministic evaluation.

## Material Allowables

The material allowable formulas and values are locked for this workflow. Bending is not the only allowable; tension/normal, bending, shear, and accident multipliers must all come from the traced workbook formulas.

| Material | tension/normal MPa | bending MPa | shear MPa | accident multiplier |
| --- | ---: | ---: | ---: | ---: |
| Q355 | `159.75` | `234.30` | `142.00` | `1.5450422535` |
| Q235 | `105.75` | `155.10` | `94.00` | `1.66` |

Formula source:

- normal/tension: `min(0.45*Sy, 0.37*Su)`;
- bending: `min(0.66*Sy, 0.55*Su)`;
- shear: `min(0.4*Sy, 0.33*Su)`;
- accident multiplier: `if Su >= 1.2*Sy then min(1.66, 1.167*Su/Sy) else 1.4`.

Default rule:

- Non-steel-platform support members use Q355.
- Steel-platform square support uses Q235 bending allowable conservatively, because only the square steel contacts the steel platform.
- Other steel-platform support parts continue to use Q355.

This policy affects section selection and evaluation. It does not replace the standard solve or result extraction command streams.

Implementation:

- `core/optimizer/square_section_selector.py`
- `core/optimizer/square_section_workflow.py`
- `core/pipeline/one_click.py`
- `core/evaluators/material_allowables.py`
- `core/evaluators/material_policy.py`

## Production Gate

When `metadata.square_section_selection_status = auto_selection_required`, the one-click production workflow now blocks formal calculation until section trials are run. The trial policy is:

1. copy the rendered job into a separate `_square_section_trials/<job_id>/<timestamp>/` workspace;
2. replace only the first square-support `SECREAD` with each candidate square `*.SECT`;
3. run real ANSYS and deterministic evaluation for the first learned/estimated candidate;
4. if the first candidate is outside `0.60 <= ratio <= 0.9999`, run at most one section-modulus correction candidate;
5. if a passing larger candidate is inside `0.60 <= ratio <= 0.75`, run exactly one immediately lower intake-allowed candidate; if it fails, keep the already passing larger section;
6. choose the candidate with controlling square-support ratio `<= 1.0` inside the economic band when available;
7. apply the selected section back to `input.json` and `generated_model.mac`;
8. run the final real calculation once with the selected section.

If no candidate satisfies `ratio <= 1.0`, the job fails. It must not continue with an oversized default section or a guessed manual value.
