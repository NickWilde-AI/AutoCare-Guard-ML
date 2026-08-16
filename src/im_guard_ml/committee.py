"""Committee-based refinement orchestration.

Implements the 3-source heterogeneous committee described in the design doc:
  1. Self (current round Judge) — fine-tuned model prediction
  2. Qwen3.5-flash (API) — independent LLM perspective via prompt engineering
  3. Rule engine — non-LLM keyword + threshold baseline

The committee is used during iterative refinement to filter noisy gold labels:
if all three sources agree on not_exist_violation, the sample is considered
reliably safe and excluded from hard-sample injection.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from typing import Any

from .prompting import render_infer_text
from .parsing import parse_judge_output
from .refinement import Predictor, committee_not_violation, refine_dataset

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Predictor factories
# ---------------------------------------------------------------------------


def build_self_predictor(
    model_path: str, rubrics: dict[str, str], device: str = "cuda"
) -> Predictor:
    """Build a predictor from the current-round fine-tuned Judge checkpoint."""
    from .inference import TransformersJudge

    judge = TransformersJudge(model_path, rubrics)

    def predict(case: dict[str, Any]) -> dict[str, Any]:
        return judge.predict(case)

    return predict


def build_flash_predictor(
    rubrics: dict[str, str],
    model_name: str = "qwen3.5-flash",
    api_base: str | None = None,
    api_key: str | None = None,
) -> Predictor:
    """Build a predictor that calls Qwen3.5-flash via OpenAI-compatible API.

    Uses the same prompt template as the fine-tuned model but relies on the
    flash model's zero-shot capability. This provides an independent LLM
    perspective that hasn't been fine-tuned on our data.
    """
    import httpx

    base_url = api_base or os.environ.get("QWEN_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    key = api_key or os.environ.get("QWEN_API_KEY", "")

    def predict(case: dict[str, Any]) -> dict[str, Any]:
        prompt_text = render_infer_text(case, rubrics)
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt_text}],
            "max_tokens": 384,
            "temperature": 0.0,
        }
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        try:
            resp = httpx.post(
                f"{base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=30.0,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return parse_judge_output(content)
        except Exception as e:
            logger.warning("flash predictor failed: %s, defaulting to safe", e)
            return {"final_judgment": "not_exist_violation", "risk_level": "low_risk",
                    "handling_suggestion": "ignore"}

    return predict


def build_rule_engine_predictor(
    thresholds: dict[str, Any] | None = None,
) -> Predictor:
    """Build a rule-engine predictor that mimics the company's online rule system.

    This is a simplified but representative implementation of the keyword +
    threshold rule engine used in production. It provides a non-LLM perspective
    for the committee.
    """
    cfg = thresholds or _DEFAULT_RULE_THRESHOLDS

    def predict(case: dict[str, Any]) -> dict[str, Any]:
        # Aggregate signals from chat evidence
        chat_texts = " ".join(
            item.get("original_content", "")
            for item in case.get("chat_evidence_list", [])
        )
        behavior_summary = case.get("audit_scene", {}).get("behavior_key_summary", {})
        gift_value = float(behavior_summary.get("gift_total_value", 0) or 0)
        abnormals = case.get("behavior_abnormal_list", [])

        # Keyword matching
        hit_topics: list[str] = []
        for topic, keywords in cfg["keywords"].items():
            if any(kw in chat_texts for kw in keywords):
                hit_topics.append(topic)

        # Behavior threshold checks
        behavior_flags: list[str] = []
        if gift_value >= cfg["gift_high_threshold"]:
            behavior_flags.append("high_gift")
        if any("高频" in str(a) or "大额" in str(a) or "批量" in str(a)
               for a in abnormals):
            behavior_flags.append("abnormal_pattern")
        if "异地" in str(behavior_summary.get("login_behavior", "")):
            behavior_flags.append("remote_login")

        # Decision logic
        if hit_topics and behavior_flags:
            return {
                "final_judgment": "exist_violation",
                "risk_level": "high_risk",
                "handling_suggestion": "ban_account",
                "topic": hit_topics[0],
            }
        elif hit_topics:
            return {
                "final_judgment": "exist_violation",
                "risk_level": "mid_risk",
                "handling_suggestion": "warning",
                "topic": hit_topics[0],
            }
        elif behavior_flags:
            return {
                "final_judgment": "exist_violation",
                "risk_level": "mid_risk",
                "handling_suggestion": "limit_account",
                "topic": "无主题",
            }
        else:
            return {
                "final_judgment": "not_exist_violation",
                "risk_level": "low_risk",
                "handling_suggestion": "ignore",
                "topic": "无主题",
            }

    return predict


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_refinement_round(
    train_data: list[dict[str, Any]],
    candidate_pool: list[dict[str, Any]],
    model_path: str,
    rubrics: dict[str, str],
    *,
    flash_model: str = "qwen3.5-flash",
    rule_thresholds: dict[str, Any] | None = None,
    device: str = "cuda",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run one round of committee-based refinement.

    Returns:
        (refined_train_data, stats_dict)
    """
    logger.info("Building committee predictors...")
    self_pred = build_self_predictor(model_path, rubrics, device=device)
    flash_pred = build_flash_predictor(rubrics, model_name=flash_model)
    rule_pred = build_rule_engine_predictor(rule_thresholds)

    committee = [self_pred, flash_pred, rule_pred]

    logger.info(
        "Running refinement: train=%d, candidates=%d",
        len(train_data), len(candidate_pool),
    )
    refined = refine_dataset(
        train_data=train_data,
        candidate_pool=candidate_pool,
        judge_predict=self_pred,
        committee_predictors=committee,
    )

    added = len(refined) - len(train_data)
    stats = {
        "original_size": len(train_data),
        "candidate_pool_size": len(candidate_pool),
        "added_hard_samples": added,
        "refined_size": len(refined),
    }
    logger.info("Refinement complete: +%d hard samples", added)
    return refined, stats


# ---------------------------------------------------------------------------
# Default rule engine configuration
# ---------------------------------------------------------------------------

_DEFAULT_RULE_THRESHOLDS: dict[str, Any] = {
    "gift_high_threshold": 5000.0,
    "keywords": {
        "代刷/包榜": ["代刷", "包榜", "冲榜", "刷榜", "老规矩", "按之前说的"],
        "诈骗引流": ["私V", "稳赚", "本金", "加微信", "加我V", "项目收益"],
        "私下交易": ["私下", "折扣", "外部结算", "转账", "收款", "规避平台"],
        "色情诱导": ["约吗", "私密照", "裸聊", "有偿", "看片"],
        "辱骂攻击": ["废物", "去死", "滚出去", "垃圾"],
        "违禁品交易": ["枪支", "弹药", "毒品", "冰毒"],
    },
}
