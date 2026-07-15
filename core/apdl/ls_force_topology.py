from __future__ import annotations

import re
from typing import Any


def _has_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE) is not None for pattern in patterns)


def audit_standard_ls_force_topology(text: str, *, has_back_side: bool) -> dict[str, Any]:
    """Audit the model interface expected by the shared LS-FORCE post block.

    The standard S2 post stream extracts tray-arm connection loads from the
    suffix-9 keypoint family (509/1509 after layer offsets). Physical bolt lines
    such as 506-507-508 are not enough: they can be valid model geometry while
    still leaving the published LS-FORCE selector pointed at missing or unrelated
    keypoints.
    """

    front_keypoint = _has_any(
        text,
        (
            r"^\s*K\s*,\s*509\s*(?:\+\s*KPOFF)?\s*\+\s*10\s*\*\s*I\b",
            r"^\s*K\s*,\s*500\s*\+\s*10\s*\*\s*cengshu1\s*\+\s*9\b",
        ),
    )
    front_connector = _has_any(
        text,
        (
            r"^\s*L\s*,\s*(?:502|503)\s*(?:\+\s*KPOFF)?\s*\+\s*10\s*\*\s*I\b.*,\s*509\s*(?:\+\s*KPOFF)?\s*\+\s*10\s*\*\s*I\b",
            r"^\s*L\s*,\s*500\s*\+\s*10\s*\*\s*cengshu1\s*\+\s*[23]\b.*,\s*500\s*\+\s*10\s*\*\s*cengshu1\s*\+\s*9\b",
        ),
    )
    back_keypoint = (not has_back_side) or _has_any(
        text,
        (
            r"^\s*K\s*,\s*1509\s*(?:\+\s*KPOFF)?\s*\+\s*10\s*\*\s*I\b",
            r"^\s*K\s*,\s*KPBKBASE\s*\+\s*9\s*\+\s*KPOFF\s*\+\s*10\s*\*\s*I\b",
        ),
    )
    back_connector = (not has_back_side) or _has_any(
        text,
        (
            r"^\s*L\s*,\s*(?:1502|1503)\s*(?:\+\s*KPOFF)?\s*\+\s*10\s*\*\s*I\b.*,\s*1509\s*(?:\+\s*KPOFF)?\s*\+\s*10\s*\*\s*I\b",
            r"^\s*L\s*,\s*KPBKBASE\s*\+\s*[23]\s*\+\s*KPOFF\s*\+\s*10\s*\*\s*I\b.*,\s*KPBKBASE\s*\+\s*9\s*\+\s*KPOFF\s*\+\s*10\s*\*\s*I\b",
        ),
    )
    legacy_physical_only = _has_any(
        text,
        (
            r"^\s*L\s*,\s*506\s*\+\s*10\s*\*\s*I\b.*,\s*507\s*\+\s*10\s*\*\s*I\b",
            r"^\s*L\s*,\s*500\s*\+\s*10\s*\*\s*cengshu1\s*\+\s*6\b.*,\s*500\s*\+\s*10\s*\*\s*cengshu1\s*\+\s*7\b",
        ),
    )
    checks = {
        "front_ls_force_keypoint_509": front_keypoint,
        "front_ls_force_connector_to_509": front_connector,
        "back_ls_force_keypoint_1509": back_keypoint,
        "back_ls_force_connector_to_1509": back_connector,
        "legacy_physical_bolt_506_508_present": legacy_physical_only,
    }
    required = [
        "front_ls_force_keypoint_509",
        "front_ls_force_connector_to_509",
        "back_ls_force_keypoint_1509",
        "back_ls_force_connector_to_1509",
    ]
    missing = [name for name in required if not checks.get(name)]
    return {
        "status": "pass" if not missing else "fail",
        "checks": checks,
        "missing": missing,
        "has_back_side": has_back_side,
        "source_ref": "generated_model.mac / standard S2 LS-FORCE KYALS suffix-9 topology",
        "policy": (
            "The shared LS-FORCE post block extracts from the suffix-9 interface "
            "(509/1509 after layer offsets). A model with only 506/507/508 physical "
            "bolt lines must not be paired with that post selector."
        ),
    }
