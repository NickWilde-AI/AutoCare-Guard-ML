# XGuard 公开训练数据接入说明

## 数据集

- 名称：`Alibaba-AAIG/XGuard-Train-Open-200K`
- 来源：Hugging Face / ModelScope
- License：Apache-2.0
- 规模：200,000 条训练样本
- 本地路径：`data/external/xguard_train_open_200k.jsonl`

该数据集是中文 LLM safety guardrail 方向的公开训练数据，包含 `prompt`、`response`、`stage`、`label`、`explanation`、`policy` 等字段。它适合作为本项目的公开安全识别底座，但不等同于真实 IM 私聊风控数据。

## 下载

```bash
python3 scripts/download_xguard_dataset.py
```

脚本默认下载到 `data/external/xguard_train_open_200k.jsonl`。该目录已加入 `.gitignore`，完整数据只保存在本机。

## 标签映射

公开数据只用于训练文本安全识别能力，不训练强处置标签。

| XGuard label | 本项目 topic |
| --- | --- |
| `sec` | `无主题` |
| `pc` | `色情诱导` |
| `ec`, `fin` | `诈骗引流` |
| `dc`, `dw`, `ter` | `违禁品交易` |
| `ac`, `def`, `ti`, `cy` | `辱骂攻击` |
| `mh` | `自伤诱导` |
| `cm`, `ma`, `md` | `未成年保护` |
| `pi` | `版权侵犯` |
| `sd`, `ext` | `政治敏感` |
| 其他风险类 | `虚假信息` |

映射约束：

- `sec` 转为 `not_exist_violation / low_risk / ignore / 无主题`。
- 所有非 `sec` 样本转为 `exist_violation / mid_risk / warning`。
- 所有 XGuard 样本保留 `task_type=public_binary`。
- 公开数据不得产生 `limit_account` 或 `ban_account`。

## 转换与审计

```bash
PYTHONPATH=src python3 -m im_guard_ml.build_dataset \
  --public-xguard data/external/xguard_train_open_200k.jsonl \
  --out data/train/xguard_public_train.jsonl \
  --split-out-dir data/train/xguard_splits

PYTHONPATH=src python3 -m im_guard_ml.cli audit-data data/train/xguard_public_train.jsonl
```

转换过程会按项目训练载荷去重，保留首个样本，避免公开数据中的重复项污染训练和评测统计。

默认拆分比例为 `train=0.8 / val=0.1 / test=0.1`，随机种子为 `42`。拆分文件位于：

- `data/train/xguard_splits/train.jsonl`
- `data/train/xguard_splits/val.jsonl`
- `data/train/xguard_splits/test.jsonl`

数据审计会检查字段缺失、标签非法、重复样本、公开数据强处置泄漏，以及邮箱、手机号、身份证号等基础 PII 风险。

## 局限

XGuard 覆盖通用内容安全、LLM 输入输出安全和动态策略场景，但缺少本项目最关键的真实 IM 行为证据，例如亲密度、礼物金额、进房、关注、搜索、登录异常和人工复核结果。因此它适合做公开安全底座，不应被包装成真实业务训练集。
