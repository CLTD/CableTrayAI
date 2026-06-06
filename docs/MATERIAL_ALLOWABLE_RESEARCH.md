# Material Allowable Research

## Scope

This note records the current material allowable source hierarchy for CableTrayAI.

Primary project sources remain:

1. `source_materials/model_commands/上游专业提资/电缆桥架结果评定-q235材料.xlsx`
2. `source_materials/model_commands/上游专业提资/电缆桥架结果评定-06Cr19Ni10材料.xlsx`
3. Existing checked reports and command streams.

Internet research is used as a cross-check only. It does not override the project evaluation workbooks without engineer approval.

## Local Workbook Formulas

From the project Excel workbooks:

| Formula | Workbook source | Meaning |
| --- | --- | --- |
| `min(0.45*Sy, 0.37*Su)` | `Q235!G2`, `应力评定!G2` | normal/tension allowable |
| `min(0.66*Sy, 0.55*Su)` | `Q235!I2`, `应力评定!I2` | bending allowable |
| `min(0.4*Sy, 0.33*Su)` | `Q235!J2`, `应力评定!J2` | shear allowable |
| `if Su >= 1.2*Sy then min(1.66, 1.167*Su/Sy) else 1.4` | `Q235!F3`, `应力评定!F3` | accident allowable multiplier |

Current confirmed values:

| Material | Sy MPa | Su MPa | tension MPa | bending MPa | shear MPa | accident multiplier |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Q235 | 235 | 370 | 105.75 | 155.10 | 94.00 | 1.66 |
| Q355 | 355 | 470 | 159.75 | 234.30 | 142.00 | 1.5450422535 |

## External Cross-Check

- AFCEN describes RCC-M as the design and construction rules for mechanical components of PWR nuclear islands. Public pages confirm the code scope, but detailed material allowable tables are not freely available in the pages checked.
- IAEA INIS also identifies RCC-M as a design/construction rule set for mechanical components of PWR nuclear islands.
- GB 50017-2017 is a civil steel structure design standard. Its public table-of-contents and clause index show Chapter 4 covers materials and design strength parameters, Chapter 6 covers flexural members, Chapter 7 covers axial members, Chapter 11 covers welded/fastener connections, and Chapter 17 covers seismic design.
- A public mirror of GB 50017 clause 4.4 states steel design strength indicators should be adopted by steel grade and thickness/diameter, and separately lists design strength tables for steel, welds, bolts, and rivets.
- GEO5's GB 50017-2017 implementation note states that the standard uses steel design compressive/tension/bending strength and shear strength as material parameters, and derives design strength from yield stress and a resistance sub-coefficient when needed.
- GB/T 34560.2-2017 public preview confirms the Q355 designation meaning: Q is the yield-strength prefix and 355 is the specified minimum upper yield strength in MPa.

Relevant links:

- AFCEN RCC-M: https://www.afcen.com/en/rcc-m/282-rcc-m-2020-9791095971429.html
- IAEA INIS RCC-M record: https://inis.iaea.org/records/dn8t7-2dx45
- GB 50017-2017 outline: https://www.codeofchina.com/standard/GB50017-2017.html
- GB 50017 clause 4.4 mirror: https://gf.cabr-fire.com/m/article-34482.htm
- GEO5 GB 50017-2017 implementation note: https://www.geo5software.com/help/geo5/en/gb-50017-2003-01/
- GB/T 34560.2-2017 public preview: https://www.codeofchina.com/standard/GBT34560.2-2017.html

## Engineering Decision

For this project, the Excel formulas above are closer to the existing nuclear support evaluation workflow than GB 50017 civil structural steel design strengths. Therefore CableTrayAI implements the Excel formulas with source references and uses public standards only as a cross-check.

Any future replacement by a purchased RCC-M clause/table must update:

- `core/evaluators/material_allowables.py`
- `docs/formula_traceability.md`
- golden tests in `tests/golden/`
