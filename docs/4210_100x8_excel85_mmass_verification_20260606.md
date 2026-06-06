# 4210 100x8 Excel 8.5 Spectrum + MMASS Verification

Date: 2026-06-06

Purpose: verify whether the coworker workbook `C:/Users/duxy/Desktop/楼层谱1818 ANSYS格式 标高线性-8.5.xlsm` and corresponding missing-mass/ZPA values make 4210 `100-100-8` exceed ratio 1.0.

## Inputs

- Base model job: `jobs/diagnostic_4210_100x8_vbaspectrum_20260605_212110/18185NI-LXSJ4210_100-100-8`
- Diagnostic job: `jobs/diagnostic_4210_100x8_excel85_mmass_20260606_011434/18185NI-LXSJ4210_100-100-8_excel85_mmass`
- Spectrum source: Excel `包络谱` active sheet, `ANSYS Format` column M output, not the lower-level segmented source table.
- Spectrum workbook SHA256: `61a413b71c9c483674cab7eb68d50556147b92b66d49c4c67fb4b316357e0ca5`

## Spectrum Blocks

The diagnostic uses the workbook output blocks labeled:

- `!SL-1(XY) 7%  Envelop:(NR_1818,8.5)`, 93 points, peak `0.561g`, 100 Hz/ZPA `0.182g`
- `!SL-1(Z) 7%  Envelop:(NR_1818,8.5)`, 77 points, peak `0.609g`, 100 Hz/ZPA `0.253g`
- `!SL-2(XY) 10%  Envelop:(NR_1818,8.5)`, 93 points, peak `1.737g`, 100 Hz/ZPA `0.477g`
- `!SL-2(Z) 10%  Envelop:(NR_1818,8.5)`, 79 points, peak `1.523g`, 100 Hz/ZPA `0.425g`

`MMASS,ON,<ZPA>` is inserted per spectrum direction in `ansys_spectrum_sl1.mac` and `ansys_spectrum_sl2.mac`.

## Real ANSYS Result

Real ANSYS completed successfully:

- `ansys_run_audit.json`: status `success`, return code `0`, duration `157.10s`
- Extra figure export was intentionally disabled for this diagnostic; LIS/OUP and deterministic evaluation were produced.

Controlling deterministic result:

- `square_support.support_tension_bending_combined_accident = 0.8245120550433136`
- Material: `q355`
- Accident bending: `288.639968 MPa / 362.0034 MPa = 0.7973404890672298`
- Accident tension+bending combined still satisfies `< 1.0`.

Comparison:

- Current 8.45 workbook-VBA 100x8 diagnostic: `0.8229657592534583`
- Excel 8.5 ANSYS Format + MMASS diagnostic: `0.8245120550433136`
- Difference: about `+0.00155`, not enough to explain a manual result above 1.0.

Conclusion: the 8.45 vs Excel-interpolated 8.5 spectrum elevation, even with corresponding MMASS/ZPA values, is not the root cause of the coworker/manual `100-100-8 > 1.0` discrepancy.
