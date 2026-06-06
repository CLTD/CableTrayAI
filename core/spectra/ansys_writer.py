from __future__ import annotations

from pathlib import Path


def spectrum_to_ansys_mac(points: list[dict], damping_ratio: float, output_path: Path | str | None = None) -> str:
    frequencies = ",".join(f"{float(point['frequency_hz']):.8g}" for point in points)
    accelerations = ",".join(f"{float(point['acceleration_g']):.8g}" for point in points)
    content = "\n".join(
        [
            "! Generated response spectrum points",
            f"FREQ,{frequencies}",
            f"SV,{damping_ratio:.8g},{accelerations}",
            "",
        ]
    )
    if output_path is not None:
        Path(output_path).write_text(content, encoding="utf-8", newline="\n")
    return content
