import json

from core.results.result_assembler import _read_input_payload


def test_read_input_payload_accepts_utf8_bom(tmp_path):
    payload = {"project": {"project_code": "1818"}, "metadata": {"report_number": "18185NI-LXSJ4210"}}
    (tmp_path / "input.json").write_bytes(b"\xef\xbb\xbf" + json.dumps(payload).encode("utf-8"))

    assert _read_input_payload(tmp_path) == payload
