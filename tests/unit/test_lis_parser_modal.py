from __future__ import annotations

from core.results.lis_parser import parse_modal_oup


def test_parse_modal_oup_participation_factor_frequency_table(tmp_path):
    path = tmp_path / "Mode.oup"
    path.write_text(
        "\n".join(
            [
                "          ***** PARTICIPATION FACTOR CALCULATION *****  X  DIRECTION",
                "  MODE   FREQUENCY       PERIOD      PARTIC.FACTOR     RATIO    EFFECTIVE MASS",
                "     1    0.894692        1.1177        24.258        1.000000     588.464",
                "     2    0.895884        1.1162        23.842        0.982829     568.429",
                "     3    0.896053        1.1160        14.221        0.586218     202.227",
                "     4    0.896068        1.1160        16.858        0.694918     284.176",
                "          ***** PARTICIPATION FACTOR CALCULATION *****  Y  DIRECTION",
                "  MODE   FREQUENCY       PERIOD      PARTIC.FACTOR     RATIO    EFFECTIVE MASS",
                "     1    0.894692        1.1177        0.0000        0.000000     0.00000",
            ]
        ),
        encoding="utf-8",
    )

    rows = parse_modal_oup(path)

    assert [row["source_mode"] for row in rows] == [1, 2, 3, 4]
    assert rows[0]["frequency_hz"] == 0.894692
    assert rows[0]["period_s"] == 1.1177
    assert rows[0]["modal_source_format"] in {"participation_factor_frequency_table", "tabular_frequency_record"}
    assert rows[0]["modal_reporting_low_frequency_fallback"] is True


def test_parse_modal_oup_keeps_above_1hz_rows_as_reportable(tmp_path):
    path = tmp_path / "Mode.oup"
    path.write_text(
        "\n".join(
            [
                "  MODE   FREQUENCY       PERIOD      PARTIC.FACTOR     RATIO    EFFECTIVE MASS",
                "     1    0.500000        2.0000        1.0           1.0          1.0",
                "     2    2.500000        0.4000        1.0           1.0          1.0",
                "     3    3.500000        0.2857        1.0           1.0          1.0",
            ]
        ),
        encoding="utf-8",
    )

    rows = parse_modal_oup(path)

    assert [row["source_mode"] for row in rows] == [2, 3]
    assert [row["mode"] for row in rows] == [1, 2]
    assert rows[0]["modal_reporting_low_frequency_fallback"] is False
