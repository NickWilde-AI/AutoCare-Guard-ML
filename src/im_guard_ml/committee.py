"""Committee-based refinement orchestration for AutoCare service cases."""

from __future__ import annotations

import logging
import os
from typing import Any

from .parsing import parse_judge_output
from .prompting import render_infer_text
from .refinement import Predictor, committee_not_risk_event, refine_dataset
from .schema import ServiceCase

logger = logging.getLogger(__name__)


def build_self_predictor(
    model_path: str, rubrics: dict[str, str], device: str = "cuda"
) -> Predictor:
    from .inference import TransformersJudge

    judge = TransformersJudge(model_path, rubrics)

    def predict(case: dict[str, Any]) -> dict[str, Any]:
        return judge.predict(case)

    return predict


def build_independent_llm_predictor(
    rubrics: dict[str, str],
    model_name: str = "qwen-plus",
    api_base: str | None = None,
    api_key: str | None = None,
) -> Predictor:
    import httpx

    base_url = api_base or os.environ.get(
        "QWEN_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
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
            logger.warning("independent LLM predictor failed: %s, defaulting to safe", e)
            return {
                "event_judgment": "not_risk_event",
                "risk_level": "low_risk",
                "recommended_action": "information_reply",
                "event_topic": "无风险事件",
            }

    return predict


def build_rule_engine_predictor(
    thresholds: dict[str, Any] | None = None,
) -> Predictor:
    """Keyword + vehicle-evidence rule baseline for AutoCare committee."""
    cfg = thresholds or _DEFAULT_RULE_THRESHOLDS

    def predict(case: dict[str, Any]) -> dict[str, Any]:
        service_case = ServiceCase.from_dict(case)
        chat_texts = " ".join(
            str(item.get("content") or item.get("original_content") or "")
            for item in service_case.conversation_evidence
            if isinstance(item, dict)
        )
        hit_topics: list[str] = []
        for topic, keywords in cfg["keywords"].items():
            if any(kw in chat_texts for kw in keywords):
                hit_topics.append(topic)

        vehicle_hit = service_case.has_vehicle_side_evidence()
        critical = any(
            k in chat_texts for k in cfg.get("critical_tokens", [])
        )

        if hit_topics and vehicle_hit and critical:
            return {
                "event_judgment": "risk_event",
                "risk_level": "high_risk",
                "recommended_action": "emergency_review",
                "event_topic": hit_topics[0],
            }
        if hit_topics and vehicle_hit:
            return {
                "event_judgment": "risk_event",
                "risk_level": "mid_risk",
                "recommended_action": "create_work_order",
                "event_topic": hit_topics[0],
            }
        if hit_topics:
            return {
                "event_judgment": "risk_event",
                "risk_level": "mid_risk",
                "recommended_action": "expert_review",
                "event_topic": hit_topics[0],
            }
        if vehicle_hit:
            # 有车辆侧证据但对话未命中主题：证据不足，避免 risk_event + 无风险事件 自相矛盾
            return {
                "event_judgment": "insufficient_evidence",
                "risk_level": "mid_risk",
                "recommended_action": "collect_more_evidence",
                "event_topic": "无风险事件",
            }
        return {
            "event_judgment": "not_risk_event",
            "risk_level": "low_risk",
            "recommended_action": "information_reply",
            "event_topic": "无风险事件",
        }

    return predict


def run_refinement_round(
    train_data: list[dict[str, Any]],
    candidate_pool: list[dict[str, Any]],
    model_path: str,
    rubrics: dict[str, str],
    *,
    independent_model: str = "qwen-plus",
    rule_thresholds: dict[str, Any] | None = None,
    device: str = "cuda",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    logger.info("Building committee predictors...")
    self_pred = build_self_predictor(model_path, rubrics, device=device)
    llm_pred = build_independent_llm_predictor(rubrics, model_name=independent_model)
    rule_pred = build_rule_engine_predictor(rule_thresholds)
    committee = [llm_pred, rule_pred]

    logger.info(
        "Running refinement: train=%d, candidates=%d",
        len(train_data),
        len(candidate_pool),
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


_DEFAULT_RULE_THRESHOLDS: dict[str, Any] = {
    "critical_tokens": ["焦糊", "冒烟", "热失控", "制动失效", "人员受伤", "冒火花"],
    "keywords": {
        "动力电池与热安全": ["电池", "热失控", "冒烟", "焦糊", "温升"],
        "充电与高压系统异常": ["充电", "充不上", "高压", "充电枪"],
        "制动与转向异常": ["制动", "刹车", "转向失灵"],
        "行驶中动力异常": ["动力中断", "跛行", "突然没力"],
        "智能驾驶与驾驶辅助反馈": ["智驾", "误刹", "突然减速", "接管"],
        "道路救援与人员安全": ["救援", "拖车", "高速抛锚", "人员受伤"],
        "车机、座舱和远程控车故障": ["车机", "远程控车", "座舱"],
        "重复维修与问题未解决": ["重复维修", "一直没修好", "多次进店"],
        "质保、零部件与服务争议": ["质保", "索赔", "零件"],
    },
}

# 兼容旧符号
committee_not_violation = committee_not_risk_event
