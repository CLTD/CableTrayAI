# Spectrum Format Draft From 1818 Source Workbook

This is an initial draft only. It must not be treated as the only supported format.

Candidate workbook:

```text
source_materials/model_commands/上游专业提资/楼层谱1818 ANSYS格式 标高线性.xlsm
```

Stage 3 does not force-parse the full workbook because real XLSM files may use merged cells, multiple sheets or non-flat layouts. The recommended next step is to confirm:

- sheet name containing spectrum values;
- header row;
- frequency column;
- acceleration columns for X/Y/Z;
- how project, building, area, elevation, damping and SL level are encoded;
- whether interpolation must happen between rows, sheets or named regions.

Once confirmed, encode the mapping using `data/spectra/spectrum_format.example.json`.
