from __future__ import annotations

import json
from pathlib import Path

from core.evaluators.formula_registry import FORMULA_REGISTRY
from core.evaluators.formula_status import TODO_FORMULA_SOURCE_REQUIRED, formula_status


def candidate_source_files(source_root: Path | str = Path("source_materials")) -> list[Path]:
    root = Path(source_root)
    patterns = [
        "*结果评定-q235材料.xlsx",
        "*结果评定-06Cr19Ni10材料.xlsx",
        "*LXSJ4120.docx",
        "*支架、设备抗震分析工作手册.docx",
        "*抗震分析规范要求工作手册.pdf",
    ]
    files: list[Path] = []
    for pattern in patterns:
        files.extend(path for path in root.rglob(pattern) if path.is_file() and not path.name.startswith("~$"))
    return sorted(set(files), key=lambda item: item.as_posix())


def resolve_formula_candidates(
    source_root: Path | str = Path("source_materials"),
    docs_dir: Path | str = Path("docs"),
) -> list[dict]:
    docs_dir = Path(docs_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)
    candidates: list[dict] = []
    source_files = candidate_source_files(source_root)
    for formula_id, record in FORMULA_REGISTRY.items():
        if record.source_ref != TODO_FORMULA_SOURCE_REQUIRED:
            candidates.append(
                {
                    "formula_id": formula_id,
                    "status": "confirmed",
                    "source_ref": record.source_ref,
                    "candidate_files": [],
                    "questions": [],
                }
            )
            continue
        candidates.append(
            {
                "formula_id": formula_id,
                "status": "unconfirmed_todo",
                "source_ref": TODO_FORMULA_SOURCE_REQUIRED,
                "candidate_files": [path.as_posix() for path in source_files],
                "questions": [
                    "Which workbook sheet/cell or standard clause defines this formula?",
                    "What units and applicability conditions govern the formula?",
                    "Which load cases and result fields feed the formula?",
                ],
            }
        )
    (docs_dir / "formula_source_candidates.json").write_text(
        json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# Formula Source Candidates",
        "",
        "| Formula id | Status | Candidate files / source ref | Questions |",
        "| --- | --- | --- | --- |",
    ]
    for item in candidates:
        sources = item["source_ref"] if item["status"] == "confirmed" else "<br>".join(item["candidate_files"])
        questions = "<br>".join(item["questions"])
        lines.append(f"| {item['formula_id']} | {item['status']} | {sources} | {questions} |")
    (docs_dir / "FORMULA_SOURCE_CANDIDATES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return candidates
