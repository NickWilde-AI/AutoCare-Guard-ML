from __future__ import annotations

from pathlib import Path
from typing import Any

DEFAULT_RUBRICS_FILE = "configs/rubrics.yaml"

DEFAULT_CONFIG = {
    "model": {
        "base_model": "Qwen/Qwen3-32B",
        "max_seq_length": 8192,
        "max_new_tokens": 512,
        "do_sample": False,
    },
    "versions": {
        "model_version": "heuristic-public-v0",
        "prompt_version": "prompt-autocare-v1",
        "rubric_version": "rubric-autocare-v1",
        "feature_schema_version": "feature-schema-autocare-v1",
        "postprocess_version": "postprocess-autocare-v1",
    },
    "alert_thresholds": {
        "emergency_review_rate_warn": 0.05,
        "emergency_review_rate_critical": 0.08,
        "parse_non_ok_rate_warn": 0.005,
        "parse_non_ok_rate_critical": 0.02,
        "missing_vehicle_evidence_rate_warn": 0.08,
        "missing_vehicle_evidence_rate_critical": 0.20,
        "unsupported_evidence_rate_warn": 0.02,
        "unsupported_evidence_rate_critical": 0.05,
    },
    "training": {
        "output_dir": "outputs/autocare-risk-judge",
        "num_train_epochs": 2,
        "learning_rate": 0.0001,
        "per_device_train_batch_size": 4,
        "gradient_accumulation_steps": 16,
        "warmup_ratio": 0.03,
        "bf16": True,
        "gradient_checkpointing": True,
        "completion_only": True,
        "enable_field_loss_mask": True,
        "peft": {
            "enabled": True,
            "method": "lora",
            "r": 16,
            "lora_alpha": 32,
            "lora_dropout": 0.05,
            "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
            "qlora_4bit": False,
        },
    },
    "labels": {
        "risk_levels": ["low_risk", "mid_risk", "high_risk"],
        "event_judgments": ["risk_event", "not_risk_event", "insufficient_evidence"],
        "recommended_actions": [
            "information_reply",
            "collect_more_evidence",
            "service_followup",
            "create_work_order",
            "expert_review",
            "emergency_review",
        ],
        "event_topics": [
            "动力电池与热安全",
            "充电与高压系统异常",
            "制动与转向异常",
            "行驶中动力异常",
            "智能驾驶与驾驶辅助反馈",
            "车机、座舱和远程控车故障",
            "重复维修与问题未解决",
            "道路救援与人员安全",
            "质保、零部件与服务争议",
            "无风险事件",
        ],
        # 兼容旧测试键名
        "judgments": ["risk_event", "not_risk_event", "insufficient_evidence"],
        "handling_suggestions": [
            "information_reply",
            "collect_more_evidence",
            "service_followup",
            "create_work_order",
            "expert_review",
            "emergency_review",
        ],
        "topics": [
            "动力电池与热安全",
            "充电与高压系统异常",
            "制动与转向异常",
            "行驶中动力异常",
            "智能驾驶与驾驶辅助反馈",
            "车机、座舱和远程控车故障",
            "重复维修与问题未解决",
            "道路救援与人员安全",
            "质保、零部件与服务争议",
            "无风险事件",
        ],
    },
    "rubrics": {
        "__default__": (
            "low_risk: 普通咨询、轻微体验问题，或已有证据明确不构成安全风险；"
            "mid_risk: 存在明确异常或重复问题，需要工单、补采或专家排查；"
            "high_risk: 可能影响人员、行车、高压或热安全，需要优先人工确认。"
        ),
        "动力电池与热安全": (
            "low_risk: 续航咨询或正常温升范围内的体验问题；"
            "mid_risk: 出现电池相关告警或异常温差，但车辆已安全停放且无人员暴露；"
            "high_risk: 焦糊味、冒烟、热失控迹象或行驶/充电中伴随严重热安全证据。"
        ),
        "充电与高压系统异常": (
            "low_risk: 预约充电设置、桩兼容性等使用咨询；"
            "mid_risk: 多次充电中断或高压告警，当前无立即现场危险；"
            "high_risk: 充电中断伴随高压/热安全证据，或存在人员暴露风险。"
        ),
        "制动与转向异常": (
            "low_risk: 轻微异响咨询且车辆侧无告警；"
            "mid_risk: 重复制动/转向告警，车辆可控停放；"
            "high_risk: 行驶中制动失效/转向异常等行车风险证据。"
        ),
        "行驶中动力异常": (
            "low_risk: 动力体感咨询且无告警；"
            "mid_risk: 动力中断或跛行告警，但已停放；"
            "high_risk: 行驶中动力突然中断并伴随安全风险证据。"
        ),
        "智能驾驶与驾驶辅助反馈": (
            "low_risk: 功能体验吐槽，无同期车辆告警；"
            "mid_risk: 误制动/突然减速等描述且有功能状态摘要印证；"
            "high_risk: 行驶中智驾异常并存在人身或行车风险的车辆侧证据。"
        ),
        "车机、座舱和远程控车故障": (
            "low_risk: 车机卡顿、账号登录等体验问题；"
            "mid_risk: 远程控车失败或重复故障影响服务；"
            "high_risk: 远程控车异常与车辆安全状态冲突且证据充分（仍不直接控车）。"
        ),
        "重复维修与问题未解决": (
            "low_risk: 首次咨询历史工单进度；"
            "mid_risk: 同类问题重复出现，需工单或专家排查；"
            "high_risk: 重复未解决且当前存在安全相关车辆证据。"
        ),
        "道路救援与人员安全": (
            "low_risk: 救援流程咨询；"
            "mid_risk: 需要道路救援但人员已脱离危险；"
            "high_risk: 人员或行车安全正在受影响，需紧急人工确认。"
        ),
        "质保、零部件与服务争议": (
            "low_risk: 质保政策咨询；"
            "mid_risk: 争议需服务升级标记与工单跟进；"
            "high_risk: 争议同时伴随明确车辆安全证据（安全与客诉分流处理）。"
        ),
        "无风险事件": (
            "low_risk: 明确无风险或证据足以排除安全风险；"
            "mid_risk: 不适用；"
            "high_risk: 不适用。"
        ),
    },
}


def merge_rubrics_file(
    cfg: dict[str, Any], rubrics_path: str | Path = DEFAULT_RUBRICS_FILE
) -> dict[str, Any]:
    """把 configs/rubrics.yaml 的逐主题 rubric 合并进配置。"""
    from .dataio import load_yaml

    rubrics_file = load_yaml(rubrics_path)
    topics_rubrics = rubrics_file.get("topics") if isinstance(rubrics_file, dict) else None
    if isinstance(topics_rubrics, dict):
        merged = dict(cfg.get("rubrics", {}))
        for topic, entry in topics_rubrics.items():
            if isinstance(entry, dict):
                merged[topic] = (
                    f"low_risk: {entry.get('low_risk', '')}；"
                    f"mid_risk: {entry.get('mid_risk', '')}；"
                    f"high_risk: {entry.get('high_risk', '')}"
                )
            elif isinstance(entry, str):
                merged[topic] = entry
        cfg = dict(cfg)
        cfg["rubrics"] = merged
    return cfg
