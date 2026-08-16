from __future__ import annotations

from collections.abc import Callable
from typing import Any

Predictor = Callable[[dict[str, Any]], dict[str, Any]]


def committee_not_violation(case: dict[str, Any], predictors: list[Predictor]) -> bool:
    votes = [predictor(case).get("final_judgment") for predictor in predictors]
    return bool(votes) and all(vote == "not_exist_violation" for vote in votes)


def refine_dataset(
    train_data: list[dict[str, Any]],
    candidate_pool: list[dict[str, Any]],
    judge_predict: Predictor,
    committee_predictors: list[Predictor],
) -> list[dict[str, Any]]:
    refined = list(train_data)
    seen_ids = {row.get("ticket_id") for row in train_data}
    for case in candidate_pool:
        gold = case.get("label", {})
        if gold.get("final_judgment") != "exist_violation":
            continue
        if case.get("ticket_id") in seen_ids:
            continue
        pred = judge_predict(case)
        if pred.get("final_judgment") == "exist_violation":
            continue
        if committee_not_violation(case, committee_predictors):
            continue
        enriched = dict(case)
        enriched["source"] = "refinement_hard"
        enriched["prev_round_pred"] = pred
        enriched["kept_in_train"] = True
        refined.append(enriched)
    return refined

