from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


SOURCE_ROOTS = (
    Path("source_materials/model_commands"),
    Path("source_materials/learning_docs"),
)

TEXT_EXTENSIONS = {".txt", ".mac", ".pip", ".sect"}
ENCODINGS = ("utf-8", "gbk", "gb2312")

EXPECTED_SOURCE_PATTERNS = {
    "standard_model_command": "建模标准化命令流.txt",
    "s2_geometry_pip": "*双侧同类型电缆桥架-方钢托臂.PIP",
    "solve_command_mac": "*计算用命令流*.mac",
    "post_extract_s2": "导出数据-S2.PIP",
    "square_tube_section": "100-100-8.SECT",
    "q235_evaluation_workbook": "电缆桥架结果评定-q235材料.xlsx",
    "stainless_evaluation_workbook": "电缆桥架结果评定-06Cr19Ni10材料.xlsx",
    "floor_spectrum_workbook": "楼层谱*ANSYS格式*标高线性.xlsm",
    "completed_report_sample": "*LXSJ4120.docx",
    "seismic_work_manual": "HDLXSC-25A5-02-03 支架、设备抗震分析工作手册.docx",
    "seismic_requirement_manual": "HDLXSC-25A5-01-01 抗震分析规范要求工作手册.pdf",
    "support_standard_atlas": "*T5013*电缆桥架支撑*.pdf",
}


@dataclass(frozen=True)
class SourceFileRecord:
    path: str
    sha256: str
    size_bytes: int
    extension: str
    modified_time_utc: str
    encoding: str | None
    decode_error: str | None = None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _detect_encoding(path: Path) -> tuple[str | None, str | None]:
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        return None, None
    data = path.read_bytes()
    for encoding in ENCODINGS:
        try:
            data.decode(encoding)
            return encoding, None
        except UnicodeDecodeError as exc:
            last_error = str(exc)
    return None, last_error


def _iter_source_files(project_root: Path, roots: Iterable[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        absolute_root = project_root / root
        if not absolute_root.exists():
            continue
        files.extend(path for path in absolute_root.rglob("*") if path.is_file())
    return sorted(files, key=lambda item: item.as_posix().lower())


def build_source_inventory(
    project_root: Path | str = Path("."),
    output_dir: Path | str = Path("docs"),
) -> tuple[list[dict], list[dict]]:
    project_root = Path(project_root).resolve()
    output_dir = project_root / Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    records: list[SourceFileRecord] = []
    warnings: list[dict] = []
    source_files = _iter_source_files(project_root, SOURCE_ROOTS)

    for path in source_files:
        encoding, decode_error = _detect_encoding(path)
        stat = path.stat()
        relative_path = path.relative_to(project_root).as_posix()
        records.append(
            SourceFileRecord(
                path=relative_path,
                sha256=_sha256(path),
                size_bytes=stat.st_size,
                extension=path.suffix.lower(),
                modified_time_utc=datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat(),
                encoding=encoding,
                decode_error=decode_error,
            )
        )
        if decode_error:
            warnings.append(
                {
                    "severity": "warning",
                    "path": relative_path,
                    "issue": "Text source could not be decoded as UTF-8, GBK, or GB2312.",
                }
            )

    for source_root in SOURCE_ROOTS:
        if not (project_root / source_root).exists():
            warnings.append(
                {
                    "severity": "error",
                    "path": source_root.as_posix(),
                    "issue": "Expected source root is missing.",
                }
            )

    for source_key, pattern in EXPECTED_SOURCE_PATTERNS.items():
        found = False
        for root in SOURCE_ROOTS:
            if any((project_root / root).rglob(pattern)):
                found = True
                break
        if not found:
            warnings.append(
                {
                    "severity": "warning",
                    "source_key": source_key,
                    "pattern": pattern,
                    "issue": "Expected reference source was not found.",
                }
            )

    inventory = [asdict(record) for record in records]
    (output_dir / "source_inventory.json").write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "source_warnings.json").write_text(
        json.dumps(warnings, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return inventory, warnings


if __name__ == "__main__":
    build_source_inventory()
