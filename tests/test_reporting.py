from im_guard_ml.reporting import build_delivery_summary, build_offline_eval_report, build_readiness_check


def test_build_offline_eval_report_contains_metrics_and_versions():
    rows = [
        {
            "label": {
                "risk_level": "low_risk",
                "topic": "无主题",
                "final_judgment": "not_exist_violation",
                "handling_suggestion": "ignore",
            },
            "prediction": {
                "risk_level": "low_risk",
                "topic": "无主题",
                "final_judgment": "not_exist_violation",
                "handling_suggestion": "ignore",
                "model_version": "m1",
                "prompt_version": "p1",
            },
        }
    ]

    report = build_offline_eval_report(rows)

    assert "二分类指标" in report
    assert "risk_macro_f1" in report
    assert "`model_version`：`m1`" in report


def test_build_delivery_summary_reports_existing_and_missing_items(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "PUBLIC_DATASET_XGUARD.md").write_text("x", encoding="utf-8")

    report = build_delivery_summary(tmp_path)

    assert "企业级生产化交付摘要" in report
    assert "`docs/PUBLIC_DATASET_XGUARD.md` | ok" in report
    assert "missing" in report


def test_build_readiness_check_fails_when_required_artifacts_missing(tmp_path):
    (tmp_path / ".gitignore").write_text("data/external/\ndata/train/\noutputs/\n", encoding="utf-8")

    report = build_readiness_check(tmp_path)

    assert report["status"] == "fail"
    assert report["summary"]["fail"] > 0
    assert any(check["category"] == "required_artifact" for check in report["checks"])


def test_build_readiness_check_warns_when_only_local_data_missing(tmp_path):
    required_files = [
        "docs/PUBLIC_DATASET_XGUARD.md",
        "docs/ENTERPRISE_READINESS_REVIEW.md",
        "docs/TRAINING_AND_EVALUATION.md",
        "src/im_guard_ml/training_readiness.py",
        "tests/test_training_readiness.py",
        "docs/HUMAN_REVIEW_AND_ROLLOUT.md",
        "docs/SLO_AND_ALERTING.md",
        "docs/DEPLOYMENT_AND_OPERATIONS.md",
        "docs/API_USAGE.md",
        "docs/COMMANDS.md",
        "docs/POLICY_CHANGELOG.md",
        "docs/LOCAL_ENV_ROOT_CAUSE.md",
        "tests/test_docs_consistency.py",
        ".github/workflows/ci.yml",
        "src/im_guard_ml/api_contract.py",
        "src/im_guard_ml/preflight.py",
        "configs/model_registry.yaml",
        "src/im_guard_ml/model_registry.py",
        "src/im_guard_ml/rollout.py",
        "deploy/Dockerfile",
        "deploy/docker-compose.example.yml",
        "deploy/k8s/deployment.yaml",
        "tests/test_deployment_templates.py",
        "deploy/prometheus/im_guard_alerts.yaml",
        "scripts/download_xguard_dataset.py",
        "scripts/benchmark_api.py",
        "tests/test_benchmark_api.py",
    ]
    for rel in required_files:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("data/external/\ndata/train/\noutputs/\n", encoding="utf-8")

    report = build_readiness_check(tmp_path)

    assert report["status"] == "warn"
    assert report["summary"]["fail"] == 0
    assert report["summary"]["warn"] == 5
    assert report["remaining_external_requirements"]
