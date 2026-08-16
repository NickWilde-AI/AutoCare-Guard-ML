import json
from pathlib import Path

from im_guard_ml.cli import main
from im_guard_ml.dataio import read_jsonl, write_jsonl


def test_cli_pipeline_build_audit_predict_monitor(tmp_path, capsys):
    raw = tmp_path / "raw_xguard.jsonl"
    built = tmp_path / "built.jsonl"
    pred = tmp_path / "pred.jsonl"
    splits = tmp_path / "splits"
    write_jsonl(
        raw,
        [
            {"id": "1", "prompt": "正常问候", "response": "", "stage": "q", "label": "sec"},
            {"id": "2", "prompt": "加微信稳赚", "response": "", "stage": "q", "label": "ec"},
        ],
    )

    from im_guard_ml.build_dataset import main as build_main

    assert build_main(["--public-xguard", str(raw), "--out", str(built), "--split-out-dir", str(splits)]) == 0
    assert len(read_jsonl(built)) == 2
    assert Path(splits / "train.jsonl").exists()

    assert main(["audit-data", str(built)]) == 0
    audit = json.loads(capsys.readouterr().out)
    assert audit["dataset"]["quality_status"] == "pass"

    assert main(["predict", str(built), "--with-route", "--with-version", "--out", str(pred)]) == 0
    assert len(read_jsonl(pred)) == 2

    assert main(["monitor", str(pred)]) == 0
    monitor = json.loads(capsys.readouterr().out)
    assert monitor["total"] == 2

    assert main(["window-alerts", str(pred), "--window-size", "1", "--step-size", "1"]) == 0
    window_alerts = json.loads(capsys.readouterr().out)
    assert window_alerts["window_count"] == 2

    drift_path = tmp_path / "drift.json"
    assert main(["drift-report", str(pred), "--baseline-pred-jsonl", str(pred), "--out", str(drift_path)]) == 0
    drift = json.loads(drift_path.read_text(encoding="utf-8"))
    assert drift["status"] == "stable"
    assert drift["tests"]

    report_path = tmp_path / "eval_report.md"
    assert main(["eval-report", str(pred), "--out", str(report_path)]) == 0
    assert "离线评测报告" in report_path.read_text(encoding="utf-8")

    delivery_path = tmp_path / "delivery.md"
    assert main(["delivery-summary", "--out", str(delivery_path), "--project-root", "."]) == 0
    assert "企业级生产化交付摘要" in delivery_path.read_text(encoding="utf-8")

    readiness_path = tmp_path / "readiness.json"
    assert main(["readiness-check", "--project-root", ".", "--out", str(readiness_path)]) == 0
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    assert readiness["status"] in {"pass", "warn"}
    assert readiness["summary"]["fail"] == 0
