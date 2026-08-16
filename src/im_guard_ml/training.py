from __future__ import annotations

import json
import re
from typing import Any

from .prompting import INFER_TEMPLATE, render_assistant_label, render_user_prompt

# Regex to locate JSON field spans: captures "field_name": "field_value"
_FIELD_PATTERN = re.compile(
    r'"(risk_level|handling_suggestion)"\s*:\s*"[^"]*"'
)


def run_sft(config: dict[str, Any], dataset_name_or_path: str, rubrics: dict[str, str]) -> None:
    from datasets import load_dataset
    from transformers import AutoTokenizer
    from trl import SFTConfig, SFTTrainer
    from trl.trainer.sft_trainer import DataCollatorForLanguageModeling

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
    collator = DataCollatorForLanguageModeling(
        pad_token_id=tokenizer.pad_token_id,
        max_length=config["model"]["max_seq_length"],
        truncation_mode="keep_end",
        completion_only_loss=train_cfg.get("completion_only", True),
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


class FieldLevelMaskCollator:
    """Custom collator that masks loss on specific JSON fields for public_binary samples.

    For internal data (history_ticket, level_generator, refinement_hard): all tokens
    in the assistant response contribute to loss normally.

    For public_binary data: only final_judgment and text fields (topic,
    correlation_analysis, judgment_basis) contribute to loss. The risk_level and
    handling_suggestion field tokens are masked (label = -100) so that public data
    does not teach the model risk grading or handling routing.

    This is a two-layer defense:
      1. Label normalization (belt): public samples are capped at mid_risk/warning.
      2. Token-level masking (suspenders): even the capped labels are masked from loss
         so that public samples contribute zero gradient to risk/handling predictions.
    """

    IGNORE_INDEX = -100

    def __init__(self, response_template: str, tokenizer: Any, formatting_func: Any = None):
        self.response_template = response_template
        self.tokenizer = tokenizer
        self.formatting_func = formatting_func
        self._response_token_ids = tokenizer.encode(
            response_template, add_special_tokens=False
        )

    def __call__(self, features: list[dict[str, Any]]) -> dict[str, Any]:
        import torch

        batch_input_ids = []
        batch_attention_mask = []
        batch_labels = []

        for feature in features:
            input_ids = feature["input_ids"]
            attention_mask = feature.get("attention_mask", [1] * len(input_ids))
            is_public = feature.get("is_public_binary", False)

            # Build labels: mask prompt tokens (before response prefix)
            labels = list(input_ids)
            response_start = self._find_response_start(input_ids)
            for i in range(response_start):
                labels[i] = self.IGNORE_INDEX

            # For public_binary samples: additionally mask risk_level and
            # handling_suggestion field tokens within the response
            if is_public:
                self._mask_fields_in_response(
                    input_ids, labels, response_start
                )

            batch_input_ids.append(torch.tensor(input_ids, dtype=torch.long))
            batch_attention_mask.append(torch.tensor(attention_mask, dtype=torch.long))
            batch_labels.append(torch.tensor(labels, dtype=torch.long))

        return {
            "input_ids": torch.nn.utils.rnn.pad_sequence(
                batch_input_ids, batch_first=True, padding_value=self.tokenizer.pad_token_id
            ),
            "attention_mask": torch.nn.utils.rnn.pad_sequence(
                batch_attention_mask, batch_first=True, padding_value=0
            ),
            "labels": torch.nn.utils.rnn.pad_sequence(
                batch_labels, batch_first=True, padding_value=self.IGNORE_INDEX
            ),
        }

    def _find_response_start(self, input_ids: list[int]) -> int:
        """Find the token position right after the response template."""
        template_len = len(self._response_token_ids)
        for i in range(len(input_ids) - template_len + 1):
            if input_ids[i : i + template_len] == self._response_token_ids:
                return i + template_len
        return 0

    def _mask_fields_in_response(
        self, input_ids: list[int], labels: list[int], response_start: int
    ) -> None:
        """Mask tokens corresponding to risk_level and handling_suggestion fields."""
        # Decode the response portion to find field spans
        response_ids = input_ids[response_start:]
        response_text = self.tokenizer.decode(response_ids, skip_special_tokens=False)

        for match in _FIELD_PATTERN.finditer(response_text):
            # Find the character span of the matched field
            char_start, char_end = match.start(), match.end()
            # Map character positions back to token positions
            tok_start = self._char_to_token_pos(response_ids, char_start)
            tok_end = self._char_to_token_pos(response_ids, char_end)
            # Mask these tokens in labels
            for idx in range(response_start + tok_start, response_start + tok_end):
                if idx < len(labels):
                    labels[idx] = self.IGNORE_INDEX

    def _char_to_token_pos(self, token_ids: list[int], char_pos: int) -> int:
        """Map a character position in decoded text to a token index."""
        accumulated = 0
        for i, tid in enumerate(token_ids):
            token_text = self.tokenizer.decode([tid], skip_special_tokens=False)
            accumulated += len(token_text)
            if accumulated >= char_pos:
                return i + 1
        return len(token_ids)


def _normalize_public_binary_labels(case: dict[str, Any]) -> dict[str, Any]:
    """Cap public binary labels conservatively as a safety net.

    Public binary samples lack true risk_level and handling_suggestion annotations.
    We assign conservative placeholder values (mid_risk/warning for violations,
    low_risk/ignore for safe) so that even if the field-level mask fails, these
    samples cannot teach the model to predict ban_account or limit_account.

    The primary defense is tokenize_training_case, which writes a completion_mask
    that excludes risk_level and handling_suggestion tokens for public samples.
    This normalization is the secondary fallback.
    """
    if case.get("task_type") != "public_binary" or not isinstance(case.get("label"), dict):
        return case
    label = dict(case["label"])
    if label.get("final_judgment") == "exist_violation":
        label["risk_level"] = "mid_risk"
        label["handling_suggestion"] = "warning"
    else:
        label["risk_level"] = "low_risk"
        label["handling_suggestion"] = "ignore"
        label["topic"] = "无主题"
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
