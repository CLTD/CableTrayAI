from core.report.template_mapper import validate_report_mapping


def test_report_mapping_requires_result_fields_and_figures():
    result = {
        "evaluation_summary": [],
        "foundation_loads": [],
        "bolt_force_results": [],
        "modal_results": [],
    }
    input_payload = {
        "materials": [],
        "support": {},
        "load_cases": [],
    }
    figures = [
        {"figure_type": "modal", "target_file": "MOTAI-1.PNG"},
        {"figure_type": "stress", "target_file": "B1SDIR1.PNG"},
    ]

    checks = validate_report_mapping(result, input_payload, figures)

    assert checks
    assert {check["status"] for check in checks} == {"pass"}


def test_report_mapping_fails_when_stress_figures_are_missing():
    result = {
        "evaluation_summary": [],
        "foundation_loads": [],
        "bolt_force_results": [],
        "modal_results": [],
    }
    input_payload = {
        "materials": [],
        "support": {},
        "load_cases": [],
    }
    checks = validate_report_mapping(result, input_payload, [{"figure_type": "modal"}])

    assert any(check["figures_path"] == "figures[figure_type=stress]" and check["status"] == "fail" for check in checks)
