from __future__ import annotations

import pytest

from core.results.lis_parser import LisParseError, parse_foundation_load_lis


def test_foundation_parser_preserves_explicit_zero_components(tmp_path):
    path = tmp_path / "JCZH.LIS"
    path.write_text(
        "\n".join(
            [
                "    LSCASE         FX(m)       FY(m)       FZ(m)       MX(Nm)       MY(Nm)       MZ(Nm)",
                "    DW             104.1         0.0      4211.7         0.0      1128.7         0.0",
            ]
        ),
        encoding="utf-8",
    )

    rows = parse_foundation_load_lis(path)

    assert rows[0]["fy"]["value"] == 0.0
    assert rows[0]["fy"]["raw_value"] == "0.0"
    assert rows[0]["mz"]["value"] == 0.0
    assert rows[0]["mz"]["raw_value"] == "0.0"


def test_foundation_parser_rejects_missing_components_instead_of_defaulting_to_zero(tmp_path):
    path = tmp_path / "JCZH.LIS"
    path.write_text(
        "\n".join(
            [
                "    LSCASE         FX(m)       FY(m)       FZ(m)       MX(Nm)       MY(Nm)       MZ(Nm)",
                "    DW             104.1         0.0      4211.7         0.0      1128.7",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LisParseError, match="missing required field mz"):
        parse_foundation_load_lis(path)
