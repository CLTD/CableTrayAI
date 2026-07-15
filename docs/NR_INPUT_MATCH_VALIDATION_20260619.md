# NR input-matched validation - 2026-06-19

Scope: only NR factory baseline comparison from `C:/Users/duxy/Desktop/2`.

## Case

- Report: `18185NI-LXSJ4249`
- Building/area: `NR`
- Elevation: `26.2 m`
- Geometry: double-side 2+2 layers, 600 mm trays
- Square section: `140-140-8`
- Baseline report: `C:/Users/duxy/Desktop/2/18185NI-LXSJ4249/18185NI-LXSJ4249.docx`
- Source model: `C:/Users/duxy/Desktop/2/18185NI-LXSJ4249/计算文件/01双侧同类型电缆桥架-方钢托臂.PIP`
- Source solve replayed for this diagnostic: `C:/Users/duxy/Desktop/2/18185NI-LXSJ4249/计算文件/02计算用命令流AR  8.55 7-10.mac`
- Diagnostic job: `jobs/nr_input_matched_20260619_170940/18185NI-LXSJ4249_source_solve`

## Input alignment

The generated model matches the source model on the governing parameters:

- `H1=0.14`
- `H2=1.4`
- `L1=0.67`
- `L2=0.6`
- `L3=0.15`
- `L4=2.0`
- `SECREAD,'140-140-8'`
- `YIXINGGANG150` / `YIXINGGANG150DAN`
- `600-75-2mm`
- yixing secondary-arm offset is `SECOFFSET,user`

The first production comparison did not use identical solve input. It used the current controlled solve template with full workbook-replicated spectrum and `MT=80`, while the baseline report source solve uses embedded simplified `NR_1818@26.2` spectrum blocks and `MT=60`.

This diagnostic replayed the source solve command stream while keeping the current generated model and current post-processing stream.

## Real ANSYS result

Real ANSYS 18.2 finished successfully:

- `ansys_run_audit.status = success`
- `returncode = 0`
- `Mode.oup` covers the 50 Hz gate with `MT=60`

The diagnostic validation gate failed only because figure export was intentionally skipped (`run_post_exports=False`) for this numeric replay. Numeric LIS/OUP outputs were present.

## Numeric comparison

Key values:

| Metric | Current controlled solve | Source-solve replay | Baseline report | Source replay error |
|---|---:|---:|---:|---:|
| upset bending stress, MPa | 61.95 | 62.67 | 62.41 | 0.41% |
| faulted bending stress, MPa | 261.23 | 289.31 | 289.32 | 0.00% |
| faulted tension+bending ratio | 0.7391 | 0.8167 | 0.82 | 0.40% |
| SL-1 JCZH FY, N | 4112.6 | 4311.4 | 4151.5 | 3.85% |
| SL-1 JCZH MX, Nm | 4728.3 | 4961.4 | 4783.6 | 3.72% |
| SL-2 JCZH FY, N | 18789.9 | 21254.3 | 21254.8 | 0.00% |
| SL-1 HF FY, N | 1082.9 | 1140.4 | 1106.0 | 3.11% |
| SL-1 LS FY, N | 1054.5 | 1110.6 | 1077.3 | 3.09% |

Interpretation:

1. The large stress/ratio mismatch in the current controlled solve is caused by solve-input mismatch, especially the spectrum command representation and MT policy.
2. When the source solve stream is replayed, the governing stress table aligns with the historical report.
3. Remaining failures are limited to several SL-1 load components at about 3% to 4%. Since the `18185NI-LXSJ4249` desktop folder contains no separate historical result-extraction command stream or historical LIS files, this cannot yet be proven as a production post-processing bug. It may be historical report/export drift.
4. The previous spectrum-file blocking issue is not present for this NR case. It applied to a NB sample whose requested elevation had no acceptable common workbook spectrum elevation under the current no-snap-down policy.

## Decision

Do not claim the whole `C:/Users/duxy/Desktop/2` historical baseline is fully accepted yet.

For NR 4249 specifically, model generation and deterministic stress evaluation are consistent when the calculation input is made consistent. Further load-table reconciliation needs either the historical LIS files or the exact historical post-processing command stream.
