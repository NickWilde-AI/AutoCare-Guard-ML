from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from .parsing import parse_judge_output
from .prompting import render_infer_text, render_user_prompt

logger = logging.getLogger(__name__)


@dataclass
class HeuristicJudge:
    """CPU-only fallback for demos when no fine-tuned checkpoint is present."""

    rubrics: dict[str, str]

    def predict(self, case: dict[str, Any]) -> dict[str, Any]:
        from .schema import ServiceCase

        service_case = ServiceCase.from_dict(case)
        text = " ".join(
            [
                str(service_case.service_context),
                str(service_case.conversation_evidence),
                str(service_case.vehicle_signal_summary),
                str(service_case.fault_evidence),
                str(service_case.service_history_summary),
            ]
        ).lower()

        battery = any(k in text for k in ["电池", "热失控", "冒烟", "焦糊", "温升", "thermal", "battery"])
        charging = any(k in text for k in ["充电", "充不上", "高压", "charging", "hv "])
        brake = any(k in text for k in ["制动", "刹车", "转向", "brake", "steering"])
        powertrain = any(k in text for k in ["动力中断", "跛行", "突然没力", "power loss"])
        adas = any(k in text for k in ["智驾", "辅助驾驶", "误刹", "突然减速", "接管", "adas", "autopilot"])
        cockpit = any(k in text for k in ["车机", "座舱", "远程控车", "app控车"])
        repeat = any(k in text for k in ["重复维修", "一直没修好", "多次进店", "反复"])
        rescue = any(k in text for k in ["救援", "拖车", "高速抛锚", "人员受伤"])
        warranty = any(k in text for k in ["质保", "零件", "索赔", "服务态度"])

        topic = "无风险事件"
        if battery:
            topic = "动力电池与热安全"
        elif charging:
            topic = "充电与高压系统异常"
        elif brake:
            topic = "制动与转向异常"
        elif powertrain:
            topic = "行驶中动力异常"
        elif adas:
            topic = "智能驾驶与驾驶辅助反馈"
        elif rescue:
            topic = "道路救援与人员安全"
        elif cockpit:
            topic = "车机、座舱和远程控车故障"
        elif repeat:
            topic = "重复维修与问题未解决"
        elif warranty:
            topic = "质保、零部件与服务争议"

        vehicle_hit = service_case.has_vehicle_side_evidence()
        motion = str(service_case.vehicle_context.get("vehicle_motion_state") or "").lower()
        driving = motion in {"driving", "行驶"}
        critical_tokens = any(
            k in text for k in ["焦糊", "冒烟", "失控", "失效", "人员", "高速", "热失控", "冒火花"]
        )
        semantic_hit = any(
            [battery, charging, brake, powertrain, adas, cockpit, repeat, rescue, warranty]
        )

        missing = service_case.missing_and_conflicts or {}
        severe_missing = bool(missing.get("missing_fields")) and semantic_hit and not vehicle_hit

        if severe_missing:
            return {
                "risk_level": "mid_risk",
                "event_topic": topic,
                "event_judgment": "insufficient_evidence",
                "recommended_action": "collect_more_evidence",
                "evidence_refs": [],
                "correlation_analysis": "用户描述存在潜在风险，但车辆侧证据不足或冲突，不能判定成立。",
                "uncertainty_reason": "关键车辆证据缺失或无法时间对齐。",
                "service_escalation_flags": [],
                "confidence": 0.7,
            }

        if not semantic_hit and not vehicle_hit:
            return {
                "risk_level": "low_risk",
                "event_topic": "无风险事件",
                "event_judgment": "not_risk_event",
                "recommended_action": "information_reply",
                "evidence_refs": [],
                "correlation_analysis": "对话与车辆侧摘要未形成需要介入的风险事件。",
                "uncertainty_reason": "",
                "service_escalation_flags": [],
                "confidence": 0.85,
            }

        high = bool(vehicle_hit and critical_tokens and (driving or charging or battery or brake or rescue))
        mid = semantic_hit or vehicle_hit
        if high:
            risk, judgment, action = "high_risk", "risk_event", "emergency_review"
        elif mid and vehicle_hit:
            risk, judgment, action = "mid_risk", "risk_event", "create_work_order"
        elif mid:
            risk, judgment, action = "mid_risk", "risk_event", "expert_review"
        else:
            risk, judgment, action = "low_risk", "not_risk_event", "information_reply"

        refs: list[dict[str, Any]] = []
        if service_case.conversation_evidence:
            refs.append(
                {
                    "source": "conversation_evidence",
                    "index": 0,
                    "field": "content",
                    "supports": "event_judgment",
                }
            )
        if vehicle_hit and service_case.fault_evidence:
            refs.append(
                {
                    "source": "fault_evidence",
                    "index": 0,
                    "field": "severity_from_source",
                    "supports": "risk_level",
                }
            )
        elif vehicle_hit:
            refs.append(
                {
                    "source": "vehicle_signal_summary",
                    "field": "warning_lights",
                    "supports": "risk_level",
                }
            )

        return {
            "risk_level": risk,
            "event_topic": topic,
            "event_judgment": judgment,
            "recommended_action": action,
            "evidence_refs": refs,
            "correlation_analysis": "对话描述与车辆侧摘要/故障证据形成同向或需人工复核的关联。",
            "uncertainty_reason": "",
            "service_escalation_flags": [],
            "confidence": 0.92 if high else 0.84,
        }


class TransformersJudge:
    def __init__(self, model_path: str, rubrics: dict[str, str], max_new_tokens: int = 512):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        self.rubrics = rubrics
        self.max_new_tokens = max_new_tokens
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, use_fast=True, trust_remote_code=True)
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype=torch.bfloat16,
            attn_implementation="sdpa",
            trust_remote_code=True,
        ).eval()
        if torch.cuda.is_available():
            self.model = self.model.cuda()

    def predict(self, case: dict[str, Any]) -> dict[str, Any]:
        prompt = render_infer_text(case, self.rubrics)
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
        with self.torch.no_grad():
            output = self.model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,
                pad_token_id=self.tokenizer.pad_token_id,
            )
        gen = self.tokenizer.decode(output[0, inputs["input_ids"].shape[1] :], skip_special_tokens=True)
        return parse_judge_output(gen)


class APIJudge:
    """Judge that calls an OpenAI-compatible API (e.g. DashScope Qwen) for inference.

    This allows running the full pipeline on a Mac without GPU by using a remote
    model API. Supports any OpenAI-compatible endpoint.

    Usage:
        judge = APIJudge(rubrics, model="qwen-plus")
        result = judge.predict(case)
    """

    def __init__(
        self,
        rubrics: dict[str, str],
        model: str = "qwen-plus",
        api_base: str | None = None,
        api_key: str | None = None,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ):
        self.rubrics = rubrics
        self.model = model
        self.api_base = api_base or os.environ.get(
            "QWEN_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        self.api_key = api_key or os.environ.get("QWEN_API_KEY", "")
        self.max_tokens = max_tokens
        self.temperature = temperature

    def predict(self, case: dict[str, Any]) -> dict[str, Any]:
        import httpx

        user_prompt = render_user_prompt(case, self.rubrics)
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": user_prompt}],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = httpx.post(
                f"{self.api_base}/chat/completions",
                json=payload,
                headers=headers,
                timeout=60.0,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return parse_judge_output(content)
        except Exception as e:
            logger.error("API Judge failed: %s", e)
            return {
                "risk_level": "low_risk",
                "event_topic": "无风险事件",
                "correlation_analysis": f"API 调用失败: {e}",
                "event_judgment": "not_risk_event",
                "uncertainty_reason": "API 异常，默认无风险。",
                "recommended_action": "information_reply",
                "evidence_refs": [],
                "service_escalation_flags": [],
            }

