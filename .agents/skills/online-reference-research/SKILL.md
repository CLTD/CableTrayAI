---
name: online-reference-research
description: Use high-quality online references, official documentation, and mature open-source projects to improve CableTrayAI tooling, skills, visualization, and automation without replacing local calculation authority.
---

# Purpose

Use online references proactively when improving engineering workflow, UI, visualization, ANSYS orchestration, parser robustness, testing patterns, and skills. Online references are implementation aids, not calculation authority.

# Priority

1. Official ANSYS / PyAnsys / PyMAPDL documentation.
2. Official repositories from original maintainers.
3. Mature open-source projects with clear licenses, tests, releases, and active maintenance.
4. High-star or widely cited GitHub projects only as maturity signals, never as formula evidence.

# Approved Current Directions

- PyMAPDL / PyAnsys for future ANSYS automation patterns, executable configuration, batch execution, and resource settings. Start from https://mapdl.docs.pyansys.com/version/stable/user_guide/mapdl.html and https://github.com/ansys/pymapdl.
- PyVista / VTK for finite-element mesh and stress-result visualization. Start from https://docs.pyvista.org/index.html.
- Apache ECharts for browser-side comparison envelopes, error plots, and operator dashboard charts. Start from https://echarts.apache.org/en/index.html.

# Adoption Boundary

Before applying an online pattern, classify it as one of:

- tooling: allowed when documented and tested
- UI/visualization: allowed when values remain traceable to local result JSON
- orchestration: allowed when APDL source commands remain local and auditable
- formula/mapping/material: blocked unless confirmed by local Excel/report/manual/source command evidence

# Forbidden

- Do not replace local APDL/PIP/MAC/SECT command streams with internet examples.
- Do not use online formulas for RCC-M, material allowables, weld checks, bolt checks, or support evaluation unless they are official standards and are separately confirmed against local reports or Excel.
- Do not use GitHub stars as proof of calculation correctness.
- Do not numerically fit result mappings to the closest report value.
- Do not download dependencies automatically in the offline deployment path.

# Required Documentation

When an online reference changes project behavior, update `docs/ONLINE_REFERENCE_POLICY.md` or a feature-specific design document with:

- reference URL
- accessed date
- adopted idea
- affected files
- why the change does not alter mechanical authority

# Calibration Boundary

The 1% calibration gate must still be proven from local evidence:

- standard command streams
- real ANSYS output files
- deterministic parser mappings
- Excel/report formula cells
- explicit report section and figure captions
