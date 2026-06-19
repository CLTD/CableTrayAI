# General S2 post-extraction topology validation - 2026-06-19

## Scope

User provided `C:/Users/duxy/Desktop/Desktopuxyb/03 导出数据-S2.PIP` as the generic S2 result-extraction stream and emphasized that tray-width families must not be mixed: single-width, double-side, 100/200, 300, 500/600, and mixed tray-width models all need matched modeling and extraction topology.

## Source check

The provided generic extraction file is byte-identical to the curated repo resource:

- `C:/Users/duxy/Desktop/Desktopuxyb/03 导出数据-S2.PIP`
- `resources/current_type_command_flows/single_mixed_600_500_300_200_100/03_extract_s2.PIP`
- SHA256: `39FC214B136A101F104559173A33081112338D7D60C9E2335C019F04D6E6E24A`

Therefore this turn did not replace the standard resource. The fix is to keep generated post-processing aligned with this standard and prevent unsafe fallback extraction.

## LS-FORCE policy

The generic `LS-FORCE` block uses the suffix-9 keypoint family:

- front: `509/609/709 + layer offset`
- back: `1509/1609/1709 + layer offset`

Production post-processing now follows that exactly:

1. `templates/apdl/post_extract_s2.mac.j2` no longer rewrites `KYALS%I%` to `KYALS%I%-3` or `KYALS%I%-101`.
2. `core/results/result_assembler.py` no longer publishes `LS-FORCE-NODES.LIS` suffix-6, suffix-7, suffix-8, or suffix-2 rows as replacement bolt loads when suffix-9 rows are missing.
3. Non-suffix-9 rows remain diagnostic evidence only. If `LS-FORCE.LIS` is zero and no non-zero suffix-9 node envelope exists, result validation fails instead of publishing a wrong connection load.

This prevents the exact failure class where physical bolt geometry points are accidentally treated as tray-arm connection-load points.

## Representative command-flow audit

Static render audit root:

`jobs/type_mix_command_audit_20260619_200315/summary.json`

Representative coverage:

| Case | Result selector topology | L3/L5 and offset result |
|---|---|---|
| double same 100 | source `TYPE=1`; TMAX `TYPE=1` minus section 1 | `L3=0.15`, channel `SECOFFSET,user,,-0.03249` |
| double same 200 | source `TYPE=1`; TMAX `TYPE=1` minus section 1 | `L3=0.15`, channel offset |
| double same 300 | source `TYPE=1`; TMAX `TYPE=1` minus section 1 | `L3=0.15`, channel offset |
| double same 500, 100 square | source `TYPE=1`; TMAX `TYPE=1` minus section 1 | `L3=0.20`, channel offset |
| double same 600, 140 square | source `TYPE=1`; TMAX `TYPE=1` minus section 1 | `L3=0.15`, plain `SECOFFSET,user` |
| single mixed 300+600 | `CTAI_TYPE1_ELEMS` for MAX; `CTAI_ARM_ELEMS` for TMAX; arms+trays for TBMODEL | component topology; no source selector mixing |
| single mixed 600+500+300+200+100 | component topology | per-layer mixed topology retained |
| double grouped 500+600, 120 square | component topology | `L5=0.20`; `L3/L4` are tray-width variables |
| double grouped 500+600, 160 square | component topology | `L5=0.15`; `L3/L4` are tray-width variables |
| double grouped 100+200+300+500+600 | component topology | all tray widths rendered under the grouped mixed flow |

All audit cases had:

- `ls_force_selector.status = pass`
- no `KYSEL`
- no `KYALS%I%-3`
- no `KYALS%I%-101`

## Verification

Commands run:

```text
D:/miniconda3/python.exe -m pytest tests/unit/test_apdl_post_extract_template.py tests/unit/test_postprocessor_alignment.py tests/unit/test_result_assembler_connection_nodes.py tests/unit/test_result_validity_square_section.py tests/unit/test_intake_standard_family_tray_widths.py -q
```

Result: `78 passed`.

```text
D:/miniconda3/python.exe -m py_compile core/apdl/ls_force_topology.py core/apdl/intake_standard_family_renderer.py core/apdl/postprocessor_alignment.py core/results/result_assembler.py core/validation/result_validity_gate.py
```

Result: passed.

```text
D:/miniconda3/python.exe -m pytest tests/unit -q
```

Result: full unit suite passed, `269 passed`.

```text
git diff --check
```

Result: no whitespace errors. Git only reported pre-existing line-ending normalization warnings on already modified files.

## Decision

Keep the standard suffix-9 LS-FORCE publication rule. Do not publish suffix-6/7/8 physical bolt points or suffix-2 CP interface rows as formal tray-arm connection loads. If a model lacks the suffix-9 interface required by the generic S2 post stream, the correct behavior is to block publication and keep diagnostic files, not to silently substitute another keypoint family.
