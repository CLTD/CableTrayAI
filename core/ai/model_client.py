from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = Path("config/ai.local.toml")
EXAMPLE_CONFIG = Path("config/ai.local.example.toml")

UNIT_MODEL_PRESETS = [
    {
        "preset_id": "qwen3-coder-30b",
        "display_name": "Qwen3-coder-30B（默认：命令流/代码理解）",
        "base_url": "http://models.ai.cnpe.cc/deepseek32b/v1",
        "model": "Qwen3-coder-30B",
        "api_key_env": "",
        "timeout_seconds": 60,
        "recommended": True,
        "role": "提资意图解析、APDL/PIP/MAC 命令计划审核、网页/部署修复建议",
        "reason": "单位清单中最贴近代码和命令流生成/审查的模型；默认用于 CableTrayAI。",
    },
    {
        "preset_id": "deepseek-r1-32b",
        "display_name": "DeepSeek-R1-32B（推理质控）",
        "base_url": "http://models.ai.cnpe.cc/deepseek32b/v1",
        "model": "DeepSeek-R1-32B",
        "api_key_env": "",
        "timeout_seconds": 90,
        "recommended": False,
        "role": "异常原因分析、规范边界解释、人工审核意见整理",
        "reason": "更适合推理归因，但不直接生成最终工程命令。",
    },
    {
        "preset_id": "qwen3-235b",
        "display_name": "Qwen3-235B（高精度复核）",
        "base_url": "http://models.ai.cnpe.cc/qwen235b/v1",
        "model": "Qwen3-235B",
        "api_key_env": "",
        "timeout_seconds": 120,
        "recommended": False,
        "role": "疑难样例复核、长上下文报告/命令流冲突审查",
        "reason": "参数规模最大，适合深度复核；可能比 30B 慢，不作为默认实时巡检。",
    },
    {
        "preset_id": "qwen3-32b",
        "display_name": "Qwen3-32B（通用质控）",
        "base_url": "http://models.ai.cnpe.cc/qwen32b/v1",
        "model": "Qwen3-32B",
        "api_key_env": "",
        "timeout_seconds": 60,
        "recommended": False,
        "role": "通用问答、日志解释和轻量质控",
        "reason": "通用能力均衡，作为 Qwen3-coder-30B 不可用时的备选。",
    },
    {
        "preset_id": "qwen2_5-vl-7b",
        "display_name": "Qwen2.5-VL-7B（图纸/图片识别备选）",
        "base_url": "http://models.ai.cnpe.cc/deepseek32b/v1",
        "model": "Qwen2.5-VL-7B",
        "api_key_env": "",
        "timeout_seconds": 90,
        "recommended": False,
        "role": "后续图纸、图片和扫描件识别；当前电缆桥架计算链路不默认使用",
        "reason": "多模态模型，适合后续扩展；当前 OpenAI-compatible 文本接口不一定开放图片输入。",
    },
]

MODEL_TASK_ROUTES = {
    "auto": {
        "preset_id": "qwen3-coder-30b",
        "label": "自动路由",
        "timeout_seconds": 24,
        "max_tokens": 384,
        "purpose": "默认由任务类型自动选择模型；模型不可达时明确标记，不伪装成功。",
    },
    "chat": {
        "preset_id": "qwen3-32b",
        "label": "日常对话",
        "timeout_seconds": 24,
        "max_tokens": 320,
        "purpose": "普通问题、日志解释和简短指导，优先速度。",
    },
    "engineering_qc": {
        "preset_id": "qwen3-coder-30b",
        "label": "工程质控",
        "timeout_seconds": 28,
        "max_tokens": 420,
        "purpose": "提资意图、命令流计划、报告注入和部署修复建议。",
    },
    "run_monitor": {
        "preset_id": "deepseek-r1-32b",
        "label": "实时巡检",
        "timeout_seconds": 28,
        "max_tokens": 180,
        "purpose": "运行状态、失败任务和异常归因；短请求但不把规则兜底伪装成模型返回。",
    },
    "postprocess_qc": {
        "preset_id": "deepseek-r1-32b",
        "label": "后处理质控",
        "timeout_seconds": 28,
        "max_tokens": 420,
        "purpose": "UNKNOWN 节点、全零载荷、缺图、公式待确认等风险解释。",
    },
    "safe_fix": {
        "preset_id": "qwen3-coder-30b",
        "label": "安全修复建议",
        "timeout_seconds": 28,
        "max_tokens": 420,
        "purpose": "网页、部署、配置、日志和已验证解析问题的安全修复建议。",
    },
    "deep_review": {
        "preset_id": "qwen3-235b",
        "label": "疑难复核",
        "timeout_seconds": 45,
        "max_tokens": 700,
        "purpose": "疑难样例、历史报告/源文件冲突和长上下文复核；不用于实时巡检。",
    },
}


SYSTEM_KNOWLEDGE = """你是 CableTrayAI 电缆桥架智能力学分析平台的本地质控助手。
你必须先理解本项目流程：提资 Excel / 反应谱文件 -> 标准化 APDL/PIP/MAC/SECT 模板 -> generated_model.mac / generated_solve.mac / generated_post.mac 三份命令流 -> ANSYS real_run 或 real_imported 输出 -> LIS/OUP/BMP/PNG/RST/OUT/ERR 解析 -> Python confirmed formulas 或 job 本地 Excel 权威评定副本 -> 固定 Word 模板注入 -> report_audit.json。
你参与的方式是“大模型理解和质控 + 软件确定性执行”：模型可以解析提资意图、提出命令计划、审查日志和指出风险；最终 APDL/PIP/MAC 仍由平台从标准源命令流编译，计算仍由 ANSYS 执行，评定仍由 Excel/确定性公式/source_ref 约束。
你只能做实时质控、错误归因、日志解释、修复建议、部署/配置/网页问题的安全修复辅助。
结论边界：
1. 建模命令来自标准化 APDL/PIP/MAC 模板，不能凭空改力学逻辑。
2. 计算权威来自 ANSYS real_run 或 real_imported 输出。
3. 评定权威来自已确认 Python 公式、规范 source_ref 或 job 本地 Excel 权威评定副本。
4. result.json 中缺源、UNKNOWN 节点、全零关键载荷、未确认公式、缺图片时，不得建议自动通过。
5. 可自动修复的范围仅限部署脚本、端口、路径、网页显示、配置缺失、日志定位、已验证的非工程性解析问题。
6. APDL/PIP 力学逻辑、材料许用值、评定公式、结果映射、报告结论只能生成补丁建议、证据、验证命令和回退说明；不得直接把工程结论改成通过。
7. 任何修复建议必须说明 evidence、影响范围、验证方式和是否需要人工审核。"""

FAST_CHAT_SYSTEM_KNOWLEDGE = """你是 CableTrayAI 本地质控助手。回答必须短、直接、可执行。
边界：大模型只做日志解释、错误归因、部署/网页/配置修复建议和工程质控提示；不得替代 ANSYS、Excel 权威评定、确定性公式、source_ref 或人工审核。
遇到 UNKNOWN 节点、关键载荷全零、缺图、未确认公式、mock/dry_run、result_validation fail 时，必须提示阻断风险，不得建议直接通过。
不要把上下文中没有出现的问题当成已经发生；没有证据时说“需要检查”，不要说“已经失败”。
默认用 3-6 条中文要点回答，先给结论，再给操作步骤；只有用户要求详细时才展开。"""

PROJECT_KNOWLEDGE_PACK = {
    "software": "CableTrayAI 电缆桥架智能力学分析平台",
    "active_scope": "电缆桥架 S2 支架智能计算、结果提取、评定、图片提取、模板报告和本地 AI 质控",
    "authoritative_chain": [
        "提资 Excel / 谱文件配置",
        "标准化 APDL/PIP/MAC/SECT 命令流",
        "generated_model.mac / generated_solve.mac / generated_post.mac 三份可审查命令",
        "ANSYS real_run 或 real_imported 输出",
        "LIS/OUP/BMP/PNG/RST/OUT/ERR 解析",
        "Python confirmed formulas 或 job-local Excel 权威评定副本",
        "固定 Word 模板注入和 report_audit.json",
    ],
    "forbidden": [
        "不能把 mock/dry_run 作为正式工程结论",
        "不能为贴近历史报告而硬改数据",
        "不能用大模型替代 ANSYS、Excel、规范公式或 source_ref",
        "不能在 UNKNOWN 节点、关键载荷全零、公式未确认、图片缺失时建议通过",
        "不能自动修改 source_materials",
    ],
    "known_quality_gates": [
        "三份命令流必须存在且可审查",
        "Fig.5.1/5.2 必须来自 ANSYS 模型图 SHITI/TBMODEL",
        "第六章表格必须按报告章节映射，不按数值接近匹配",
        "附录C按方钢截面和模板章节逻辑选择托臂云图或焊缝评定原理",
        "正式报告只替换模板中的表格数值和图片，不自由排版",
    ],
    "safe_autofix_policy": {
        "auto_allowed": [
            "部署脚本路径、端口和启动检查",
            "网页显示、按钮状态、配置读取和错误提示",
            "已验证的文件命名、输出目录整理、日志定位",
            "不会改变工程结论的 parser 防御性错误处理",
        ],
        "human_review_required": [
            "APDL/PIP 建模、载荷、约束和后处理集合",
            "材料许用值、RCC-M/Excel 评定公式",
            "result.json 关键数值映射和报告正式结论",
            "任何可能让不通过项变成通过项的修改",
        ],
    },
}

_MOJIBAKE_MARKERS = ("Ã", "Â", "å", "æ", "ç", "è", "é", "ä", "\x80", "\x81", "\x82", "\x83", "\x84", "\x85", "\x86", "\x87", "\x88", "\x89")


def _cjk_count(text: str) -> int:
    return sum(1 for char in text if "\u4e00" <= char <= "\u9fff")


def _looks_like_mojibake(text: str) -> bool:
    if not text:
        return False
    marker_count = sum(text.count(marker) for marker in _MOJIBAKE_MARKERS)
    return marker_count >= 2 and _cjk_count(text) == 0


def _repair_mojibake_text(text: str) -> str:
    """Repair common UTF-8-as-Latin-1 model responses without touching valid Chinese."""
    if not _looks_like_mojibake(text):
        return text
    try:
        repaired = text.encode("latin1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    if _cjk_count(repaired) > _cjk_count(text) + 2:
        return repaired
    return text

def model_presets() -> list[dict[str, Any]]:
    return [dict(item) for item in UNIT_MODEL_PRESETS]


def model_task_routes() -> dict[str, dict[str, Any]]:
    return {key: dict(value) for key, value in MODEL_TASK_ROUTES.items()}


def _route_for_mode(mode: str | None) -> dict[str, Any]:
    clean = str(mode or "engineering_qc").strip() or "engineering_qc"
    if clean in {"conversation", "general", "general_chat"}:
        clean = "chat"
    return dict(MODEL_TASK_ROUTES.get(clean) or MODEL_TASK_ROUTES["engineering_qc"])


def _apply_task_route(config: dict[str, Any], mode: str | None) -> tuple[dict[str, Any], dict[str, Any]]:
    route = _route_for_mode(mode)
    configured_preset_id = _match_preset(config.get("base_url", ""), config.get("model", ""))
    routed_preset = _preset_by_id(route.get("preset_id")) or _default_preset()

    def manual_config(reason: str) -> tuple[dict[str, Any], dict[str, Any]]:
        manual = dict(config)
        manual["selected_preset_id"] = config.get("selected_preset_id") or configured_preset_id
        manual["timeout_seconds"] = min(int(config.get("timeout_seconds") or route["timeout_seconds"]), int(route["timeout_seconds"]))
        manual_route = dict(route)
        manual_route["label"] = f"当前模型/{route.get('label', mode or '质控')}"
        manual_route["manual_model"] = True
        manual_route["routing_reason"] = reason
        manual_route["requested_preset_id"] = route.get("preset_id")
        return manual, manual_route
    if not config.get("routing_enabled", True):
        return manual_config("routing_disabled")
    if not configured_preset_id or configured_preset_id != routed_preset.get("preset_id"):
        return manual_config("configured_model_primary")
    if not config.get("routing_enabled", True):
        manual = dict(config)
        manual["selected_preset_id"] = config.get("selected_preset_id") or _match_preset(config.get("base_url", ""), config.get("model", ""))
        manual["timeout_seconds"] = min(int(config.get("timeout_seconds") or route["timeout_seconds"]), int(route["timeout_seconds"]))
        return manual, {**route, "label": f"手动模型/{route.get('label', mode or '质控')}", "manual_model": True}
    preset = _preset_by_id(route.get("preset_id")) or _default_preset()
    routed = dict(config)
    routed["base_url"] = preset["base_url"]
    routed["model"] = preset["model"]
    routed["api_key_env"] = config.get("api_key_env") or preset.get("api_key_env", "")
    routed["timeout_seconds"] = min(int(config.get("timeout_seconds") or route["timeout_seconds"]), int(route["timeout_seconds"]))
    routed["selected_preset_id"] = preset["preset_id"]
    return routed, route


def _preset_by_id(preset_id: str | None) -> dict[str, Any] | None:
    if not preset_id:
        return None
    wanted = str(preset_id).strip()
    return next((dict(item) for item in UNIT_MODEL_PRESETS if item["preset_id"] == wanted), None)


def _default_preset() -> dict[str, Any]:
    return next((dict(item) for item in UNIT_MODEL_PRESETS if item.get("recommended")), dict(UNIT_MODEL_PRESETS[0]))


def _match_preset(base_url: str, model: str) -> str:
    clean_url = str(base_url or "").strip().rstrip("/")
    clean_model = str(model or "").strip()
    for preset in UNIT_MODEL_PRESETS:
        if preset["base_url"].rstrip("/") == clean_url and preset["model"] == clean_model:
            return preset["preset_id"]
    return ""


def _parse_toml_like(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    try:
        import tomllib

        return tomllib.loads(text)
    except Exception:
        data: dict[str, Any] = {}
        section: dict[str, Any] = data
        for raw_line in text.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                continue
            if line.startswith("[") and line.endswith("]"):
                section = data.setdefault(line[1:-1].strip(), {})
                continue
            if "=" not in line:
                continue
            key, value = [part.strip() for part in line.split("=", 1)]
            section[key] = value.strip('"')
        return data


def _as_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


def _load_config(config_path: Path | str = DEFAULT_CONFIG) -> dict[str, Any]:
    path = Path(config_path)
    if not path.exists() and path == DEFAULT_CONFIG and EXAMPLE_CONFIG.exists():
        path = EXAMPLE_CONFIG
    if not path.exists():
        preset = _default_preset()
        return {
            "enabled": False,
            "base_url": preset["base_url"],
            "model": preset["model"],
            "api_key_env": "",
            "timeout_seconds": int(preset.get("timeout_seconds") or 60),
            "routing_enabled": True,
            "selected_preset_id": preset["preset_id"],
        }
    data = _parse_toml_like(path)
    provider = data.get("provider") or data
    if not isinstance(provider, dict):
        provider = {}
    preset = _default_preset()
    return {
        "enabled": str(provider.get("enabled", "true")).lower() == "true",
        "base_url": provider.get("base_url") or preset["base_url"],
        "model": provider.get("model") or preset["model"],
        "api_key_env": provider.get("api_key_env", ""),
        "timeout_seconds": int(provider.get("timeout_seconds", 60)),
        "routing_enabled": _as_bool(provider.get("routing_enabled"), True),
        "selected_preset_id": provider.get("preset_id") or _match_preset(provider.get("base_url") or preset["base_url"], provider.get("model") or preset["model"]),
    }


def public_model_config(config_path: Path | str = DEFAULT_CONFIG) -> dict[str, Any]:
    path = Path(config_path)
    config = _load_config(path)
    return {
        "configured": path.exists(),
        "enabled": config["enabled"],
        "base_url": config["base_url"],
        "model": config["model"],
        "api_key_env": config["api_key_env"],
        "api_key_env_set": bool(config["api_key_env"] and os.environ.get(config["api_key_env"], "")),
        "timeout_seconds": config["timeout_seconds"],
        "config_path": str(path),
        "adapter": "openai_compatible",
        "selected_preset_id": config.get("selected_preset_id") or _match_preset(config["base_url"], config["model"]),
        "authority": "LLM parses intent and audits risks; deterministic ANSYS/Excel/formula gates remain authoritative.",
        "routing_enabled": bool(config.get("routing_enabled", True)),
        "routing_policy": "按任务类型自动选择单位模型；模型不可达时明确标记并给出规则辅助，不伪装成模型返回。",
    }

def write_model_config(payload: dict[str, Any], config_path: Path | str = DEFAULT_CONFIG) -> dict[str, Any]:
    path = Path(config_path)
    preset = _preset_by_id(payload.get("preset_id")) or None
    payload_model = str(payload.get("model") or "").strip()
    payload_base_url = str(payload.get("base_url") or "").strip().rstrip("/")
    use_preset_model = bool(preset) and (not payload_model or payload_model == str(preset["model"]).strip())
    if preset and use_preset_model:
        base_url = str(preset["base_url"]).strip().rstrip("/")
        model = str(preset["model"]).strip()
        api_key_env = str(payload.get("api_key_env") if "api_key_env" in payload else preset.get("api_key_env", "")).strip()
        timeout_seconds = int(payload.get("timeout_seconds") or preset.get("timeout_seconds") or 60)
    else:
        default = _default_preset()
        base_url = payload_base_url or (str(preset["base_url"]).strip().rstrip("/") if preset else str(default["base_url"]).strip().rstrip("/"))
        model = payload_model or str(default["model"]).strip()
        api_key_env = str(payload.get("api_key_env") or "").strip()
        timeout_seconds = int(payload.get("timeout_seconds") or default.get("timeout_seconds") or 60)
    enabled = bool(payload.get("enabled", True))
    routing_enabled = _as_bool(payload.get("routing_enabled"), True)
    if not base_url.startswith(("http://", "https://")):
        raise ValueError("base_url must start with http:// or https://")
    if not model:
        raise ValueError("model is required")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(
        [
            "[provider]",
            "# OpenAI-compatible unit intranet endpoint selected from CableTrayAI vetted presets.",
            f"enabled = {'true' if enabled else 'false'}",
            f'base_url = "{base_url}"',
            f'model = "{model}"',
            f'api_key_env = "{api_key_env}"',
            f"timeout_seconds = {timeout_seconds}",
            f"routing_enabled = {'true' if routing_enabled else 'false'}",
            f'preset_id = "{_match_preset(base_url, model)}"',
            "",
        ]
    )
    path.write_text(text, encoding="utf-8")
    return public_model_config(path)


def probe_model_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
    base_url = str(payload.get("base_url") or "").strip().rstrip("/")
    model = str(payload.get("model") or "").strip()
    api_key_env = str(payload.get("api_key_env") or "").strip()
    timeout_seconds = int(payload.get("timeout_seconds") or 20)
    if not base_url.startswith(("http://", "https://")):
        raise ValueError("base_url must start with http:// or https://")

    api_key = os.environ.get(api_key_env, "") if api_key_env else ""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    models_url = base_url + "/models"
    available_models: list[str] = []
    models_error = ""
    try:
        request = urllib.request.Request(models_url, headers=headers, method="GET")
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
        data = body.get("data", []) if isinstance(body, dict) else []
        for item in data:
            if isinstance(item, dict) and item.get("id"):
                available_models.append(str(item["id"]))
    except Exception as exc:  # noqa: BLE001 - probe must report all endpoint variants
        models_error = str(exc)

    selected_model = model or (available_models[0] if available_models else "")
    chat_status = "skipped"
    chat_error = ""
    sample_answer = ""
    if selected_model:
        try:
            config = {
                "base_url": base_url,
                "model": selected_model,
                "api_key_env": api_key_env,
                "timeout_seconds": timeout_seconds,
            }
            result = _call_openai_compatible(
                config,
                {
                    "mode": "connection_probe",
                    "authority_policy": "Probe only; do not provide engineering conclusions.",
                },
                "请只回复：CableTrayAI unit model connection ok",
                fast=True,
                max_tokens=48,
            )
            chat_status = "pass"
            sample_answer = _repair_mojibake_text(str(result.get("answer") or ""))[:500]
        except Exception as exc:  # noqa: BLE001
            chat_status = "fail"
            chat_error = str(exc)

    status = "pass" if chat_status == "pass" else "fail"
    return {
        "status": status,
        "base_url": base_url,
        "models_endpoint": "pass" if available_models else "warning",
        "models_error": models_error,
        "available_models": available_models[:50],
        "selected_model": selected_model,
        "chat_status": chat_status,
        "chat_error": chat_error,
        "sample_answer": sample_answer,
        "auth_policy": "no_key" if not api_key_env else ("env_key_set" if api_key else "env_key_missing"),
        "message": "Endpoint is usable for CableTrayAI advisory AI." if chat_status == "pass" else "Endpoint probe did not complete a real chat/completions call; check /v1 path, model name, firewall, and API compatibility.",
    }


def model_recommendations() -> list[dict[str, str]]:
    return [
        {
            "name": item["model"],
            "role": item["role"],
            "why": item["reason"],
            "deployment": f"{item['base_url']} / {item['model']}",
            "source": "C:/Users/duxy/Desktop/模型清单.txt",
        }
        for item in UNIT_MODEL_PRESETS
    ]


def ai_runtime_policy() -> dict[str, Any]:
    return {
        "status": "pass",
        "default_preset_id": "qwen3-coder-30b",
        "routing_enabled": True,
        "routes": model_task_routes(),
        "latency_policy": {
            "run_monitor_timeout_seconds": MODEL_TASK_ROUTES["run_monitor"]["timeout_seconds"],
            "chat_timeout_seconds": MODEL_TASK_ROUTES["chat"]["timeout_seconds"],
            "deep_review_timeout_seconds": MODEL_TASK_ROUTES["deep_review"]["timeout_seconds"],
            "fallback": "单位模型超时、502、不可达或返回异常时，会明确标记 model_unavailable；规则质控只作临时辅助，不伪装成模型结果，也不替代 ANSYS/Excel/报告审计。",
        },
        "authority_boundary": PROJECT_KNOWLEDGE_PACK["safe_autofix_policy"],
        "project_knowledge_pack": PROJECT_KNOWLEDGE_PACK,
    }


def _attachment_summary(path: Path, *, max_chars: int = 5000) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "path": str(path),
        "filename": path.name,
        "exists": path.exists(),
    }
    if not path.exists() or not path.is_file():
        return summary
    summary["size_bytes"] = path.stat().st_size
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".json", ".csv", ".tsv", ".toml", ".ini", ".py", ".ps1", ".html", ".js", ".css", ".mac", ".lis", ".oup", ".out", ".err"}:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        summary["text_excerpt"] = text[:max_chars]
        summary["truncated"] = len(text) > max_chars
    else:
        summary["note"] = "Binary or Office file; only filename, size and path are provided to the model. Use deterministic parsers for engineering data."
    return summary


def _normalise_attachments(attachments: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not isinstance(attachments, list):
        return items
    cwd = Path.cwd().resolve()
    upload_root = (cwd / "uploads").resolve()
    for item in attachments[:5]:
        raw_path = item.get("path") if isinstance(item, dict) else item
        if not raw_path:
            continue
        path = Path(str(raw_path))
        if not path.is_absolute():
            path = cwd / path
        try:
            resolved = path.resolve()
        except OSError:
            continue
        # Keep the general AI workbench on uploaded/operator files.  It should
        # not casually exfiltrate original source_materials into a model prompt.
        if upload_root not in [resolved, *resolved.parents]:
            items.append({"path": str(path), "exists": resolved.exists(), "blocked": "Only files under uploads/ are passed to the AI workbench."})
            continue
        items.append(_attachment_summary(resolved))
    return items


def chat_with_model(
    message: str,
    *,
    job_dir: Path | str | None = None,
    config_path: Path | str = DEFAULT_CONFIG,
    mode: str = "engineering_qc",
    attachments: Any = None,
    run_context: dict[str, Any] | None = None,
    conversation: Any = None,
) -> dict[str, Any]:
    config = _load_config(config_path)
    context = {
        "mode": mode,
        "job_id": Path(job_dir).name if job_dir else None,
        "project_scope": PROJECT_KNOWLEDGE_PACK["active_scope"],
        "authority_boundary": PROJECT_KNOWLEDGE_PACK["authoritative_chain"],
        "forbidden": PROJECT_KNOWLEDGE_PACK["forbidden"],
    }
    if job_dir:
        context["job_summary"] = _context_summary(Path(job_dir))
    if run_context:
        context["run_context"] = run_context
    if isinstance(conversation, list):
        compact_conversation = []
        for item in conversation[-8:]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip()
            content = str(item.get("content") or "").strip()
            if role not in {"user", "assistant"} or not content:
                continue
            compact_conversation.append({"role": role, "content": content[:1800]})
        if compact_conversation:
            context["recent_conversation"] = compact_conversation
    attachment_summary = _normalise_attachments(attachments)
    if attachment_summary:
        context["attachments"] = attachment_summary
    if not config["enabled"]:
        result = _rule_based_response(context, message)
        result["status"] = "fallback"
        return result
    try:
        wants_detail = any(word in str(message or "") for word in ("详细", "展开", "逐项", "完整", "全部"))
        request_config, route = _apply_task_route(config, mode)
        max_tokens = int(route.get("max_tokens") or 384)
        if wants_detail and mode not in {"run_monitor", "chat"}:
            max_tokens = min(max_tokens + 260, 900)
        result = _call_openai_compatible(request_config, context, message, fast=True, max_tokens=max_tokens)
        result["route"] = route
        result["selected_preset_id"] = request_config.get("selected_preset_id")
        return result
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        result = _rule_based_response(context, message)
        result["status"] = "model_unavailable"
        result["provider"] = "rule_based_after_model_error"
        result["answer"] = "单位模型没有完成真实返回；下面只是规则质控的临时提示，不等同于模型回复。请先修复模型连接或选择可用模型。"
        result["model_error"] = str(exc)
        result["route"] = _route_for_mode(mode)
        return result


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _context_summary(job_dir: Path) -> dict[str, Any]:
    result = _read_json(job_dir / "result.json", {})
    validation = _read_json(job_dir / "result_validation.json", {})
    state = _read_json(job_dir / "job_state.json", {})
    evaluation = result.get("evaluation_summary") or _read_json(job_dir / "evaluation_summary.json", [])
    figures = _read_json(job_dir / "figures_manifest.json", [])
    template_audit = _read_json(job_dir / "template_report_audit.json", {})
    if isinstance(figures, dict):
        figures = figures.get("figures") or figures.get("items") or []
    if not isinstance(evaluation, list):
        evaluation = []
    if not isinstance(figures, list):
        figures = []
    unknown_loads = []
    for key in ("foundation_loads", "bolt_force_results", "weld_force_results"):
        for row in result.get(key, []) or []:
            if str(row.get("node") or row.get("keypoint") or "").upper() == "UNKNOWN":
                unknown_loads.append({"scope": key, "load_case": row.get("load_case"), "source_file": row.get("source_file")})
    return {
        "job_id": job_dir.name,
        "job_state": state.get("status") or state.get("state"),
        "result_status": result.get("result_status"),
        "validation_status": validation.get("status"),
        "evaluation_count": len(evaluation),
        "failed_evaluations": [item for item in evaluation if item.get("pass_fail") == "不满足"],
        "pending_formula_items": [item for item in evaluation if item.get("pass_fail") == "待确认" or item.get("formula_status") == "unconfirmed_todo"],
        "figure_count": len(figures),
        "template_report_status": template_audit.get("status") if isinstance(template_audit, dict) else None,
        "template_report_warnings": [
            item for item in (template_audit.get("replacements") or []) if isinstance(item, dict) and item.get("status") == "warning"
        ] if isinstance(template_audit, dict) else [],
        "unknown_loads": unknown_loads,
        "command_files": {
            "model": (job_dir / "generated_model.mac").exists(),
            "solve": (job_dir / "generated_solve.mac").exists(),
            "post": (job_dir / "generated_post.mac").exists(),
        },
        "audit_files": {
            "template_report_audit": (job_dir / "template_report_audit.json").exists(),
            "ansys_run_audit": (job_dir / "ansys_run_audit.json").exists(),
        },
    }


def _rule_based_response(context: dict[str, Any], question: str | None) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    job_summary = context.get("job_summary") if isinstance(context.get("job_summary"), dict) else context
    run_context = context.get("run_context") if isinstance(context.get("run_context"), dict) else {}
    mode = str(context.get("mode") or "")
    attachments = context.get("attachments") if isinstance(context.get("attachments"), list) else []
    if attachments:
        findings.append(
            {
                "severity": "建议",
                "issue": "已读取上传文件摘要",
                "suggested_fix": "本地模型可解释 uploads/ 下的日志、命令流片段和审计文件；原始 source_materials 不会被直接发送到模型。",
            }
        )
    if mode in {"developer_assistant", "safe_fix"}:
        findings.append(
            {
                "severity": "风险",
                "issue": "修复边界已启用",
                "suggested_fix": "部署、路径、网页、配置类问题可自动修复；APDL/PIP、材料许用值、评定公式和正式结论必须先生成补丁建议与回归验证，不能直接改成通过。",
            }
        )
    run_status = run_context.get("status")
    if isinstance(run_status, dict):
        run_status = run_status.get("status")
    if run_status in {"running", "queued"}:
        findings.append({"severity": "建议", "issue": "当前存在运行中的计算任务", "suggested_fix": "持续观察 progress/current_stage；若长时间无日志增长，再检查 ANSYS 进程、license、RST/OUT 更新时间和 run audit。"})
    if run_context.get("failed_jobs"):
        findings.append({"severity": "必改", "issue": "批量运行中存在失败 job", "suggested_fix": "逐个打开 failure_reason、ansys_run_audit.json、result_validation.json，优先处理全零、UNKNOWN 节点、缺图和模板注入失败。"})
    if job_summary.get("validation_status") == "fail":
        findings.append({"severity": "必改", "issue": "result_validation.json 存在 fail", "suggested_fix": "先修复结果提取缺源、全零或 UNKNOWN 节点问题，再允许评定/报告注入。"})
    if job_summary.get("failed_evaluations"):
        findings.append({"severity": "必改", "issue": "存在不满足的评定项", "suggested_fix": "检查方钢截面、材料策略、载荷/约束/谱选择和评定公式来源，不能在报告中写满足。"})
    if job_summary.get("unknown_loads"):
        findings.append({"severity": "必改", "issue": "载荷提取存在 UNKNOWN 节点", "suggested_fix": "回到 generated_post.mac/PIP 输出集合，确认节点/组件选择和对应报告表章节映射。"})
    if job_summary.get("pending_formula_items"):
        findings.append({"severity": "风险", "issue": "存在未确认公式项", "suggested_fix": "调用 Excel 权威评定或补充规范 source_ref，未确认前不得最终通过。"})
    if job_summary.get("figure_count", 0) == 0 and context.get("mode") == "engineering_qc":
        findings.append({"severity": "格式", "issue": "没有可注入报告的 ANSYS 图片", "suggested_fix": "先执行图片导出或真实输出导入，保证模态图和应力云图文件存在。"})
    if job_summary.get("template_report_warnings"):
        findings.append({"severity": "风险", "issue": "模板报告注入存在 warning", "suggested_fix": "打开 template_report_audit.json，逐项补齐缺失的焊缝/螺栓评定源或图片源。"})
    if not findings:
        findings.append({"severity": "建议", "issue": "未发现阻断项", "suggested_fix": "可继续做人工复核：检查命令流、谱表、表格值和图片是否与工程范围一致。"})
    return {
        "status": "fallback",
        "provider": "rule_based",
        "answer": "单位内网模型未启用，已按固定工程审核规则给出建议。",
        "question": question,
        "mode": context.get("mode"),
        "findings": findings,
    }


def _call_openai_compatible(
    config: dict[str, Any],
    context: dict[str, Any],
    question: str | None,
    *,
    fast: bool = False,
    max_tokens: int = 768,
) -> dict[str, Any]:
    api_key_env = str(config.get("api_key_env") or "")
    api_key = os.environ.get(api_key_env, "") if api_key_env else ""
    url = config["base_url"].rstrip("/") + "/chat/completions"
    user_content = {
        "question": question or "请审核当前 job 的建模、结果提取、评定和报告注入风险。",
        "context": context,
    }
    payload = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": FAST_CHAT_SYSTEM_KNOWLEDGE if fast else SYSTEM_KNOWLEDGE},
            {"role": "user", "content": json.dumps(user_content, ensure_ascii=False)},
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=config["timeout_seconds"]) as response:
        body = json.loads(response.read().decode("utf-8"))
    content = _repair_mojibake_text(body.get("choices", [{}])[0].get("message", {}).get("content", ""))
    return {
        "status": "pass",
        "provider": "openai_compatible",
        "model": config["model"],
        "mode": context.get("mode"),
        "answer": content,
        "raw_usage": body.get("usage"),
        "findings": [],
    }


def audit_job_with_model(job_dir: Path | str, *, question: str | None = None, config_path: Path | str = DEFAULT_CONFIG) -> dict[str, Any]:
    job_dir = Path(job_dir)
    context = _context_summary(job_dir)
    config = _load_config(config_path)
    if not config["enabled"]:
        result = _rule_based_response(context, question)
    else:
        try:
            result = _call_openai_compatible(config, context, question)
        except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            result = _rule_based_response(context, question)
            result["model_error"] = str(exc)
    result["context_summary"] = context
    result["model_switch_policy"] = "Use any OpenAI-compatible local model endpoint by editing config/ai.local.toml; deterministic ANSYS/Excel/spec results remain authoritative."
    (job_dir / "ai_audit_comments.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _all_zero_load_rows(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> bool:
    if not rows:
        return False
    saw_number = False
    for row in rows:
        values = row.get("values") if isinstance(row.get("values"), dict) else {}
        for field in fields:
            value = row.get(field, values.get(field))
            if isinstance(value, dict):
                value = value.get("value", value.get("normalized_value", value.get("raw_value")))
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            saw_number = True
            if abs(number) > 1e-9:
                return False
    return saw_number


def _postprocess_context(job_dir: Path, result: dict[str, Any] | None = None) -> dict[str, Any]:
    result = result or _read_json(job_dir / "result.json", {})
    validation = result.get("result_validation") or _read_json(job_dir / "result_validation.json", {})
    evaluation = result.get("evaluation_summary") or _read_json(job_dir / "evaluation_summary.json", [])
    figures = result.get("figures") or _read_json(job_dir / "figures_manifest.json", [])
    if isinstance(figures, dict):
        figures = figures.get("figures") or figures.get("items") or []
    if not isinstance(figures, list):
        figures = []
    if not isinstance(evaluation, list):
        evaluation = []
    source_files = {
        "modal": bool(result.get("modal_results")),
        "beam_stress": bool(result.get("beam_stress_results")),
        "weld_force": bool(result.get("weld_force_results")),
        "bolt_force": bool(result.get("bolt_force_results")),
        "foundation_load": bool(result.get("foundation_loads")),
    }
    load_rows = []
    for key in ("foundation_loads", "bolt_force_results", "weld_force_results"):
        rows = result.get(key) or []
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    load_rows.append({"scope": key, **row})
    unknown_nodes = [
        {
            "scope": row.get("scope"),
            "load_case": row.get("load_case"),
            "node": row.get("node") or row.get("keypoint") or row.get("name"),
            "source_file": row.get("source_file"),
        }
        for row in load_rows
        if str(row.get("node") or row.get("keypoint") or "").upper() == "UNKNOWN"
    ]
    max_ratio = 0.0
    pending = 0
    failed = 0
    for item in evaluation:
        try:
            max_ratio = max(max_ratio, float(item.get("ratio") or 0.0))
        except (TypeError, ValueError):
            pass
        if item.get("pass_fail") == "不满足":
            failed += 1
        if item.get("pass_fail") == "待确认" or item.get("formula_status") == "unconfirmed_todo":
            pending += 1
    figure_types = sorted({str(item.get("figure_type") or item.get("appendix") or "unknown") for item in figures if isinstance(item, dict)})
    return {
        "job_id": job_dir.name,
        "result_status": result.get("result_status"),
        "validation_status": validation.get("status"),
        "validation_fail_checks": [
            item for item in validation.get("checks", []) if isinstance(item, dict) and item.get("status") == "fail"
        ] if isinstance(validation, dict) else [],
        "source_files": source_files,
        "figure_count": len(figures),
        "figure_types": figure_types,
        "unknown_nodes": unknown_nodes,
        "foundation_all_zero": _all_zero_load_rows(result.get("foundation_loads") or [], ("fx", "fy", "fz", "mx", "my", "mz")),
        "bolt_all_zero": _all_zero_load_rows(result.get("bolt_force_results") or [], ("fx", "fy", "fz", "mx", "my", "mz", "tension_mpa", "shear_mpa")),
        "weld_all_zero": _all_zero_load_rows(result.get("weld_force_results") or [], ("force_n", "fx", "fy", "fz", "mx", "my", "mz", "stress_mpa")),
        "evaluation_count": len(evaluation),
        "max_ratio": max_ratio,
        "failed_evaluation_count": failed,
        "pending_formula_count": pending,
        "authoritative_boundary": PROJECT_KNOWLEDGE_PACK["authoritative_chain"],
    }


def _rule_based_postprocess_qc(context: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    if context.get("validation_status") == "fail":
        checks = ", ".join(str(item.get("check_id")) for item in context.get("validation_fail_checks", [])[:8])
        findings.append(
            {
                "severity": "必改",
                "location": "result_validation.json",
                "issue": "结果有效性门禁失败",
                "evidence": checks or "validation_status=fail",
                "suggested_fix": "先修复 LIS/OUP/BMP 提取源、节点集合、全零输出或图片缺失，再允许正式结论。",
                "source_ref": "result_validation.json",
            }
        )
    if context.get("unknown_nodes"):
        findings.append(
            {
                "severity": "必改",
                "location": "load extraction",
                "issue": "载荷提取存在 UNKNOWN 节点或关键点",
                "evidence": json.dumps(context.get("unknown_nodes")[:5], ensure_ascii=False),
                "suggested_fix": "回查 generated_post.mac 的组件/节点集合和 PIP 输出表，不能用 UNKNOWN 节点进入报告。",
                "source_ref": "generated_post.mac / LIS",
            }
        )
    for key, label in (("foundation_all_zero", "支架基础载荷"), ("bolt_all_zero", "支架连接螺栓载荷"), ("weld_all_zero", "托臂根部焊缝载荷")):
        if context.get(key):
            findings.append(
                {
                    "severity": "必改",
                    "location": label,
                    "issue": f"{label}解析结果全零",
                    "evidence": f"{key}=true",
                    "suggested_fix": "全零通常说明结果集合、工况选择或 LIS 字段映射有问题，必须回到后处理命令和真实 LIS 对齐。",
                    "source_ref": "result.json",
                }
            )
    if context.get("failed_evaluation_count", 0) > 0:
        findings.append(
            {
                "severity": "必改",
                "location": "evaluation_summary.json",
                "issue": "存在不满足评定项",
                "evidence": f"failed_evaluation_count={context.get('failed_evaluation_count')}",
                "suggested_fix": "检查截面、材料许用值、载荷工况和公式 source_ref；不得把结果写为满足。",
                "source_ref": "evaluation_summary.json",
            }
        )
    if context.get("pending_formula_count", 0) > 0:
        findings.append(
            {
                "severity": "风险",
                "location": "evaluation_summary.json",
                "issue": "存在未确认公式或 Excel 权威评定未完成项",
                "evidence": f"pending_formula_count={context.get('pending_formula_count')}",
                "suggested_fix": "调用 Excel 权威评定副本或补充规范 source_ref，未确认前 AI 不得建议最终通过。",
                "source_ref": "evaluation_summary.json",
            }
        )
    if context.get("figure_count", 0) == 0:
        findings.append(
            {
                "severity": "格式",
                "location": "figures_manifest.json",
                "issue": "未收集到 ANSYS 图片",
                "evidence": "figure_count=0",
                "suggested_fix": "运行 ANSYS 图片导出或导入真实 BMP/PNG，报告附录不能空白。",
                "source_ref": "figures_manifest.json",
            }
        )
    if not findings:
        findings.append(
            {
                "severity": "建议",
                "location": "postprocess",
                "issue": "未发现后处理阻断项",
                "evidence": f"max_ratio={context.get('max_ratio')}",
                "suggested_fix": "仍需人工抽查命令流集合、谱选择、图片章节和报告模板注入。",
                "source_ref": "result.json",
            }
        )
    deterministic_status = "fail" if any(item["severity"] == "必改" for item in findings) else "warning" if any(item["severity"] in {"风险", "格式"} for item in findings) else "pass"
    return {
        "status": deterministic_status,
        "provider": "rule_based",
        "answer": "已按电缆桥架后处理质控规则审核。AI/规则只给疑点和建议，不替代 ANSYS、Excel 或规范公式。",
        "findings": findings,
    }


def audit_postprocess_with_model(
    job_dir: Path | str,
    *,
    result: dict[str, Any] | None = None,
    config_path: Path | str = DEFAULT_CONFIG,
) -> dict[str, Any]:
    job_dir = Path(job_dir)
    context = _postprocess_context(job_dir, result)
    config = _load_config(config_path)
    rule_result = _rule_based_postprocess_qc(context)
    payload = {
        **rule_result,
        "mode": "postprocess_qc",
        "context_summary": context,
        "deterministic_status": rule_result["status"],
        "authority_policy": "The model may explain or add review suggestions, but it cannot override result_validation, Excel authoritative evaluation, or confirmed formula source_ref.",
    }
    if config["enabled"]:
        try:
            model_result = _call_openai_compatible(
                config,
                {
                    "mode": "postprocess_qc",
                    "postprocess_context": context,
                    "rule_findings": rule_result["findings"],
                    "project_knowledge_pack": PROJECT_KNOWLEDGE_PACK,
                },
                "请审核当前电缆桥架后处理结果是否符合工程逻辑、规范边界和报告章节映射。请只输出疑点、证据和建议，不要替代确定性结论。",
                fast=True,
                max_tokens=768,
            )
            payload["model_provider"] = model_result.get("provider")
            payload["model"] = model_result.get("model")
            payload["model_answer"] = model_result.get("answer")
            payload["model_status"] = model_result.get("status")
        except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            payload["model_status"] = "unavailable"
            payload["model_error"] = str(exc)
    else:
        payload["model_status"] = "disabled"
    (job_dir / "postprocess_ai_qc.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
