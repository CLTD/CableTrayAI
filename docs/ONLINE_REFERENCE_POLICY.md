# Online Reference Policy

## Purpose

CableTrayAI can use high-quality online references to improve tooling, skills, UI design, automation patterns, and visualization. Online references must not replace the project authority chain for mechanics calculations.

This policy is intentionally strict: online projects can improve how the platform is built, but the calculation evidence still comes from local engineering sources.

## Allowed Uses

- ANSYS automation practices: prefer official Ansys documentation and official PyAnsys/PyMAPDL repositories.
- Mesh and result visualization: prefer production-tested scientific visualization projects such as PyVista/VTK.
- Web and operator UI patterns: use mature open-source practices such as Apache ECharts for comparison envelopes, but keep the workflow aligned with CableTrayAI jobs.
- Skills and agent workflows: borrow structure from well-maintained public examples only after documenting the source, license, maturity signal, and reason.
- Resource tuning and runner orchestration: use official ANSYS/PyMAPDL guidance to improve configuration fields such as executable path, core count, batch input, and environment variables.

## Forbidden Uses

- Do not take RCC-M formulas, material allowables, or report mappings from unverified web sources.
- Do not replace local `source_materials` command streams with internet examples.
- Do not use GitHub star count as calculation evidence.
- Do not download dependencies automatically in the unit offline deployment path.
- Do not fit parser mappings to whichever report value is numerically closest. Mapping must come from report captions, APDL/PIP command blocks, node/element topology, Excel cells, or explicit source references.

## Reference Selection Rules

1. Prefer official documentation over blogs.
2. Prefer original project repositories over forks.
3. Prefer mature projects with active maintenance, releases, tests, and clear licenses.
4. Record the exact URL and the reason for adoption before changing project behavior.
5. Treat online references as implementation support only; they cannot override local reports, Excel workbooks, APDL/PIP/MAC/SECT files, or real ANSYS output.

## Current Candidate References

| Area | Reference | Use |
| --- | --- | --- |
| MAPDL automation | PyMAPDL official docs, https://mapdl.docs.pyansys.com/version/stable/user_guide/mapdl.html | Candidate future automation layer and runner configuration reference, especially executable path, environment variables, and core-count configuration; not a replacement for APDL source commands. Accessed 2026-05-16. |
| Python MAPDL project maturity | `ansys/pymapdl` GitHub, https://github.com/ansys/pymapdl | Official Ansys-maintained client library and citation/license reference. Its agent/test/documentation practices can inform CableTrayAI skills, but not engineering formulas. Accessed 2026-05-16. |
| 3D mesh/result visualization | PyVista official documentation, https://docs.pyvista.org/index.html | Candidate stack for ANSYS-like mesh views, finite-element stress cloud inspection, and regression screenshots. Accessed 2026-05-16. |
| Web comparison envelopes | Apache ECharts official documentation, https://echarts.apache.org/en/index.html | Candidate stack for report-vs-calculation envelope plots, data zoom, tooltips, and large comparison tables. Accessed 2026-05-16. |
| Web dashboard data mapping | Apache ECharts dataset and visualMap handbook, https://echarts.apache.org/handbook/en/concepts/dataset and https://echarts.apache.org/handbook/en/concepts/visual-map | Informed the dashboard's data-to-visual mapping and envelope-chart structure. The current UI uses native SVG to preserve offline deployment and avoid new runtime dependencies. Accessed 2026-05-17. |
| Mesh visualization roadmap | PyVista official documentation, https://docs.pyvista.org/index.html | Informed the future 3D mesh-view direction for ANSYS-like finite-element visualization. Current web UI keeps a placeholder until node/element connectivity is exported from local ANSYS results. Accessed 2026-05-17. |
| MAPDL batch tracking | PyMAPDL batch documentation, https://mapdl.docs.pyansys.com/version/stable/api/_autosummary/ansys.mapdl.core.pool.MapdlPool.run_batch.html | Informed UI wording around explicit batch status, timeout, and failure visibility. No PyMAPDL dependency or APDL command replacement was introduced. Accessed 2026-05-17. |
| Enterprise upload/data entry | Ant Design Data Entry, https://ant.design/docs/spec/data-entry/ | Informed the production workbench's explicit upload slots, contextual hints, and operator-facing file selection layout. No Ant Design dependency was added. Accessed 2026-05-17. |
| Data list/detail workflow | Ant Design Data List, https://ant.design/docs/spec/data-list/ | Informed the parsed-intake multi-select table and current-row detail workflow. It changes only UI navigation. Accessed 2026-05-17. |
| Enterprise command/grid layout | Microsoft Power Apps modern Fluent design, https://learn.microsoft.com/en-us/power-apps/user/modern-fluent-design | Informed the use of command-like top actions, section separation, and grid/detail operator layout. It does not affect APDL, ANSYS, or formulas. Accessed 2026-05-17. |
| APDL generated square tube section fallback | ANSYS Mechanical APDL Command Reference SECTYPE/SECDATA, https://ansyshelp.ansys.com/public/Views/Secured/corp/v242/en/ans_cmd/Hlp_C_SECTYPE.html and https://ansyshelp.ansys.com/public/Views/Secured/corp/v242/en/ans_cmd/Hlp_C_SECDATA.html | Used only when the local square-tube `.SECT` catalog is exhausted and a final real-ANSYS ratio gate still fails. The fallback writes job-local `SECTYPE,BEAM,HREC` and `SECDATA,W1,W2,t1,t2,t3,t4` with audit metadata; it does not alter formulas, report mappings, or source materials. Accessed 2026-05-18. |
| Modal extraction count policy | PyMAPDL MODOPT/MXPAND command docs, https://mapdl.docs.pyansys.com/version/stable/mapdl_commands/solution/_autosummary/ansys.mapdl.core.Mapdl.modopt.html and https://mapdl.docs.pyansys.com/version/stable/mapdl_commands/solution/_autosummary/ansys.mapdl.core.Mapdl.mxpand.html | Used to confirm that the modal mode count is a solve-time command input, while `Mode.oup` is only a post-run coverage check. CableTrayAI still uses local standard command streams for APDL structure and only extends retry counts when real `Mode.oup` fails the 50 Hz gate. Accessed 2026-05-29. |
| AI model adapter | Qwen3-Coder-Next model card, https://huggingface.co/Qwen/Qwen3-Coder-Next; Qwen3-Coder official blog, https://qwenlm.github.io/blog/qwen3-coder/; Qwen3-Coder GitHub, https://github.com/QwenLM/Qwen3-Coder | Informed the recommendation for a code-focused internal assistant. It only affects AI advisory UI and model selection, not mechanics authority. Accessed 2026-05-20. |
| AI model adapter | DeepSeek-V3.2 Hugging Face model card, https://huggingface.co/deepseek-ai/DeepSeek-V3.2 | Informed the recommendation for reasoning/tool-use quality control when the unit already has a DeepSeek platform. It only affects optional OpenAI-compatible AI chat. Accessed 2026-05-20. |
| AI model adapter | GLM-4.5 official documentation, https://docs.z.ai/guides/llm/glm-4.5 | Informed the backup model recommendation for agent/coding/reasoning use. It does not affect formulas or report mappings. Accessed 2026-05-20. |
| AI serving adapter | vLLM OpenAI-compatible server, https://docs.vllm.ai/serving/openai_compatible_server.html | Informed the decision to keep CableTrayAI model access as a generic `/v1/chat/completions` compatible adapter for the unit intranet model platform. No inference dependency is bundled into the deployment package. Accessed 2026-05-20. |
| Optional DeepSeek comparison | DeepSeek-Coder-V2-Lite-Instruct model card, https://huggingface.co/deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct, and DeepSeek-V3 repository, https://github.com/deepseek-ai/DeepSeek-V3 | Informed the decision not to bundle DeepSeek by default on low-memory Windows PCs, while keeping it available through a stronger unit model platform. Accessed 2026-05-22. |
| UI/UX skill reference | `nextlevelbuilder/ui-ux-pro-max-skill`, https://github.com/nextlevelbuilder/ui-ux-pro-max-skill | Installed as a Codex skill reference for dashboard layout critique and operator-flow review. It affects only UI review workflow and cannot change ANSYS/APDL, formulas, result extraction, or report values. Accessed 2026-05-24. |
| Code graph skill reference | `castlenthesky/codegraph`, https://github.com/castlenthesky/codegraph, and `FalkorDB/code-graph`, https://github.com/FalkorDB/code-graph | Installed as Codex skill references for code navigation, dependency review, and repository reasoning. They are tooling aids only and are not calculation evidence. Accessed 2026-05-24. |
| One-dimensional search strategy | SciPy `minimize_scalar` bounded documentation, https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.minimize_scalar.html | Informed the square-section search design: bounded candidate search should converge around a target interval instead of full catalog sweeps. CableTrayAI does not use SciPy to calculate engineering results; ANSYS and deterministic ratio gates remain authoritative. Accessed 2026-05-30. |
| CAE design optimization workflow | Ansys optiSLang product page, https://www.ansys.com/products/connect/ansys-optislang | Informed the idea of parameterized design points and constraint-guided candidate selection. It affects only candidate ordering and documentation, not APDL source authority, formulas, or report mappings. Accessed 2026-05-30. |

## Adoption Notes

- PyMAPDL documentation confirms that MAPDL launch behavior can be controlled by explicit launch arguments and environment variables such as executable path and processor count. CableTrayAI should keep these as configurable runner settings rather than hardcoded values.
- PyMAPDL's official repository is useful as a mature open-source reference for agent organization, test expectations, contribution hygiene, and license traceability. It is not a source for APDL commands used in this project.
- PyVista is appropriate for future ANSYS-like finite-element mesh and stress visualization because it directly supports scientific 3D mesh/result plotting workflows. Any visualized values must still come from parsed ANSYS results.
- Apache ECharts is appropriate for browser-side comparison envelopes and precision-gate plots because it supports rich chart types, progressive rendering, data transforms, and accessibility features. It must not generate or alter engineering results.

## Application To Current Calibration

For the 1% calibration gate, external references are limited to tooling. The values compared against reports must come from:

1. Generated APDL derived from local standard command streams.
2. Real ANSYS output files.
3. Deterministic parser mappings tied to report captions, command blocks, node/element topology, and Excel formula cells.
4. Report and Excel formulas only where they are used as baseline evidence.

If a report result cannot be reproduced from the available local source commands, the correct status is `blocked` with a source-conflict explanation, not a fitted pass.

## Required Output When Online References Affect Code

Any code change inspired by online material must add or update one of:

- `docs/ONLINE_REFERENCE_POLICY.md`
- a feature-specific design document under `docs/`
- a `source_ref` entry in generated JSON when the online source only affects tooling behavior

The entry must include:

- reference URL
- accessed date
- adopted idea
- affected files
- why it does not alter mechanical formulas or report mappings
