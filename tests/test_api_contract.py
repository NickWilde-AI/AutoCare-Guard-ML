import json

from im_guard_ml.api_contract import REQUIRED_ENDPOINTS, build_openapi_contract, validate_openapi_contract
from im_guard_ml.cli import main


def test_build_openapi_contract_contains_required_endpoints():
    schema = build_openapi_contract()

    assert schema["x-im-guard-contract-status"]["status"] == "pass"
    assert set(schema["x-im-guard-required-endpoints"]) == REQUIRED_ENDPOINTS
    assert "/judge" in schema["paths"]
    assert "post" in schema["paths"]["/judge"]


def test_validate_openapi_contract_fails_when_required_endpoint_missing():
    schema = build_openapi_contract()
    del schema["paths"]["/judge"]

    result = validate_openapi_contract(schema)

    assert result["status"] == "fail"
    assert "POST /judge" in result["missing"]


def test_cli_api_contract_writes_contract_file(tmp_path):
    out = tmp_path / "openapi.json"

    code = main(["api-contract", "--out", str(out), "--fail-on-missing"])

    assert code == 0
    body = json.loads(out.read_text(encoding="utf-8"))
    assert body["x-im-guard-contract-status"]["status"] == "pass"
