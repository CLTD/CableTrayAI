from pathlib import Path

from core.report.template_injector import choose_report_template


def test_choose_report_template_returns_existing_static_template():
    selection = choose_report_template({"metadata": {"analysis_method": "static"}})

    assert selection["mode"] == "steel_platform"
    assert Path(selection["template"]).exists()


def test_choose_report_template_returns_existing_response_spectrum_template():
    selection = choose_report_template({"metadata": {"analysis_method": "response_spectrum"}})

    assert selection["mode"] == "non_steel_platform"
    assert Path(selection["template"]).exists()
