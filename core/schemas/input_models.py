from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ProjectConfig(BaseModel):
    project_code: str
    building: str
    area: str
    elevation: float
    unit_system: str = "SI"
    description: str | None = None


class SpectrumSelection(BaseModel):
    spectrum_file: str
    spectrum_level: str
    damping_ratio: float
    directions: list[str] = Field(default_factory=lambda: ["X", "Y", "Z"])
    source_ref: str | None = None


class MaterialInput(BaseModel):
    material_id: str
    name: str
    elastic_modulus_pa: float
    poisson_ratio: float
    density_kg_m3: float
    yield_strength_mpa: float | None = None
    tensile_strength_mpa: float | None = None
    allowable_normal_mpa: float | None = None
    allowable_shear_mpa: float | None = None
    allowable_tension_mpa: float | None = None
    allowable_compression_mpa: float | None = None
    allowable_bending_mpa: float | None = None
    source_ref: str = "TODO_FORMULA_SOURCE_REQUIRED"


class SectionInput(BaseModel):
    section_id: str
    sect_file: str
    section_type: str = "BEAM_MESH"
    area_mm2: float | None = None
    section_modulus_mm3: float | None = None
    inertia_mm4: float | None = None
    source_ref: str | None = None


class SupportInput(BaseModel):
    support_type: str
    square_tube_width_m: float
    support_height_m: float
    support_spacing_m: float
    layers_front: int
    layers_back: int
    support_section_id: str
    material_id: str
    weld_size_mm: float | None = None
    bolt_count: int | None = None
    source_ref: str | None = None


class TrayLayerInput(BaseModel):
    side: str
    layer_index: int
    tray_width_m: float
    arm_a_length_m: float
    arm_b_length_m: float
    arm_section_id: str
    tray_section_id: str
    tray_density_kg_m3: float
    material_id: str
    source_ref: str | None = None


class LoadCaseInput(BaseModel):
    name: str
    category: str
    spectrum_level: str | None = None
    directions: list[str] = Field(default_factory=list)
    source_ref: str | None = None


class AnsysConfig(BaseModel):
    mode: str = "mock"
    executable_path: str | None = None
    timeout_minutes: int = 120
    keep_failed_job_files: bool = True


class EvaluationConfig(BaseModel):
    formula_policy: str = "traceable_or_todo"
    allow_todo_formula: bool = True
    source_ref: str = "docs/formula_traceability.md"


class ReportConfig(BaseModel):
    template_name: str = "stage1_fixed_docx"
    output_filename: str = "report.docx"
    include_figures: bool = True


class CableTrayInput(BaseModel):
    project: ProjectConfig
    spectrum: SpectrumSelection
    support: SupportInput
    tray_layers: list[TrayLayerInput]
    materials: list[MaterialInput]
    sections: list[SectionInput]
    load_cases: list[LoadCaseInput]
    ansys: AnsysConfig = Field(default_factory=AnsysConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    report: ReportConfig = Field(default_factory=ReportConfig)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def material_by_id(self, material_id: str) -> MaterialInput:
        for material in self.materials:
            if material.material_id == material_id:
                return material
        raise KeyError(f"Unknown material_id: {material_id}")

    def section_by_id(self, section_id: str) -> SectionInput:
        for section in self.sections:
            if section.section_id == section_id:
                return section
        raise KeyError(f"Unknown section_id: {section_id}")


def model_to_dict(model: BaseModel | dict) -> dict:
    if isinstance(model, dict):
        return model
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def parse_cable_input(payload: "CableTrayInput | dict") -> CableTrayInput:
    if isinstance(payload, CableTrayInput):
        return payload
    if hasattr(CableTrayInput, "model_validate"):
        return CableTrayInput.model_validate(payload)
    return CableTrayInput.parse_obj(payload)
