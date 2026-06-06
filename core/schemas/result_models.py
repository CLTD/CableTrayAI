from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MetricValue(BaseModel):
    value: float | str | None
    unit: str | None = None
    raw_value: Any | None = None
    source_ref: str


class ModalResult(BaseModel):
    mode: int
    source_mode: int | None = None
    frequency_hz: float
    period_s: float
    mt_cutoff_hz: float | None = None
    mt_mode: int | None = None
    mt_mode_first_above_cutoff_hz: int | None = None
    mt_mode_last_above_cutoff_hz: int | None = None
    modal_cutoff_status: str | None = None
    modal_cutoff_policy: str | None = None
    modal_reporting_min_frequency_hz: float | None = None
    modal_reporting_policy: str | None = None
    mass_x: float | None = None
    mass_y: float | None = None
    mass_z: float | None = None
    source_ref: str
    source_file: str | None = None
    source_hash: str | None = None
    source_line: int | None = None
    source_block: str | None = None
    raw_value: Any | None = None
    normalized_value: Any | None = None
    parser_version: str | None = None


class BeamStressResult(BaseModel):
    load_case: str
    stress_type: str
    element_id: int
    value_mpa: float
    unit: str = "MPa"
    source_ref: str
    source_file: str | None = None
    source_hash: str | None = None
    source_line: int | None = None
    source_block: str | None = None
    raw_value: Any | None = None
    normalized_value: Any | None = None
    parser_version: str | None = None
    component_scope: str | None = None
    report_component_hint: str | None = None
    source_selection_ref: str | None = None


class ForceResult(BaseModel):
    name: str
    load_case: str
    values: dict[str, MetricValue]
    source_ref: str
    source_file: str | None = None
    source_hash: str | None = None
    source_line: int | None = None
    source_block: str | None = None
    raw_value: Any | None = None
    normalized_value: Any | None = None
    parser_version: str | None = None


class FoundationLoad(BaseModel):
    load_case: str
    node: str
    fx: MetricValue
    fy: MetricValue
    fz: MetricValue
    mx: MetricValue
    my: MetricValue
    mz: MetricValue
    source_ref: str
    source_file: str | None = None
    source_hash: str | None = None
    source_line: int | None = None
    source_block: str | None = None
    raw_value: Any | None = None
    normalized_value: Any | None = None
    parser_version: str | None = None


class FigureItem(BaseModel):
    figure_id: str
    path: str
    source_file: str | None = None
    target_file: str | None = None
    category: str
    figure_type: str | None = None
    load_case: str | None = None
    case: str | None = None
    stress_type: str | None = None
    component_scope: str | None = None
    appendix: str | None = None
    caption: str
    source_ref: str


class EvaluationItem(BaseModel):
    check_id: str
    category: str
    calculation_value: float | None
    allowable_value: float | None
    ratio: float | None
    pass_fail: str
    unit: str | None
    source_ref: str
    formula_status: str | None = None
    notes: str | None = None


class ResultJson(BaseModel):
    result_version: str = "stage1"
    project: dict[str, Any]
    modal_results: list[ModalResult] = Field(default_factory=list)
    beam_stress_results: list[BeamStressResult] = Field(default_factory=list)
    weld_force_results: list[ForceResult] = Field(default_factory=list)
    bolt_force_results: list[ForceResult] = Field(default_factory=list)
    foundation_loads: list[FoundationLoad] = Field(default_factory=list)
    figures: list[FigureItem] = Field(default_factory=list)
    evaluation_summary: list[EvaluationItem] = Field(default_factory=list)
    raw_files: dict[str, str] = Field(default_factory=dict)
    generated_at: str


def model_to_dict(model: BaseModel | dict) -> dict:
    if isinstance(model, dict):
        return model
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()
