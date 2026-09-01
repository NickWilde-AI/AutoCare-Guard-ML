# Local data

本仓库不包含真实售后工单、车主数据或内部测试集。请将已授权且脱敏的 JSONL 放在 `data/local/`（该目录被 Git 忽略）。

最小输入形态：

```json
{
  "case_id": "local-example-id",
  "conversation_evidence": [
    {"role": "owner", "text": "充电中闻到焦糊味，车机提示高压异常。"}
  ],
  "vehicle_signal_summary": {
    "motion_state": "charging",
    "warning_lights": ["高压系统告警"]
  },
  "fault_evidence": []
}
```

完整 schema 与评测流程见 `src/autocare_guard_ml/schema.py` 与 `docs/TRAINING_AND_EVALUATION.md`。
