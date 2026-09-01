import json

from autocare_guard_ml.cli import main
from autocare_guard_ml.rollout import build_ab_report, render_ab_report_markdown


def _row(ticket_id, label, prediction, **extra):
    return {"ticket_id": ticket_id, "label": label, "prediction": prediction, **extra}


SAFE = {
    "risk_level": "low_risk",
    "event_topic": "无风险事件",
    "event_judgment": "not_risk_event",
    "recommended_action": "information_reply",
}
RISK = {
    "risk_level": "high_risk",
    "event_topic": "动力电池与热安全",
    "event_judgment": "risk_event",
    "recommended_action": "emergency_review",
}
FOLLOWUP = {
    "risk_level": "mid_risk",
    "event_topic": "动力电池与热安全",
    "event_judgment": "risk_event",
    "recommended_action": "service_followup",
}


def test_build_ab_report_promotes_when_candidate_improves_and_guardrails_pass():
    control = [
        _row("safe-1", SAFE, SAFE),
        _row("risk-1", RISK, FOLLOWUP),
    ]
    candidate = [
        _row("safe-1", SAFE, {**SAFE, "latency_ms": 20}),
        _row("risk-1", RISK, {**RISK, "latency_ms": 30}),
    ]

    report = build_ab_report(control, candidate)

    assert report["status"] == "promote"
    assert report["sample_alignment"]["paired_total"] == 2
    assert report["metrics"]["candidate"]["handling_macro_f1"] > report["metrics"]["control"]["handling_macro_f1"]
    assert all(item["status"] == "pass" for item in report["guardrails"])


def test_build_ab_report_holds_when_candidate_false_emergency_on_safe_cases():
    control = [
        _row("safe-1", SAFE, SAFE),
        _row("risk-1", RISK, RISK),
    ]
    candidate = [
        _row("safe-1", SAFE, {**SAFE, "recommended_action": "emergency_review"}),
        _row("risk-1", RISK, RISK),
    ]

    report = build_ab_report(control, candidate)

    assert report["status"] == "hold"
    assert any(
        item["name"] == "emergency_review_fpr_max" and item["status"] == "fail"
        for item in report["guardrails"]
    )


def test_render_ab_report_markdown_contains_decision():
    report = build_ab_report([_row("safe-1", SAFE, SAFE)], [_row("safe-1", SAFE, SAFE)])

    text = render_ab_report_markdown(report)

    assert "A/B 灰度对比报告" in text
    assert "Guardrails" in text
    assert "建议" in text


def test_cli_ab_report_writes_markdown_and_json(tmp_path):
    control = tmp_path / "control.jsonl"
    candidate = tmp_path / "candidate.jsonl"
    out = tmp_path / "ab.md"
    json_out = tmp_path / "ab.json"
    row = _row("safe-1", SAFE, SAFE)
    control.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    candidate.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")

    code = main(
        [
            "ab-report",
            "--control",
            str(control),
            "--candidate",
            str(candidate),
            "--out",
            str(out),
            "--json-out",
            str(json_out),
        ]
    )

    assert code == 0
    assert "A/B 灰度对比报告" in out.read_text(encoding="utf-8")
    assert json.loads(json_out.read_text(encoding="utf-8"))["status"] == "promote"
