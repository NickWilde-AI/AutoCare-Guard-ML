from __future__ import annotations

import json
from pathlib import Path

from im_guard_ml.cli import main
from im_guard_ml.training_readiness import build_training_readiness_report


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def _row(ticket_id: str, *, task_type: str = "public_binary", handling: str = "warning") -> dict:
    return {
        "ticket_id": ticket_id,
        "task_type": task_type,
        "audit_scene": {"chat_type": "public_safety_guardrail"},
        "chat_evidence_list": [{"original_content": "加微信稳赚。"}],
        "behavior_abnormal_list": [],
        "label": {
            "risk_level": "mid_risk",
            "topic": "诈骗引流",
            "correlation_analysis": "公开安全数据仅提供文本侧监督。",
            "final_judgment": "exist_violation",
            "judgment_basis": "公开安全样本。",
            "handling_suggestion": handling,
        },
    }


def test_training_readiness_detects_public_binary_strong_handling(tmp_path):
    data = tmp_path / "train.jsonl"
    _write_jsonl(data, [_row("bad", handling="ban_account")])

    report = build_training_readiness_report(data, max_scan_rows=10)

    check = next(item for item in report["checks"] if item["name"] == "public_binary_guardrail")
    assert check["status"] == "fail"
    assert check["public_strong_handling_count"] == 1


def test_training_readiness_reports_missing_train_dependencies(tmp_path):
    data = tmp_path / "train.jsonl"
    _write_jsonl(data, [_row("ok")])

    report = build_training_readiness_report(data, max_scan_rows=10)

    dep_check = next(item for item in report["checks"] if item["name"] == "train_dependencies")
    assert dep_check["status"] in {"pass", "fail"}
    assert "recommended_commands" in report
    assert report["training_task"]["objective"].startswith("Learn structured")


def test_cli_train_readiness_writes_report(tmp_path):
    data = tmp_path / "train.jsonl"
    out = tmp_path / "training_readiness.json"
    _write_jsonl(data, [_row("ok")])

    assert main(["train-readiness", str(data), "--out", str(out), "--max-scan-rows", "10"]) in {0, 1}
    body = json.loads(out.read_text(encoding="utf-8"))
    assert body["dataset"]["rows"] == 1
    assert any(item["name"] == "public_binary_guardrail" for item in body["checks"])
