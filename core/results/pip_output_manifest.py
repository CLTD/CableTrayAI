from __future__ import annotations

import json
import re
from pathlib import Path

from core.apdl.source_diff import read_text_with_encoding


KNOWN_RESULT_OUTPUTS = {
    "SQUAREBEAMSTRESS.LIS": ("square support section-1 stress extrema", "beam_stress_results", "支架方钢应力评定表"),
    "MAXBEAMSTRESS.LIS": ("beam stress extrema", "beam_stress_results", "支架评定表"),
    "TMAXBEAMSTRESS.LIS": ("tray stress extrema", "beam_stress_results", "支架评定表"),
    "JCZH.LIS": ("foundation reactions", "foundation_loads", "基础载荷表"),
    "HF-FORCE.LIS": ("weld force extraction", "weld_force_results", "焊缝评定表"),
    "LS-FORCE.LIS": ("bolt force extraction", "bolt_force_results", "螺栓载荷表"),
    "Mode.oup": ("modal frequencies", "modal_results", "模态频率表"),
}


def _normalize_output_name(name: str, extension: str | None = None) -> str:
    clean = name.strip().strip("'\"")
    if extension:
        ext = extension.strip().strip("'\"").lstrip(".")
        if ext:
            clean = f"{clean}.{ext}"
    return clean


def _figure_metadata(filename: str) -> tuple[str, str | None, str | None, str]:
    stem = Path(filename).stem.upper()
    if stem == "SHITI":
        return "model", None, None, "整体模型图"
    if stem.startswith("MOTAI-"):
        return "modal", None, None, "模态图"
    match = re.match(r"^T?([ABD])[-_]?(\d?)(SDIR[12]?|SBEND\d?|SHEAR)", stem)
    if match:
        case = match.group(1)
        stress_type = match.group(3)
        return "stress", case, stress_type, "应力图"
    return "figure", None, None, "图片"


def parse_pip_output_manifest(pip_path: Path | str) -> list[dict]:
    pip_path = Path(pip_path)
    text, encoding = read_text_with_encoding(pip_path)
    outputs: dict[str, dict] = {}
    for line_no, line in enumerate(text.splitlines(), start=1):
        cfopen = re.search(r"\*CFOPEN\s*,\s*([^,\s]+)\s*,\s*([^,\s!]+)", line, re.IGNORECASE)
        if cfopen:
            filename = _normalize_output_name(cfopen.group(1), cfopen.group(2))
            purpose, result_field, report_section = KNOWN_RESULT_OUTPUTS.get(
                filename,
                ("text output", "result_raw", "附录"),
            )
            outputs[filename] = {
                "output_filename": filename,
                "file_type": Path(filename).suffix.lstrip(".").upper(),
                "purpose": purpose,
                "result_json_field": result_field,
                "report_section": report_section,
                "source_ref": f"{pip_path.name}:{line_no}",
                "encoding": encoding,
            }
        output = re.search(r"/OUTPUT\s*,\s*([^,\s]+)\s*,\s*([^,\s!]+)", line, re.IGNORECASE)
        if output:
            filename = _normalize_output_name(output.group(1), output.group(2))
            purpose, result_field, report_section = KNOWN_RESULT_OUTPUTS.get(
                filename,
                ("solver text output", "result_raw", "附录"),
            )
            outputs[filename] = {
                "output_filename": filename,
                "file_type": Path(filename).suffix.lstrip(".").upper(),
                "purpose": purpose,
                "result_json_field": result_field,
                "report_section": report_section,
                "source_ref": f"{pip_path.name}:{line_no}",
                "encoding": encoding,
            }
        image = re.search(r"/IMAGE\s*,\s*SAVE\s*,\s*([^,\s!]+)\s*,\s*([^,\s!]+)", line, re.IGNORECASE)
        if image:
            filename = _normalize_output_name(image.group(1), image.group(2))
            figure_type, case, stress_type, report_section = _figure_metadata(filename)
            outputs[filename] = {
                "output_filename": filename,
                "file_type": Path(filename).suffix.lstrip(".").upper(),
                "purpose": figure_type,
                "result_json_field": "figures",
                "report_section": report_section,
                "case": case,
                "stress_type": stress_type,
                "source_ref": f"{pip_path.name}:{line_no}",
                "encoding": encoding,
            }
    return sorted(outputs.values(), key=lambda item: item["output_filename"])


def write_pip_output_manifest(
    pip_path: Path | str = Path("source_materials/model_commands/导出数据-S2.PIP"),
    docs_dir: Path | str = Path("docs"),
) -> list[dict]:
    docs_dir = Path(docs_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)
    manifest = parse_pip_output_manifest(pip_path)
    (docs_dir / "pip_output_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# PIP Output Manifest",
        "",
        "| Output file | Purpose | result.json field | Report section | Source ref |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in manifest:
        lines.append(
            f"| {item['output_filename']} | {item['purpose']} | {item['result_json_field']} | {item['report_section']} | {item['source_ref']} |"
        )
    (docs_dir / "PIP_OUTPUT_MANIFEST.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest
