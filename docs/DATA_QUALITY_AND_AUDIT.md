# 数据质量与审计

这份文档回答“训练前怎么保证数据可靠”。真实项目里，模型效果很多时候不是被算法限制，而是被脏数据、重复样本、标签冲突、测试集泄漏拖垮。

## 1. 数据审计目标

训练前至少检查：

- 必填字段是否完整。
- `label` 枚举是否合法。
- `final_judgment / risk_level / handling_suggestion` 是否逻辑一致。
- `ticket_id` 是否重复。
- 输入证据和标签是否完全重复。
- 公开二分类数据是否误注入重处置标签。
- 训练集和评测集是否存在 ID 或 payload 泄漏。
- `internal / public_binary / synthetic / hard_case` 等来源类型占比。
- `risk_level / final_judgment / handling_suggestion / topic` 分布是否严重偏斜。

## 2. 仓库实现

对应代码：[src/im_guard_ml/data_audit.py](../src/im_guard_ml/data_audit.py)

CLI：

```bash
PYTHONPATH=src python3 -m im_guard_ml.cli \
  --config configs/default.yaml \
  audit-data data/local/input.jsonl
```

如果要检查训练集和评测集泄漏：

```bash
PYTHONPATH=src python3 -m im_guard_ml.cli \
  --config configs/default.yaml \
  audit-data data/train/im_audit_train.jsonl \
  --eval-jsonl data/eval/internal_test.jsonl
```

`audit-data` 输出包含：

- `by_source`：原始 `source` 分布。
- `by_source_type`：归一后的来源类型分布，优先读取 `task_type`，否则根据 `source` 推断 `internal / public_binary / synthetic / hard_case`。
- `by_topic`、`by_risk_level`、`by_final_judgment`、`by_handling_suggestion`：标签分布。
- `distribution_warnings`：当大样本数据集中某个字段被单一取值严重支配时给出 warning，用于提醒重新抽样、分层拆分或单独构造评测集。
- `quality_status`：硬性质量门禁，字段缺失、标签非法、重复、公开数据强处置泄漏会返回 `fail`。

## 3. 质量红线

建议红线：

- 必填字段缺失：0。
- 标签枚举错误：0。
- `not_exist_violation + ban_account`：0。
- 训练/评测 `ticket_id` 重合：0。
- 训练/评测 payload 完全重复：0。
- 公开二分类数据进入 `limit_account / ban_account`：0。
- 训练集、验证集、测试集应分别检查类别分布，不能只看全量数据。
- 如果 `distribution_warnings` 提示某类标签占比过高，应解释采样原因或补充 hard case / minority class。

## 4. 使用原则

多源数据不能直接拼接后训练。应先检查 schema 完整性、标签逻辑、重复样本、来源占比、类别偏斜及训练/评测泄漏。公开二分类数据没有真实 handling 标签，不应参与强处置字段训练。
