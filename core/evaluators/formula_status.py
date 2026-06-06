from __future__ import annotations


TODO_FORMULA_SOURCE_REQUIRED = "TODO_FORMULA_SOURCE_REQUIRED"


def formula_status(source_ref: str | None) -> str:
    if source_ref == TODO_FORMULA_SOURCE_REQUIRED:
        return "unconfirmed_todo"
    if source_ref:
        return "confirmed"
    return "not_applicable"
