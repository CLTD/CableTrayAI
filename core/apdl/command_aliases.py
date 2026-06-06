from __future__ import annotations

import json
from pathlib import Path
from typing import Any


COMMAND_ALIASES = {
    "generated_model.mac": "01_build_model.PIP",
    "generated_solve.mac": "02_solve.mac",
    "generated_post.mac": "03_extract.mac",
}

VISUALIZE_MACRO = "04_visualize.mac"


def write_command_aliases(job_dir: Path | str) -> dict[str, Any]:
    job_dir = Path(job_dir)
    aliases: list[dict[str, Any]] = []
    for source_name, alias_name in COMMAND_ALIASES.items():
        source = job_dir / source_name
        target = job_dir / alias_name
        if source.exists():
            target.write_text(source.read_text(encoding="utf-8", errors="replace"), encoding="utf-8", newline="\n")
            aliases.append({"source": source_name, "alias": alias_name, "status": "written"})
        else:
            aliases.append({"source": source_name, "alias": alias_name, "status": "missing_source"})

    visualize = job_dir / VISUALIZE_MACRO
    if not visualize.exists():
        visualize.write_text(
            "\n".join(
                [
                    "! CableTrayAI visualization macro",
                    "! Exported for command-flow review and mesh/figure generation.",
                    "/POST1",
                    "/SHOW,PNG",
                    "/VIEW,1,1,1,1",
                    "/ESHAPE,1",
                    "EPLOT",
                    "/IMAGE,SAVE,mesh_view,png",
                    "FINISH",
                    "",
                ]
            ),
            encoding="utf-8",
            newline="\n",
        )
    aliases.append({"source": None, "alias": VISUALIZE_MACRO, "status": "written"})

    audit = {
        "status": "pass" if all(item["status"] == "written" for item in aliases) else "warning",
        "aliases": aliases,
        "purpose": "Compatibility with the legacy tray_platform workflow for command-flow calibration.",
    }
    (job_dir / "command_aliases.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return audit
