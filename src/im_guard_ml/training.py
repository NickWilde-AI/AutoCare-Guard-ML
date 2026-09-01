from __future__ import annotations

import json
import re
from typing import Any

from .prompting import INFER_TEMPLATE, render_assistant_label, render_user_prompt

# Regex to locate JSON field spans: captures "field_name": "field_value"
# 公开二分类数据只监督 event_judgment + 文本字段；
# risk_level / event_topic / recommended_action 均不参与损失。
_FIELD_PATTERN = re.compile(
    r'"(risk_level|event_topic|topic|recommended_action|handling_suggestion)"\s*:\s*"[^"]*"'
)


def run_sft(config: dict[str, Any], dataset_name_or_path: str, rubrics: dict[str, str]) -> None:
    from datasets import load_dataset
    from transformers import AutoTokenizer
    from trl import SFTConfig, SFTTrainer

    model_name = config["model"]["base_model"]
    train_cfg = config["training"]
    peft_config = _build_peft_config(train_cfg)
    tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True, trust_remote_code=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    if dataset_name_or_path.endswith(".jsonl"):
        raw = load_dataset("json", data_files=dataset_name_or_path, split="train")
    else:
        raw = load_dataset(dataset_name_or_path, split="train")

    # Normalize public labels conservatively as a safety net (belt & suspenders)
    raw = raw.map(_normalize_public_binary_labels)

    enable_field_mask = train_cfg.get("enable_field_loss_mask", True)
    tokenized = raw.map(
        lambda case: tokenize_training_case(
            case,
            tokenizer=tokenizer,
            rubrics=rubrics,
            enable_field_mask=enable_field_mask,
        ),
        remove_columns=raw.column_names,
    )
    # P1-15：不再依赖 TRL 内部类（trl.trainer.sft_trainer.DataCollatorForLanguageModeling
    # 在 v0.9–v0.12 实际是 transformers 的 MLM collator，按当前参数构造必然 TypeError）。
    # 使用自研 CompletionMaskCollator：completion_mask 同时携带行级（Prompt 屏蔽）
    # 与字段级（public_binary 的 risk/topic/handling 屏蔽）信息，对 TRL 版本无依赖。
    collator = CompletionMaskCollator(
        pad_token_id=tokenizer.pad_token_id,
        max_length=config["model"]["max_seq_length"],
    )

    args = SFTConfig(
        output_dir=train_cfg["output_dir"],
        num_train_epochs=train_cfg["num_train_epochs"],
        per_device_train_batch_size=train_cfg["per_device_train_batch_size"],
        gradient_accumulation_steps=train_cfg["gradient_accumulation_steps"],
        learning_rate=train_cfg["learning_rate"],
        warmup_ratio=train_cfg["warmup_ratio"],
        max_length=config["model"]["max_seq_length"],
        bf16=train_cfg.get("bf16", True),
        gradient_checkpointing=train_cfg.get("gradient_checkpointing", True),
        dataset_kwargs={"skip_prepare_dataset": True},
        logging_steps=10,
    )
    trainer = SFTTrainer(
        model=model_name,
        args=args,
        train_dataset=tokenized,
        data_collator=collator,
        processing_class=tokenizer,
        peft_config=peft_config,
    )
    trainer.train()
    trainer.save_model(train_cfg["output_dir"])


def tokenize_training_case(
    case: dict[str, Any],
    *,
    tokenizer: Any,
    rubrics: dict[str, str],
    enable_field_mask: bool = True,
) -> dict[str, list[int]]:
    prompt_text = INFER_TEMPLATE.format(user=render_user_prompt(case, rubrics))
    completion_text = render_assistant_label(case["label"]) + "<|im_end|>"
    prompt_ids = tokenizer.encode(prompt_text, add_special_tokens=False)
    completion = tokenizer(
        completion_text,
        add_special_tokens=False,
        return_offsets_mapping=True,
    )
    completion_ids = completion["input_ids"]
    completion_mask = [1] * len(completion_ids)

    if enable_field_mask and case.get("task_type") == "public_binary":
        offsets = completion.get("offset_mapping") or []
        for match in _FIELD_PATTERN.finditer(completion_text):
            char_start, char_end = match.start(), match.end()
            for idx, (tok_start, tok_end) in enumerate(offsets):
                if tok_start < char_end and tok_end > char_start:
                    completion_mask[idx] = 0

    return {
        "input_ids": prompt_ids + completion_ids,
        "completion_mask": [0] * len(prompt_ids) + completion_mask,
    }


IGNORE_INDEX = -100


def build_completion_labels(input_ids: list[int], completion_mask: list[int]) -> list[int]:
    """Pure-function label builder（可无 torch 单测）：
    只保留 completion_mask==1 的 token 参与损失，其余（Prompt/被屏蔽字段）置 -100。
    """
    return [
        token_id if mask == 1 else IGNORE_INDEX
        for token_id, mask in zip(input_ids, completion_mask)
    ]


class CompletionMaskCollator:
    """Version-proof collator：padding + completion_mask → labels（P1-15）。

    不依赖 TRL 内部 collator 的构造签名（该签名在 TRL 0.9–0.12 间为 MLM
    collator），只消费数据集中已有的 input_ids/completion_mask，并负责
    keep_end 截断与 attention_mask 生成，兼容 SFTTrainer 的普通 callable。
    """

    def __init__(self, pad_token_id: int, max_length: int | None = None):
        self.pad_token_id = pad_token_id
        self.max_length = max_length

    def __call__(self, features: list[dict[str, Any]]) -> dict[str, Any]:
        import torch

        input_ids_list: list[torch.Tensor] = []
        labels_list: list[torch.Tensor] = []
        for feature in features:
            ids = list(feature["input_ids"])
            mask = list(feature.get("completion_mask", [1] * len(ids)))
            if self.max_length and len(ids) > self.max_length:
                # keep_end 截断：与 SFTConfig.max_length 对齐，ids 与 mask 同步截断。
                ids = ids[-self.max_length:]
                mask = mask[-self.max_length:]
            labels = build_completion_labels(ids, mask)
            input_ids_list.append(torch.tensor(ids, dtype=torch.long))
            labels_list.append(torch.tensor(labels, dtype=torch.long))

        input_ids = torch.nn.utils.rnn.pad_sequence(
            input_ids_list, batch_first=True, padding_value=self.pad_token_id
        )
        attention_mask = (input_ids != self.pad_token_id).long()
        labels = torch.nn.utils.rnn.pad_sequence(
            labels_list, batch_first=True, padding_value=IGNORE_INDEX
        )
        return {"input_ids": input_ids, "attention_mask": attention_mask, "labels": labels}


def _normalize_public_binary_labels(case: dict[str, Any]) -> dict[str, Any]:
    """Cap public binary labels conservatively as a safety net.

    Public binary samples lack true risk_level and recommended_action annotations.
    We assign conservative placeholders so that even if the field-level mask fails,
    these samples cannot teach the model to predict emergency_review / expert_review.
    """
    if case.get("task_type") != "public_binary" or not isinstance(case.get("label"), dict):
        return case
    label = dict(case["label"])
    judgment = label.get("event_judgment") or label.get("final_judgment")
    if judgment in {"risk_event", "exist_violation"}:
        label["risk_level"] = "mid_risk"
        label["event_judgment"] = "risk_event"
        label["recommended_action"] = "service_followup"
        label.pop("handling_suggestion", None)
        label.pop("final_judgment", None)
    else:
        label["risk_level"] = "low_risk"
        label["event_judgment"] = "not_risk_event"
        label["recommended_action"] = "information_reply"
        label["event_topic"] = "无风险事件"
        label.pop("handling_suggestion", None)
        label.pop("final_judgment", None)
        label.pop("topic", None)
    case["label"] = label
    return case


def _build_peft_config(train_cfg: dict[str, Any]):
    peft_cfg = train_cfg.get("peft", {})
    if not peft_cfg.get("enabled"):
        return None
    from peft import LoraConfig

    return LoraConfig(
        r=peft_cfg.get("r", 16),
        lora_alpha=peft_cfg.get("lora_alpha", 32),
        lora_dropout=peft_cfg.get("lora_dropout", 0.05),
        target_modules=peft_cfg.get("target_modules"),
        bias="none",
        task_type="CAUSAL_LM",
    )
