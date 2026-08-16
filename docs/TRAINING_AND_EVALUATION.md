# 训练与评测流程

本文档把数据构建、训练、离线评测、报告生成和上线前检查串成一条可复现流程。当前仓库支持生产化展示级流程；真实生产训练仍需要内部 IM 私聊、人审、申诉和线上回流样本。

## 1. 流程总览

```text
公开/内部/合成/难例数据
  -> 数据转换与保守标签映射
  -> 数据审计与去重
  -> train/val/test 拆分
  -> completion-only SFT / LoRA
  -> 离线预测
  -> 多字段评测与报告
  -> drift / window 异常检查
  -> 人审复核和灰度上线
```

核心原则：

- 公开二分类安全数据只作为安全识别底座，不训练 `limit_account` 或 `ban_account`。
- 强处置标签必须来自真实业务标注或人工审核过的内部样本。
- 训练集、验证集、测试集必须先去重再拆分，避免 payload 泄漏。
- 离线指标不能只看 accuracy，必须看 macro-F1、ban FPR、解析失败率和人审改判。

## 2. 数据来源与 task_type

| 来源 | `task_type` | 作用 | 处置标签策略 |
| --- | --- | --- | --- |
| 内部历史工单 | `internal` | 主体业务分布和真实处置边界 | 可训练完整三层标签 |
| 公开安全数据 | `public_binary` | 补安全识别和泛化 | 违规样本统一 `mid_risk / warning` |
| 合成样本 | `synthetic` | 补长尾主题和边界案例 | 需要规则审计或人工抽检 |
| hard case | `hard_case` | 回灌误判、灰区和事故样本 | 需要 committee 或人审确认 |

XGuard 公开数据说明见：[PUBLIC_DATASET_XGUARD.md](PUBLIC_DATASET_XGUARD.md)

## 3. 下载与转换公开数据

下载：

```bash
make download-xguard
```

转换为项目 JSONL 训练格式并拆分：

```bash
make build-xguard
```

等价命令：

```bash
PYTHONPATH=src python3 -m im_guard_ml.build_dataset \
  --public-xguard data/external/xguard_train_open_200k.jsonl \
  --out data/train/xguard_public_train.jsonl \
  --split-out-dir data/train/xguard_splits
```

输出：

- `data/train/xguard_public_train.jsonl`
- `data/train/xguard_splits/train.jsonl`
- `data/train/xguard_splits/val.jsonl`
- `data/train/xguard_splits/test.jsonl`

这些路径已加入 `.gitignore`，不提交大文件。

## 4. 合并多源训练数据

示例：

```bash
PYTHONPATH=src python3 -m im_guard_ml.build_dataset \
  --internal data/raw/history_tickets.jsonl \
  --internal data/raw/synthetic_cases.jsonl \
  --internal data/raw/refinement_cases.jsonl \
  --public-xguard data/external/xguard_train_open_200k.jsonl \
  --out data/train/im_audit_train.jsonl \
  --split-out-dir data/train/im_audit_splits
```

构建逻辑：

- 多源数据统一成 `audit_scene / chat_evidence_list / behavior_abnormal_list / label`。
- 对训练 payload 做 hash 去重。
- 对公开安全数据执行保守映射，避免污染强处置。
- 默认拆分比例为 `train=0.8 / val=0.1 / test=0.1`，随机种子为 `42`。

## 5. 数据审计

训练前必须执行：

```bash
make audit-xguard
```

或：

```bash
PYTHONPATH=src python3 -m im_guard_ml.cli --config configs/default.yaml \
  audit-data data/train/im_audit_train.jsonl \
  --eval-jsonl data/eval/internal_test.jsonl
```

审计项：

- 必填字段缺失
- 标签枚举错误
- 标签逻辑冲突
- `ticket_id` 重复
- payload 重复
- 训练/评测泄漏
- 公开数据强处置污染
- 邮箱、手机号、身份证等 PII 风险

上线前红线：

| 检查 | 红线 |
| --- | ---: |
| 标签非法 | `0` |
| 公开数据产生 `limit_account / ban_account` | `0` |
| 训练/评测 ID 泄漏 | `0` |
| 训练/评测 payload 泄漏 | `0` |
| 高风险 PII 未处理 | 必须脱敏或移除 |

## 6. 训练

安装训练依赖：

```bash
pip install -e ".[train]"
```

训练前先跑 readiness：

```bash
make train-readiness
```

或直接指定训练集：

```bash
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 \
im-guard --config configs/default.yaml train-readiness \
  data/train/xguard_splits/train.jsonl \
  --out outputs/training_readiness.json
```

`train-readiness` 会检查：

- 训练 JSONL 是否存在、是否有样本。
- `public_binary` 是否产生了 `limit_account / ban_account` 强处置污染。
- `torch / transformers / datasets / trl / peft` 等训练依赖是否安装。
- 当前环境是否有 CUDA/MPS/CPU，以及默认模型是否适合当前硬件。

启动 SFT：

```bash
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 \
im-guard --config configs/default.yaml train data/train/xguard_splits/train.jsonl
```

训练入口：[src/im_guard_ml/training.py](../src/im_guard_ml/training.py)

关键设置：

- completion-only SFT：只对 assistant JSON 输出算 loss。
- LoRA/PEFT：通过 `configs/default.yaml` 的 `training.peft` 开启。
- `enable_field_loss_mask`：保留字段级 loss mask 扩展能力。
- `bf16` 和 `gradient_checkpointing`：控制显存与吞吐。

当前默认 `configs/default.yaml` 使用公开可访问的 `Qwen/Qwen2.5-7B-Instruct`，完整 SFT 仍需要 GPU 训练环境。本地 Mac 或无 GPU 环境适合跑数据构建、审计、readiness 和小模型 smoke/full-pipeline run，不适合直接完成高质量 7B SFT。

本机 MPS LoRA 示例：

```bash
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 \
PYTHONPATH=src im-guard --config configs/local_mps_train.yaml \
  train data/train/xguard_splits/train.jsonl
```

该配置使用 `Qwen/Qwen2.5-0.5B-Instruct`，可以验证真实 Qwen 训练链路，但在 16GB Mac 上完整一轮约为几十小时级，更适合作为隔夜任务或迁移到 CUDA 机器。

本机快速完整链路训练：

```bash
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 \
PYTHONPATH=src im-guard --config configs/local_fast_full_train.yaml \
  train data/train/xguard_splits/train.jsonl
```

该配置使用 `sshleifer/tiny-gpt2` 跑完整训练集，目标是证明数据、tokenize、completion mask、TRL Trainer 和 checkpoint 保存链路可执行。它不是中文 IM 风控质量模型，不能用来宣称识别精度。

LoRA 示例：

```yaml
training:
  peft:
    enabled: true
    method: lora
    r: 16
    lora_alpha: 32
    lora_dropout: 0.05
```

## 7. 离线预测

启发式 demo：

```bash
make predict-route
```

使用 checkpoint：

```bash
PYTHONPATH=src im-guard --config configs/default.yaml predict \
  data/train/im_audit_splits/test.jsonl \
  --model-path outputs/im-audit-judge \
  --with-route \
  --with-version \
  --audit-log-out outputs/test_audit_logs.jsonl \
  --out outputs/test_predictions.jsonl
```

使用远程 API Judge：

```bash
export QWEN_API_KEY="replace-with-api-key"
PYTHONPATH=src im-guard --config configs/default.yaml predict \
  data/train/im_audit_splits/test.jsonl \
  --api \
  --api-model qwen-plus \
  --with-route \
  --with-version \
  --out outputs/test_predictions_api.jsonl
```

## 8. 评测与报告

评测：

```bash
PYTHONPATH=src im-guard --config configs/default.yaml eval outputs/test_predictions.jsonl
```

生成 Markdown 报告：

```bash
PYTHONPATH=src im-guard --config configs/default.yaml eval-report \
  outputs/test_predictions.jsonl \
  --out outputs/offline_eval_report.md
```

核心指标：

| 维度 | 指标 |
| --- | --- |
| 二分类违规判断 | accuracy、precision、recall、F1、FPR、AUPRC |
| 风险等级 | macro-F1、per-topic accuracy |
| 处置建议 | macro-F1、ban FPR、human review 改判率 |
| 生成质量 | JSON 解析失败率、fallback 率 |
| 数据稳定性 | PSI、drift report、窗口异常 |

## 9. 监控回放检查

滑动窗口异常：

```bash
PYTHONPATH=src im-guard --config configs/default.yaml window-alerts \
  outputs/test_predictions.jsonl \
  --window-size 100 \
  --step-size 50
```

drift 检测：

```bash
PYTHONPATH=src im-guard --config configs/default.yaml drift-report \
  outputs/test_predictions.jsonl \
  --baseline-pred-jsonl outputs/baseline_predictions.jsonl \
  --out outputs/drift_report.json
```

说明：

- `window-alerts` 用于发现局部时间段或批次内的处置比例异常。
- `drift-report` 用于比较当前结果和历史 baseline 的整体分布变化。
- 两者都不能替代线上 Prometheus 和日志平台，但适合回放验收。

## 10. 上线前检查

```bash
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 make enterprise-check
PYTHONPATH=src im-guard readiness-check --project-root . --out outputs/readiness_check.json
```

上线红线：

- `ban_account FPR <= 3%`。
- JSON 解析异常率低于 SLO。
- `ban_account` 占比没有异常尖峰。
- 公开数据没有强处置污染。
- 训练/评测没有 ID 或 payload 泄漏。
- 模型、prompt、rubric、feature schema、postprocess 版本都可追踪。
- `ban_account` 默认进入人审或策略复核，不直接自动执行。

## 11. 真实生产缺口

当前仓库已经能展示完整训练评测工程链路，但真实企业上线仍需要：

- 真实 IM 私聊、人审、申诉和客诉数据。
- 固定业务 eval set 和线上回流机制。
- 模型注册、审批和实验追踪平台。
- 多实例服务压测、网关限流和集中审计。
- 人审平台的改判、申诉和复盘闭环。
