from __future__ import annotations

from core.apdl.modal_policy import modal_mode_count_from_layer_count, modal_mode_count_from_payload, modal_policy_audit


def test_six_layer_new_intake_starts_at_bounded_safe_initial_count() -> None:
    assert modal_mode_count_from_layer_count(6) == 80


def test_payload_infers_layer_count_when_explicit_modal_count_absent() -> None:
    payload = {
        "support": {"layers_front": 4, "layers_back": 2},
        "metadata": {},
        "tray_layers": [{"width_mm": 500} for _ in range(6)],
    }

    assert modal_mode_count_from_payload(payload, source_text="MT=40") == 40
    audit = modal_policy_audit(payload, source_text="MT=40")
    assert audit["assigned_modal_mode_count"] == 40
    assert audit["assigned_modal_mode_count_source"] == "audited_source_safe_count"
    assert audit["inferred_layer_count"] == 6


def test_explicit_modal_count_still_wins_over_layer_heuristic() -> None:
    payload = {
        "support": {"layers_front": 4, "layers_back": 2},
        "metadata": {"modal_mode_count": 120},
    }

    assert modal_mode_count_from_payload(payload, source_text="MT=40") == 120
    audit = modal_policy_audit(payload, source_text="MT=40")
    assert audit["assigned_modal_mode_count"] == 120
    assert audit["assigned_modal_mode_count_source"] == "input_metadata"
