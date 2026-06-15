import json

from core.apdl.keypoint_guard import guard_undefined_keypoint_coordinate_refs


def test_guard_wraps_line_mesh_blocks_and_is_idempotent(tmp_path):
    model = tmp_path / "generated_model.mac"
    model.write_text(
        "\n".join(
            [
                "K,1,0,0,0",
                "K,2,1,0,0",
                "L,1,2",
                "ALLSEL",
                "LSEL,S,LOC,X,9",
                "LATT,1,,1,,,,1",
                "LESIZE,ALL,0.05,,,,,,,1",
                "LMESH,ALL",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    audit = guard_undefined_keypoint_coordinate_refs(model)
    guarded = model.read_text(encoding="utf-8")

    assert audit["status"] == "applied"
    assert audit["empty_line_mesh_guard"]["block_count"] == 1
    assert "*GET,CTAILCNT,LINE,0,COUNT" in guarded
    assert "*IF,CTAILCNT,GT,0,THEN" in guarded
    assert "LATT,1,,1,,,,1" in guarded
    assert "selected line count is zero" in guarded

    second_audit = guard_undefined_keypoint_coordinate_refs(model)
    guarded_again = model.read_text(encoding="utf-8")

    assert second_audit["empty_line_mesh_guard"]["block_count"] == 0
    assert guarded_again.count("*GET,CTAILCNT,LINE,0,COUNT") == 1


def test_guard_keeps_undefined_keypoint_audit_with_mesh_guard(tmp_path):
    model = tmp_path / "generated_model.mac"
    model.write_text(
        "\n".join(
            [
                "K,1,0,0,0",
                "K,2,1,0,0",
                "L,1,2",
                "LSEL,S,LOC,Z,KZ(99)",
                "LATT,1,,1,,,,1",
                "LESIZE,ALL,0.05,,,,,,,1",
                "LMESH,ALL",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    audit = guard_undefined_keypoint_coordinate_refs(model)
    audit_file = json.loads((tmp_path / "model_keypoint_guard_audit.json").read_text(encoding="utf-8"))
    guarded = model.read_text(encoding="utf-8")

    assert audit["disabled_line_count"] == 1
    assert audit_file["disabled_lines"][0]["missing_keypoints"] == [99]
    assert "disabled undefined keypoint coordinate reference" in guarded
    assert audit["empty_line_mesh_guard"]["block_count"] == 1
