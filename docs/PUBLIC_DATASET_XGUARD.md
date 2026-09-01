# XGuard 公开训练数据接入说明

## 数据集

- 名称：`Alibaba-AAIG/XGuard-Train-Open-200K`
- 来源：Hugging Face / ModelScope
- License：Apache-2.0
- 规模：200,000 条训练样本
- 本地路径：`data/external/xguard_train_open_200k.jsonl`

该数据集是中文 LLM safety guardrail 方向的公开训练数据，包含 `prompt`、`response`、`stage`、`label`、`explanation`、`policy` 等字段。它适合作为本项目的**公开安全识别底座**，**不等于真实售后车辆风险样本**。

## 下载

```bash
python3 scripts/download_xguard_dataset.py
```

脚本默认下载到 `data/external/xguard_train_open_200k.jsonl`。该目录已加入 `.gitignore`，完整数据只保存在本机。

## 标签映射

公开数据只用于训练文本安全识别能力，不训练强处置标签。

| XGuard label | 本项目 event_topic（弱映射演示） |
| --- | --- |
| `sec` | `无风险事件` |
| `pc` / `ac` / `def` / `ti` / `cm` / `ma` / `md` / `pi` / `sd` / `ext` | `无风险事件` |
| `ec` / `fin` | `质保、零部件与服务争议` |
| `dc` / `dw` / `ter` / `mh` | `道路救援与人员安全` |
| `cy` | `车机、座舱和远程控车故障` |
| 其他风险类 | `质保、零部件与服务争议` |

映射约束：

- `sec` 转为 `not_risk_event / low_risk / information_reply / 无风险事件`。
- 所有非 `sec` 样本转为 `risk_event / mid_risk / service_followup`。
- 所有 XGuard 样本保留 `task_type=public_binary`。
- 公开数据不得产生 `expert_review` 或 `emergency_review`。

说明：上述主题映射仅为冷启动弱映射，不宣称 XGuard 类别与真实车辆故障主题等价。

## 转换与审计

```bash
PYTHONPATH=src python3 -m autocare_guard_ml.build_dataset \
  --public-xguard data/external/xguard_train_open_200k.jsonl \
  --out data/train/xguard_public_train.jsonl \
  --split-out-dir data/train/xguard_splits

PYTHONPATH=src python3 -m autocare_guard_ml.cli audit-data data/train/xguard_public_train.jsonl
```

转换过程会按项目训练载荷去重，保留首个样本，避免公开数据中的重复项污染训练和评测统计。

默认拆分比例为 `train=0.8 / val=0.1 / test=0.1`，随机种子为 `42`。拆分文件位于：

- `data/train/xguard_splits/train.jsonl`
- `data/train/xguard_splits/val.jsonl`
- `data/train/xguard_splits/test.jsonl`

数据审计会检查字段缺失、标签非法、重复样本、公开数据强处置泄漏，以及邮箱、手机号、身份证号等基础 PII 风险。

## 局限

XGuard 覆盖通用内容安全、LLM 输入输出安全和动态策略场景，但缺少本项目最关键的真实售后车辆证据，例如车辆信号摘要、故障证据、服务历史和人工复核结果。因此它适合做公开安全底座，不应被包装成真实售后车辆风险训练集。
