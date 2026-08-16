import json

import yaml

from im_guard_ml.cli import main
from im_guard_ml.model_registry import build_model_registry_report


def _registry():
    return {
        "current_stable": "stable-v1",
        "candidate": "candidate-v2",
        "promotion_guardrails": {
            "min_final_judgment_f1": 0.8,
            "min_handling_macro_f1": 0.7,
            "max_ban_account_fpr": 0.03,
            "max_parse_non_ok_rate": 0.02,
            "max_p95_latency_ms": 1200,
        },
        "models": [
            {
                "model_version": "stable-v1",
                "status": "stable",
                "prompt_version": "prompt-v1",
                "rubric_version": "rubric-v1",
                "feature_schema_version": "feature-schema-v1",
                "postprocess_version": "postprocess-v1",
                "train_data_version": "train-v1",
                "eval_data_version": "eval-v1",
                "approved_by": "owner",
                "approved_at": "2026-06-06T00:00:00Z",
                "rollback_to": "",
                "metrics": {
                    "final_judgment_f1": 0.9,
                    "handling_macro_f1": 0.8,
                    "ban_account_fpr": 0.01,
                    "parse_non_ok_rate": 0.0,
                    "p95_latency_ms": 600,
                },
            },
            {
                "model_version": "candidate-v2",
                "status": "candidate",
                "prompt_version": "prompt-v1",
                "rubric_version": "rubric-v1",
                "feature_schema_version": "feature-schema-v1",
                "postprocess_version": "postprocess-v1",
                "train_data_version": "train-v2",
                "eval_data_version": "eval-v1",
                "approved_by": "",
                "approved_at": "",
                "rollback_to": "stable-v1",
                "metrics": {
                    "final_judgment_f1": 0.91,
                    "handling_macro_f1": 0.82,
                    "ban_account_fpr": 0.01,
                    "parse_non_ok_rate": 0.0,
                    "p95_latency_ms": 700,
                },
            },
        ],
    }


def _write_registry(tmp_path, registry):
    path = tmp_path / "registry.yaml"
    path.write_text(yaml.safe_dump(registry, allow_unicode=True), encoding="utf-8")
    return path


def test_model_registry_report_passes_for_valid_registry(tmp_path):
    path = _write_registry(tmp_path, _registry())

    report = build_model_registry_report(path)

    assert report["status"] == "pass"
    assert report["summary"]["fail"] == 0
    assert report["current_stable"] == "stable-v1"


def test_model_registry_report_fails_when_stable_is_not_approved(tmp_path):
    registry = _registry()
    registry["models"][0]["approved_by"] = ""
    path = _write_registry(tmp_path, registry)

    report = build_model_registry_report(path)

    assert report["status"] == "fail"
    assert any(item["name"] == "stable_approved:stable-v1" for item in report["checks"])


def test_model_registry_report_fails_when_candidate_has_no_rollback(tmp_path):
    registry = _registry()
    registry["models"][1]["rollback_to"] = "missing-version"
    path = _write_registry(tmp_path, registry)

    report = build_model_registry_report(path)

    assert report["status"] == "fail"
    assert any(item["name"] == "candidate_rollback:candidate-v2" for item in report["checks"])


def test_model_registry_report_fails_when_metric_violates_guardrail(tmp_path):
    registry = _registry()
    registry["models"][1]["metrics"]["ban_account_fpr"] = 0.2
    path = _write_registry(tmp_path, registry)

    report = build_model_registry_report(path)

    assert report["status"] == "fail"
    assert any(item["name"] == "metric_guardrail:candidate-v2:ban_account_fpr" for item in report["checks"])


def test_model_registry_report_does_not_apply_promotion_guardrails_to_retired_models(tmp_path):
    registry = _registry()
    registry["models"].append(
        {
            "model_version": "retired-demo",
            "status": "retired",
            "prompt_version": "prompt-v1",
            "rubric_version": "rubric-v1",
            "feature_schema_version": "feature-schema-v1",
            "postprocess_version": "postprocess-v1",
            "train_data_version": "demo",
            "eval_data_version": "demo",
            "metrics": {"handling_macro_f1": 0.0, "ban_account_fpr": 1.0},
        }
    )
    path = _write_registry(tmp_path, registry)

    report = build_model_registry_report(path)

    assert report["status"] == "pass"
    assert not any(item["name"].startswith("metric_guardrail:retired-demo") for item in report["checks"])


def test_cli_model_registry_check_writes_report(tmp_path):
    registry = _write_registry(tmp_path, _registry())
    out = tmp_path / "registry-report.json"

    code = main(["model-registry-check", "--registry", str(registry), "--out", str(out)])

    assert code == 0
    assert json.loads(out.read_text(encoding="utf-8"))["status"] == "pass"
