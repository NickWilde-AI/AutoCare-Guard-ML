import json

from autocare_guard_ml.cli import main
from autocare_guard_ml.preflight import build_production_preflight


SAFE_ENV = {
    "AUTOCARE_GUARD_API_TOKEN_HASHES": "a" * 64 + ":admin",
    "AUTOCARE_GUARD_CORS_ORIGINS": "https://audit.example.com",
    "AUTOCARE_GUARD_AUDIT_BACKEND": "sqlite",
    "AUTOCARE_GUARD_AUDIT_LOG_PATH": "outputs/api_audit_events.sqlite",
    "AUTOCARE_GUARD_MAX_REQUEST_BYTES": "262144",
    "AUTOCARE_GUARD_RATE_LIMIT_PER_MINUTE": "120",
}


def test_production_preflight_passes_for_restricted_safe_env():
    report = build_production_preflight(environ=SAFE_ENV)

    assert report["status"] == "pass"
    assert report["summary"]["fail"] == 0
    assert {item["name"] for item in report["checks"]} >= {
        "api_auth_enabled",
        "cors_not_wildcard",
        "audit_backend_supported",
        "rate_limit_enabled",
    }


def test_production_preflight_fails_for_unsafe_public_env():
    report = build_production_preflight(
        environ={
            "AUTOCARE_GUARD_CORS_ORIGINS": "*",
            "AUTOCARE_GUARD_AUDIT_BACKEND": "jsonl",
            "AUTOCARE_GUARD_AUDIT_LOG_PATH": "",
            "AUTOCARE_GUARD_MAX_REQUEST_BYTES": "0",
            "AUTOCARE_GUARD_RATE_LIMIT_PER_MINUTE": "0",
        }
    )

    assert report["status"] == "fail"
    failed = {item["name"] for item in report["checks"] if item["status"] == "fail"}
    assert "api_auth_enabled" in failed
    assert "cors_not_wildcard" in failed
    assert "rate_limit_enabled" in failed


def test_production_preflight_warns_for_placeholder_hash():
    env = {**SAFE_ENV, "AUTOCARE_GUARD_API_TOKEN_HASHES": "0" * 64 + ":admin"}

    report = build_production_preflight(environ=env)

    assert report["status"] == "warn"
    assert any(item["name"] == "api_token_hash_placeholder" for item in report["checks"])


def test_cli_production_preflight_writes_report(tmp_path):
    env_file = tmp_path / "prod.env"
    out = tmp_path / "preflight.json"
    env_file.write_text(
        "\n".join(f"{key}={value}" for key, value in SAFE_ENV.items()) + "\n",
        encoding="utf-8",
    )

    code = main(["production-preflight", "--env-file", str(env_file), "--out", str(out)])

    assert code == 0
    assert json.loads(out.read_text(encoding="utf-8"))["status"] == "pass"
