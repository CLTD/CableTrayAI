from __future__ import annotations

import ast
import itertools
import json
import re
from pathlib import Path
from typing import Any


_ASSIGN_RE = re.compile(r"^\s*([A-Za-z]\w*)\s*=\s*([^!]+)")
_DO_RE = re.compile(r"^\s*\*DO\s*,\s*([A-Za-z]\w*)\s*,\s*([^,]+)\s*,\s*([^,]+)(?:,\s*([^,!]+))?", re.IGNORECASE)
_ENDDO_RE = re.compile(r"^\s*\*ENDDO\b", re.IGNORECASE)
_KEYPOINT_RE = re.compile(r"^\s*K\s*,\s*([^,]+)", re.IGNORECASE)
_COORD_REF_RE = re.compile(r"\bK[XYZ]\s*\(\s*(\d+)\s*\)", re.IGNORECASE)


class _ExpressionError(ValueError):
    pass


def _strip_comment(line: str) -> str:
    return line.split("!", 1)[0].strip()


def _safe_eval(expression: str, variables: dict[str, float]) -> float:
    node = ast.parse(expression.strip(), mode="eval")

    def visit(item: ast.AST) -> float:
        if isinstance(item, ast.Expression):
            return visit(item.body)
        if isinstance(item, ast.Constant) and isinstance(item.value, (int, float)):
            return float(item.value)
        if isinstance(item, ast.Name):
            key = item.id
            if key not in variables:
                raise _ExpressionError(f"unknown variable: {key}")
            return float(variables[key])
        if isinstance(item, ast.UnaryOp) and isinstance(item.op, (ast.UAdd, ast.USub)):
            value = visit(item.operand)
            return value if isinstance(item.op, ast.UAdd) else -value
        if isinstance(item, ast.BinOp):
            left = visit(item.left)
            right = visit(item.right)
            if isinstance(item.op, ast.Add):
                return left + right
            if isinstance(item.op, ast.Sub):
                return left - right
            if isinstance(item.op, ast.Mult):
                return left * right
            if isinstance(item.op, ast.Div):
                return left / right
            if isinstance(item.op, ast.Pow):
                return left**right
        raise _ExpressionError(f"unsupported expression: {expression}")

    return visit(node)


def _int_if_close(value: float) -> int | None:
    rounded = int(round(value))
    return rounded if abs(value - rounded) < 1e-9 else None


def _range_from_do(match: re.Match[str], variables: dict[str, float]) -> tuple[str, list[int]] | None:
    name = match.group(1)
    try:
        start = _int_if_close(_safe_eval(match.group(2), variables))
        end = _int_if_close(_safe_eval(match.group(3), variables))
        step_text = match.group(4) or "1"
        step = _int_if_close(_safe_eval(step_text, variables))
    except (_ExpressionError, SyntaxError):
        return None
    if start is None or end is None or step is None or step == 0:
        return None
    stop = end + (1 if step > 0 else -1)
    return name, list(range(start, stop, step))


def _active_loop_envs(loops: list[tuple[str, list[int]]]) -> list[dict[str, float]]:
    if not loops:
        return [{}]
    names = [name for name, _ in loops]
    ranges = [values for _, values in loops]
    return [dict(zip(names, values, strict=True)) for values in itertools.product(*ranges)]


def collect_defined_keypoint_ids(lines: list[str]) -> set[int]:
    variables: dict[str, float] = {}
    loops: list[tuple[str, list[int]]] = []
    keypoints: set[int] = set()

    for line in lines:
        code = _strip_comment(line)
        if not code:
            continue
        assignment = _ASSIGN_RE.match(code)
        if assignment and not code.upper().startswith("*"):
            try:
                variables[assignment.group(1)] = _safe_eval(assignment.group(2), variables)
            except (_ExpressionError, SyntaxError):
                pass
            continue
        do_match = _DO_RE.match(code)
        if do_match:
            loop = _range_from_do(do_match, variables)
            if loop:
                loops.append(loop)
            else:
                loops.append((do_match.group(1), []))
            continue
        if _ENDDO_RE.match(code):
            if loops:
                loops.pop()
            continue
        keypoint = _KEYPOINT_RE.match(code)
        if not keypoint:
            continue
        expression = keypoint.group(1)
        for loop_env in _active_loop_envs(loops):
            env = {**variables, **loop_env}
            try:
                value = _int_if_close(_safe_eval(expression, env))
            except (_ExpressionError, SyntaxError):
                value = None
            if value is not None:
                keypoints.add(value)
    return keypoints


def guard_undefined_keypoint_coordinate_refs(model_path: Path | str) -> dict[str, Any]:
    model_path = Path(model_path)
    original_text = model_path.read_text(encoding="utf-8", errors="replace")
    lines = original_text.splitlines()
    defined_keypoints = collect_defined_keypoint_ids(lines)
    guarded_lines: list[str] = []
    disabled: list[dict[str, Any]] = []

    for line_number, line in enumerate(lines, start=1):
        if _strip_comment(line).startswith("!"):
            guarded_lines.append(line)
            continue
        refs = [int(match.group(1)) for match in _COORD_REF_RE.finditer(_strip_comment(line))]
        missing = [ref for ref in refs if ref not in defined_keypoints]
        if missing:
            disabled.append(
                {
                    "line": line_number,
                    "missing_keypoints": missing,
                    "original": line,
                    "reason": "The generated APDL references keypoint coordinates that are not defined by this case's keypoint loops.",
                }
            )
            guarded_lines.append(
                f"! CableTrayAI guard: disabled undefined keypoint coordinate reference(s) {','.join(str(item) for item in missing)}; original: {line}"
            )
        else:
            guarded_lines.append(line)

    if disabled:
        model_path.write_text("\n".join(guarded_lines) + "\n", encoding="utf-8", newline="\n")

    audit = {
        "status": "applied" if disabled else "pass",
        "model_file": model_path.name,
        "defined_keypoint_count": len(defined_keypoints),
        "disabled_line_count": len(disabled),
        "disabled_lines": disabled,
        "policy": "Generated command streams may be guarded when a source PIP references an undefined keypoint. The original source is not modified; every guarded line is preserved as an APDL comment for review.",
    }
    (model_path.parent / "model_keypoint_guard_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return audit
