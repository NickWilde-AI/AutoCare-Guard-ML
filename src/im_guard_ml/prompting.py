from __future__ import annotations

import json
from typing import Any


PROMPT_TEMPLATE = """你是新能源汽车售后风险研判 Judge。请基于服务上下文、车辆上下文、对话证据、车辆信号摘要、故障证据和服务历史，结合风险主题与处置策略，输出严格 JSON。

<风险主题清单>
动力电池与热安全、充电与高压系统异常、制动与转向异常、行驶中动力异常、智能驾驶与驾驶辅助反馈、车机、座舱和远程控车故障、重复维修与问题未解决、道路救援与人员安全、质保、零部件与服务争议、无风险事件
</风险主题清单>

<风险等级 rubric>
{topic_rubric}
</风险等级 rubric>

<事件判断>
- risk_event：当前信息构成需要介入的风险事件。
- not_risk_event：明确不构成风险事件。
- insufficient_evidence：证据不足，不能把缺失当成正常。
</事件判断>

<处置策略表>
- information_reply：普通信息回复候选。
- collect_more_evidence：建议补采对话或车辆侧信息。
- service_followup：建议客服继续询问或跟进。
- create_work_order：建议创建或补充售后工单。
- expert_review：技术专家复核。
- emergency_review：紧急人工确认；不得仅凭情绪文本触发，且不能直接控车。
</处置策略表>

注意：
1. high_risk 不等于 emergency_review。
2. evidence_refs 只能引用输入中真实存在的来源与字段。
3. 重大客诉使用 service_escalation_flags，不要塞进 event_topic。
4. 智能驾驶主题只做售后风险研判，不做责任认定。

<service_context>
{service_context}
</service_context>

<vehicle_context>
{vehicle_context}
</vehicle_context>

<conversation_evidence>
{conversation_evidence}
</conversation_evidence>

<vehicle_signal_summary>
{vehicle_signal_summary}
</vehicle_signal_summary>

<fault_evidence>
{fault_evidence}
</fault_evidence>

<service_history_summary>
{service_history_summary}
</service_history_summary>

<missing_and_conflicts>
{missing_and_conflicts}
</missing_and_conflicts>

请按以下 JSON Schema 输出，字段顺序固定：
{{"risk_level": "low_risk|mid_risk|high_risk",
 "event_topic": "<风险主题清单中的某一项>",
 "event_judgment": "risk_event|not_risk_event|insufficient_evidence",
 "recommended_action": "information_reply|collect_more_evidence|service_followup|create_work_order|expert_review|emergency_review",
 "evidence_refs": [{{"source":"fault_evidence","index":0,"field":"severity_from_source","supports":"risk_level"}}],
 "correlation_analysis": "<多证据关联分析，1-3句>",
 "uncertainty_reason": "<缺失/过期/冲突说明，可空>",
 "service_escalation_flags": []}}"""

CHAT_TEMPLATE = "<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n{assistant}<|im_end|>"
INFER_TEMPLATE = "<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n"
RESPONSE_PREFIX = "<|im_start|>assistant\n"


def render_user_prompt(case: dict[str, Any], rubrics: dict[str, str]) -> str:
    label = case.get("label") or {}
    label_topic = (
        case.get("hint_topic")
        or label.get("event_topic")
        or label.get("topic")
        or "__default__"
    )
    topic_rubric = rubrics.get(label_topic, rubrics.get("__default__", ""))
    return PROMPT_TEMPLATE.format(
        topic_rubric=topic_rubric,
        service_context=json.dumps(
            case.get("service_context") or case.get("audit_scene") or {},
            ensure_ascii=False,
            indent=2,
        ),
        vehicle_context=json.dumps(case.get("vehicle_context") or {}, ensure_ascii=False, indent=2),
        conversation_evidence=json.dumps(
            case.get("conversation_evidence") or case.get("chat_evidence_list") or [],
            ensure_ascii=False,
            indent=2,
        ),
        vehicle_signal_summary=json.dumps(
            case.get("vehicle_signal_summary") or {}, ensure_ascii=False, indent=2
        ),
        fault_evidence=json.dumps(case.get("fault_evidence") or [], ensure_ascii=False, indent=2),
        service_history_summary=json.dumps(
            case.get("service_history_summary") or {}, ensure_ascii=False, indent=2
        ),
        missing_and_conflicts=json.dumps(
            case.get("missing_and_conflicts") or {}, ensure_ascii=False, indent=2
        ),
    )


def render_assistant_label(label: dict[str, Any]) -> str:
    obj = {
        "risk_level": label["risk_level"],
        "event_topic": label.get("event_topic") or label.get("topic", "无风险事件"),
        "event_judgment": label.get("event_judgment")
        or label.get("final_judgment", "not_risk_event"),
        "recommended_action": label.get("recommended_action")
        or label.get("handling_suggestion", "information_reply"),
        "evidence_refs": label.get("evidence_refs") or [],
        "correlation_analysis": label.get("correlation_analysis", ""),
        "uncertainty_reason": label.get("uncertainty_reason")
        or label.get("judgment_basis", ""),
        "service_escalation_flags": label.get("service_escalation_flags") or [],
    }
    return json.dumps(obj, ensure_ascii=False)


def render_train_text(case: dict[str, Any], rubrics: dict[str, str]) -> str:
    return CHAT_TEMPLATE.format(
        user=render_user_prompt(case, rubrics),
        assistant=render_assistant_label(case["label"]),
    )


def render_infer_text(case: dict[str, Any], rubrics: dict[str, str]) -> str:
    return INFER_TEMPLATE.format(user=render_user_prompt(case, rubrics))
