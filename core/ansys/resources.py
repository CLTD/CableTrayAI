from __future__ import annotations

import math
import os
from dataclasses import dataclass


DEFAULT_NPROC_PERCENT = 0.35


@dataclass(frozen=True)
class CpuResources:
    logical_processors: int


@dataclass(frozen=True)
class EffectiveNproc:
    nproc: int | None
    source: str
    logical_processors: int
    nproc_percent: float | None


def detect_cpu_resources() -> CpuResources:
    return CpuResources(logical_processors=max(1, int(os.cpu_count() or 1)))


def _normalise_percent(nproc_percent: float | None) -> float | None:
    if nproc_percent is None:
        return None
    if nproc_percent <= 0:
        return None
    return min(1.0, float(nproc_percent))


def effective_ansys_nproc(
    configured_nproc: int | None = None,
    nproc_percent: float | None = DEFAULT_NPROC_PERCENT,
    *,
    logical_processors: int | None = None,
) -> int | None:
    if configured_nproc and configured_nproc > 0:
        return int(configured_nproc)

    percent = _normalise_percent(nproc_percent)
    if percent is None:
        return None

    logical = max(1, int(logical_processors or detect_cpu_resources().logical_processors))
    return max(1, min(logical, int(math.floor(logical * percent))))


def resolve_ansys_nproc(
    configured_nproc: int | None = None,
    nproc_percent: float | None = DEFAULT_NPROC_PERCENT,
    *,
    logical_processors: int | None = None,
) -> EffectiveNproc:
    logical = max(1, int(logical_processors or detect_cpu_resources().logical_processors))
    nproc = effective_ansys_nproc(
        configured_nproc,
        nproc_percent,
        logical_processors=logical,
    )
    if configured_nproc and configured_nproc > 0:
        source = "explicit_nproc"
    elif nproc is None:
        source = "disabled"
    else:
        source = "percent_of_logical_processors"
    return EffectiveNproc(
        nproc=nproc,
        source=source,
        logical_processors=logical,
        nproc_percent=_normalise_percent(nproc_percent),
    )

