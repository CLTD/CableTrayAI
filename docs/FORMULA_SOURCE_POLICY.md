# Formula Source Policy

CableTrayAI must not invent engineering formulas.

## Allowed Formula Sources

1. Authoritative evaluation Excel workbooks:
   - `电缆桥架结果评定-q235材料.xlsx`
   - `电缆桥架结果评定-06Cr19Ni10材料.xlsx`
2. Existing issued reports and their tables.
3. RCC-M / project manuals and standard documents in `source_materials`.
4. Explicit human-confirmed formula records with workbook cell, report table, or clause reference.

## Blocking Rules

- A formula without `source_ref` cannot support a final pass conclusion.
- TODO formulas must remain `unconfirmed_todo` until the Excel cell, report table, or clause is identified.
- If Python replication and Excel authoritative evaluation conflict, the case fails and requires review.
- Mock or dry-run results cannot be used for precision acceptance.

## Current Formula Trace

`docs/formula_traceability.md` is generated from the Excel workbooks and currently records formula cells and manual-confirmation items. This file is an audit artifact and must be regenerated when the Excel workbooks or formula registry change.
