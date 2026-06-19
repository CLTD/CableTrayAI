from __future__ import annotations

from core.results.result_assembler import (
    _connection_nodes_to_bolt_rows,
    _select_connection_node_rows_for_bolt_envelope,
)


def _force_row(keypoint: int, *, fx: float, load_case: str = "UPSET") -> dict:
    return {
        "keypoint": keypoint,
        "load_case": load_case,
        "fx": fx,
        "fy": 0.0,
        "fz": 0.0,
        "mx": 0.0,
        "my": 0.0,
        "mz": 0.0,
        "source_file": "LS-FORCE-NODES.LIS",
    }


def test_connection_node_selection_does_not_bypass_zero_standard_suffix9_family() -> None:
    rows = [
        _force_row(519, fx=0.0),
        _force_row(619, fx=0.0),
        _force_row(516, fx=12.0),
    ]

    selected, audit = _select_connection_node_rows_for_bolt_envelope(rows)
    envelopes = _connection_nodes_to_bolt_rows(rows)

    assert audit["status"] == "selected_all_zero"
    assert audit["selected_suffixes"] == [9]
    assert {row["keypoint"] for row in selected} == {519, 619}
    assert envelopes[0]["fx"] == 0.0
    assert envelopes[0]["topology_selection"]["selected_all_zero"] is True


def test_connection_node_selection_blocks_suffix6_when_suffix9_family_is_absent() -> None:
    rows = [
        _force_row(516, fx=12.0),
        _force_row(616, fx=8.0),
    ]

    selected, audit = _select_connection_node_rows_for_bolt_envelope(rows)
    envelopes = _connection_nodes_to_bolt_rows(rows)

    assert selected == []
    assert envelopes == []
    assert audit["status"] == "missing_standard_suffix9"
    assert audit["selected_suffixes"] == [9]
    assert audit["diagnostic_keypoints"] == [516, 616]


def test_connection_node_selection_uses_suffix9_and_keeps_other_nodes_diagnostic() -> None:
    rows = [
        _force_row(519, fx=10.0),
        _force_row(619, fx=13.0),
        _force_row(516, fx=99.0),
    ]

    selected, audit = _select_connection_node_rows_for_bolt_envelope(rows)
    envelopes = _connection_nodes_to_bolt_rows(rows)

    assert audit["status"] == "pass"
    assert audit["policy"] == "standard_kyals_suffix_9"
    assert {row["keypoint"] for row in selected} == {519, 619}
    assert audit["diagnostic_keypoints"] == [516]
    assert envelopes[0]["fx"] == 13.0
