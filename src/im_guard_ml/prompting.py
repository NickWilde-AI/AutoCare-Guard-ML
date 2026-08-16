from __future__ import annotations

import json
from typing import Any


PROMPT_TEMPLATE = """你是直播平台 IM 私聊违规审核 Judge。请基于下面的审核场景、聊天证据和行为异常证据，结合违规主题列表与处置策略表，输出严格 JSON。

<违规主题清单>
代刷/包榜、色情诱导、诈骗引流、私下交易、政治敏感、辱骂攻击、未成年保护、版权侵犯、虚假信息、自伤诱导、违禁品交易
</违规主题清单>

<风险等级 rubric>
{topic_rubric}
</风险等级 rubric>

<处置策略表>
- ignore：不存在违规或风险极低。
- warning：低/中风险且首次出现，仅站内警示。
- limit_account：中/高风险且具备行为印证，限号 7-30 天。
- ban_account：高风险且证据链完整，永久封禁并触发人审复核。
</处置策略表>

<审核场景>
{audit_scene}
</审核场景>

<聊天证据>
{chat_evidence}
</聊天证据>

<行为异常证据>
{behavior_abnormal}
</行为异常证据>

请按以下 JSON Schema 输出，字段顺序固定：
{{"risk_level": "low_risk|mid_risk|high_risk",
 "topic": "<违规主题清单中的某一项或 '无主题'>",
 "correlation_analysis": "<语义+行为关联分析，1-3句>",
 "final_judgment": "exist_violation|not_exist_violation",
 "judgment_basis": "<判定理由，引用证据要点>",
 "handling_suggestion": "ignore|warning|limit_account|ban_account"}}"""

CHAT_TEMPLATE = "<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n{assistant}<|im_end|>"
INFER_TEMPLATE = "<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n"
RESPONSE_PREFIX = "<|im_start|>assistant\n"


def render_user_prompt(case: dict[str, Any], rubrics: dict[str, str]) -> str:
    label_topic = case.get("hint_topic") or case.get("label", {}).get("topic", "__default__")
    topic_rubric = rubrics.get(label_topic, rubrics.get("__default__", ""))
    return PROMPT_TEMPLATE.format(
        topic_rubric=topic_rubric,
        audit_scene=json.dumps(case.get("audit_scene", {}), ensure_ascii=False, indent=2),
        chat_evidence=json.dumps(case.get("chat_evidence_list", []), ensure_ascii=False, indent=2),
        behavior_abnormal=json.dumps(case.get("behavior_abnormal_list", []), ensure_ascii=False, indent=2),
    )


def render_assistant_label(label: dict[str, Any]) -> str:
    obj = {
        "risk_level": label["risk_level"],
        "topic": label.get("topic", "无主题"),
        "correlation_analysis": label.get("correlation_analysis", ""),
        "final_judgment": label["final_judgment"],
        "judgment_basis": label.get("judgment_basis", ""),
        "handling_suggestion": label["handling_suggestion"],
    }
    return json.dumps(obj, ensure_ascii=False)


def render_train_text(case: dict[str, Any], rubrics: dict[str, str]) -> str:
    return CHAT_TEMPLATE.format(
        user=render_user_prompt(case, rubrics),
        assistant=render_assistant_label(case["label"]),
    )


def render_infer_text(case: dict[str, Any], rubrics: dict[str, str]) -> str:
    return INFER_TEMPLATE.format(user=render_user_prompt(case, rubrics))

