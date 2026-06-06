from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


class AnsysRunnerConfig(BaseModel):
    mode: str = "mock"


class AnsysExecutableConfig(BaseModel):
    executable: str | None = None
    default_workdir: str = "jobs"
    timeout_minutes: int = 120
    license_wait: bool = True
    product: str | None = None
    nproc: int | None = None
    nproc_percent: float | None = 0.35
    high_modal_nproc_cap: int | None = None
    high_modal_nproc_cap_threshold: int = 300
    startup_no_output_timeout_seconds: int = 90
    output_stall_timeout_seconds: int = 300
    retry_on_startup_no_output: bool = True
    startup_retry_nproc: list[int] = Field(default_factory=lambda: [4, 2, 1])
    memory: str | None = None
    extra_args: list[str] = Field(default_factory=list)


class OutputImportConfig(BaseModel):
    default_source_dir: str = "outputs"


class AnsysLocalConfig(BaseModel):
    ansys: AnsysExecutableConfig = Field(default_factory=AnsysExecutableConfig)
    runner: AnsysRunnerConfig = Field(default_factory=AnsysRunnerConfig)
    output_import: OutputImportConfig = Field(default_factory=OutputImportConfig)


def _validate_config(payload: dict[str, Any]) -> AnsysLocalConfig:
    if hasattr(AnsysLocalConfig, "model_validate"):
        return AnsysLocalConfig.model_validate(payload)
    return AnsysLocalConfig.parse_obj(payload)


def load_ansys_config(config_path: Path | str = Path("config/ansys.local.toml")) -> AnsysLocalConfig:
    config_path = Path(config_path)
    if not config_path.exists():
        example = config_path.with_name("ansys.local.example.toml")
        if example.exists():
            config_path = example
        else:
            return AnsysLocalConfig()
    payload = tomllib.loads(config_path.read_text(encoding="utf-8-sig"))
    return _validate_config(payload)


def config_to_dict(config: BaseModel | dict) -> dict:
    if isinstance(config, dict):
        return config
    if hasattr(config, "model_dump"):
        return config.model_dump()
    return config.dict()

