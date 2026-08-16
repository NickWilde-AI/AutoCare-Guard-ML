from __future__ import annotations

from datetime import UTC, datetime
from statistics import quantiles
from typing import Any

from .evaluation import eval_binary, eval_multi_field


DEFAULT_SUCCESS_METRICS = ["final_judgment_f1", "handling_macro_f1", "ban_account_fpr"]
DEFAULT_GUARDRAILS = {
    "ban_account_fpr_max": 0.03,
    "parse_non_ok_rate_max": 0.02,
    "p95_latency_ms_max": 1200.0,
}


def build_ab_report(
    control_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare a control and candidate prediction replay for rollout decisions."""
    rollout_cfg = config or {}
    ab_cfg = rollout_cfg.get("ab_test", rollout_cfg)
    success_metrics = list(ab_cfg.get("success_metrics") or DEFAULT_SUCCESS_METRICS)
    guardrails = {**DEFAULT_GUARDRAILS, **(ab_cfg.get("guardrails") or {})}

    control_by_id = _index_by_ticket(control_rows)
    candidate_by_id = _index_by_ticket(candidate_rows)
    common_ids = sorted(set(control_by_id) & set(candidate_by_id))
    paired_control = [control_by_id[ticket_id] for ticket_id in common_ids]
    paired_candidate = [candidate_by_id[ticket_id] for ticket_id in common_ids]

    control_metrics = _variant_metrics(paired_control)
    candidate_metrics = _variant_metrics(paired_candidate)
    deltas = {
        key: _metric_delta(candidate_metrics.get(key), control_metrics.get(key))
        for key in sorted(set(control_metrics) | set(candidate_metrics))
    }
    guardrail_results = _guardrail_results(candidate_metrics, guardrails)
    success_results = _success_results(control_metrics, candidate_metrics, success_metrics)
    decision = _decision(success_results, guardrail_results, len(common_ids), len(control_rows), len(candidate_rows))
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "status": decision["status"],
        "recommendation": decision["recommendation"],
        "sample_alignment": {
            "control_total": len(control_rows),
            "candidate_total": len(candidate_rows),
            "paired_total": len(common_ids),
            "control_only": len(set(control_by_id) - set(candidate_by_id)),
            "candidate_only": len(set(candidate_by_id) - set(control_by_id)),
        },
        "success_metrics": success_results,
        "guardrails": guardrail_results,
        "metrics": {
            "control": control_metrics,
            "candidate": candidate_metrics,
            "delta": deltas,
        },
        "notes": [
            "A/B 报告基于离线 replay prediction JSONL；真实线上放量仍需要接入生产流量分桶、人审回写和告警平台。",
            "`ban_account_fpr` 以 gold 非违规样本中被预测为 ban_account 的比例计算。",
        ],
    }


def render_ab_report_markdown(report: dict[str, Any], *, title: str = "AI-IM-Guard-ML A/B 灰度对比报告") -> str:
    lines = [
        f"# {title}",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- 状态：`{report['status']}`",
        f"- 建议：{report['recommendation']}",
        "",
        "## 样本对齐",
        "",
        "| 项目 | 数量 |",
        "| --- | ---: |",
    ]
    for key, value in report["sample_alignment"].items():
        lines.append(f"| {key} | {value} |")
    lines.extend(["", "## 主指标", "", "| 指标 | control | candidate | delta | 状态 |", "| --- | ---: | ---: | ---: | --- |"])
    control = report["metrics"]["control"]
    candidate = report["metrics"]["candidate"]
    delta = report["metrics"]["delta"]
    for item in report["success_metrics"]:
        metric = item["metric"]
        lines.append(
            f"| {metric} | {_fmt(control.get(metric))} | {_fmt(candidate.get(metric))} | "
            f"{_fmt(delta.get(metric))} | {item['status']} |"
        )
    lines.extend(["", "## Guardrails", "", "| Guardrail | 当前值 | 阈值 | 状态 |", "| --- | ---: | ---: | --- |"])
    for item in report["guardrails"]:
        lines.append(f"| {item['name']} | {_fmt(item['value'])} | {_fmt(item['threshold'])} | {item['status']} |")
    lines.extend(["", "## 说明", ""])
    lines.extend(f"- {note}" for note in report.get("notes", []))
    lines.append("")
    return "\n".join(lines)


def _index_by_ticket(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for idx, row in enumerate(rows):
        ticket_id = str(row.get("ticket_id") or row.get("id") or idx)
        indexed[ticket_id] = row
    return indexed


def _variant_metrics(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    pairs = [row for row in rows if isinstance(row.get("label"), dict) and isinstance(row.get("prediction"), dict)]
    gold = [row["label"] for row in pairs]
    pred = [row["prediction"] for row in pairs]
    metrics: dict[str, float | None] = {
        "sample_count": float(len(rows)),
        "labeled_count": float(len(pairs)),
        "parse_non_ok_rate": _parse_non_ok_rate(rows),
        "p95_latency_ms": _p95_latency_ms(rows),
        "human_review_overturn_rate": _human_review_overturn_rate(rows),
    }
    if not pairs:
        metrics.update(
            {
                "final_judgment_f1": None,
                "final_judgment_fpr": None,
                "risk_macro_f1": None,
                "handling_macro_f1": None,
                "ban_account_fpr": None,
            }
        )
        return metrics

    binary_targets = [1 if item.get("final_judgment") == "exist_violation" else 0 for item in gold]
    binary_preds = [1 if item.get("final_judgment") == "exist_violation" else 0 for item in pred]
    binary = eval_binary(binary_targets, binary_preds)
    multi = eval_multi_field(gold, pred)
    metrics.update(
        {
            "final_judgment_f1": binary["f1"],
            "final_judgment_fpr": binary["fpr"],
            "risk_macro_f1": multi["risk_macro_f1"],
            "handling_macro_f1": multi["handling_macro_f1"],
            "ban_account_fpr": _ban_account_fpr(gold, pred),
        }
    )
    return metrics


def _parse_non_ok_rate(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    predictions = [row.get("prediction", row) for row in rows]
    count = sum(1 for pred in predictions if pred.get("parse_status") not in (None, "ok"))
    return count / len(rows)


def _p95_latency_ms(rows: list[dict[str, Any]]) -> float:
    values: list[float] = []
    for row in rows:
        pred = row.get("prediction", {})
        raw = pred.get("latency_ms", row.get("latency_ms"))
        try:
            values.append(float(raw))
        except (TypeError, ValueError):
            continue
    if not values:
        return 0.0
    values = sorted(values)
    if len(values) < 2:
        return values[0]
    return float(quantiles(values, n=100, method="inclusive")[94])


def _human_review_overturn_rate(rows: list[dict[str, Any]]) -> float | None:
    reviewed = [
        row
        for row in rows
        if "review_result" in row or "is_model_error" in row or "review" in row
    ]
    if not reviewed:
        return None
    overturn = 0
    for row in reviewed:
        review = row.get("review") or {}
        is_error = row.get("is_model_error", review.get("is_model_error"))
        review_result = row.get("review_result", review.get("review_result"))
        if is_error is True or str(review_result).lower() in {"overturn", "overturned", "reject", "model_error"}:
            overturn += 1
    return overturn / len(reviewed)


def _ban_account_fpr(gold: list[dict[str, Any]], pred: list[dict[str, Any]]) -> float:
    negatives = [idx for idx, item in enumerate(gold) if item.get("final_judgment") != "exist_violation"]
    if not negatives:
        return 0.0
    false_bans = sum(1 for idx in negatives if pred[idx].get("handling_suggestion") == "ban_account")
    return false_bans / len(negatives)


def _metric_delta(candidate: float | None, control: float | None) -> float | None:
    if candidate is None or control is None:
        return None
    return float(candidate) - float(control)


def _success_results(
    control: dict[str, float | None],
    candidate: dict[str, float | None],
    metrics: list[str],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for metric in metrics:
        control_value = control.get(metric)
        candidate_value = candidate.get(metric)
        if control_value is None or candidate_value is None:
            status = "missing"
        elif metric.endswith("_fpr") or metric.endswith("_rate"):
            status = "pass" if candidate_value <= control_value else "fail"
        else:
            status = "pass" if candidate_value >= control_value else "fail"
        results.append(
            {
                "metric": metric,
                "control": control_value,
                "candidate": candidate_value,
                "delta": _metric_delta(candidate_value, control_value),
                "status": status,
            }
        )
    return results


def _guardrail_results(metrics: dict[str, float | None], guardrails: dict[str, float]) -> list[dict[str, Any]]:
    mapping = {
        "ban_account_fpr_max": "ban_account_fpr",
        "parse_non_ok_rate_max": "parse_non_ok_rate",
        "p95_latency_ms_max": "p95_latency_ms",
        "human_review_overturn_rate_max": "human_review_overturn_rate",
    }
    results: list[dict[str, Any]] = []
    for guardrail, metric in mapping.items():
        if guardrail not in guardrails:
            continue
        value = metrics.get(metric)
        threshold = float(guardrails[guardrail])
        status = "missing" if value is None else "pass" if value <= threshold else "fail"
        results.append({"name": guardrail, "metric": metric, "value": value, "threshold": threshold, "status": status})
    return results


def _decision(
    success_results: list[dict[str, Any]],
    guardrail_results: list[dict[str, Any]],
    paired_total: int,
    control_total: int,
    candidate_total: int,
) -> dict[str, str]:
    if paired_total == 0:
        return {"status": "fail", "recommendation": "没有可对齐的 ticket_id，不能做 A/B 晋级判断。"}
    if paired_total < min(control_total, candidate_total):
        alignment_note = "样本未完全对齐，建议先修正 replay 输入。"
    else:
        alignment_note = "样本已按 ticket_id 对齐。"
    if any(item["status"] == "fail" for item in guardrail_results):
        return {"status": "hold", "recommendation": f"候选版本触发 guardrail，保持当前版本；{alignment_note}"}
    if any(item["status"] == "missing" for item in guardrail_results + success_results):
        return {"status": "hold", "recommendation": f"关键指标缺失，先补齐评测/人审/延迟字段；{alignment_note}"}
    if any(item["status"] == "fail" for item in success_results):
        return {"status": "hold", "recommendation": f"候选版本主指标未优于 control，暂不放量；{alignment_note}"}
    return {"status": "promote", "recommendation": f"候选版本主指标不退化且 guardrail 通过，可进入下一灰度阶段；{alignment_note}"}


def _fmt(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)
