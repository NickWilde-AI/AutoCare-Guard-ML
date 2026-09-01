from __future__ import annotations

from collections.abc import Callable
from typing import Any

Predictor = Callable[[dict[str, Any]], dict[str, Any]]


def _judgment(pred: dict[str, Any]) -> str:
    return str(pred.get("event_judgment") or pred.get("final_judgment") or "")


def committee_not_risk_event(case: dict[str, Any], predictors: list[Predictor]) -> bool:
    votes = [_judgment(predictor(case)) for predictor in predictors]
    return bool(votes) and all(vote == "not_risk_event" for vote in votes)


# 兼容旧导入名
committee_not_violation = committee_not_risk_event


def refine_dataset(
    train_data: list[dict[str, Any]],
    candidate_pool: list[dict[str, Any]],
    judge_predict: Predictor,
    committee_predictors: list[Predictor],
) -> list[dict[str, Any]]:
    refined = list(train_data)
    seen_ids = {
        row.get("case_id") or row.get("ticket_id") for row in train_data
    }
    for case in candidate_pool:
        gold = case.get("label", {})
        if _judgment(gold) != "risk_event":
            continue
        case_id = case.get("case_id") or case.get("ticket_id")
        if case_id in seen_ids:
            continue
        pred = judge_predict(case)
        if _judgment(pred) == "risk_event":
            continue
        if committee_not_risk_event(case, committee_predictors):
            continue
        enriched = dict(case)
        enriched["source"] = "refinement_hard"
        enriched["prev_round_pred"] = pred
        enriched["kept_in_train"] = True
        refined.append(enriched)
    return refined
