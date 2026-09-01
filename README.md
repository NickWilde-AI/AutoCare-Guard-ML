<div align="center">

# AI-IM-Guard-ML

**新能源汽车售后风险智能研判与工单路由（工作名 AutoCare-Guard-ML）**

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688)](https://fastapi.tiangolo.com/)
[![vLLM](https://img.shields.io/badge/Serving-vLLM-7c3aed)](https://github.com/vllm-project/vllm)
[![enterprise-check](https://github.com/NickWilde-AI/AI-IM-Guard-ML/actions/workflows/ci.yml/badge.svg)](https://github.com/NickWilde-AI/AI-IM-Guard-ML/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[English](README_EN.md) · [快速开始](#快速开始) · [系统架构](#系统架构) · [训练](#训练) · [企业级验收](#企业级验收) · [文档](#文档)

</div>

---

本仓库是基于新能源汽车售后风险研判项目整理的脱敏工程实现（工作名 **AutoCare-Guard-ML**）。仓库名 `AI-IM-Guard-ML`、Python 包 `im_guard_ml`、CLI `im-guard` 保留历史命名。公开内容覆盖数据处理、SFT 训练、离线评测、推理服务和工单路由策略链路；**不包含**原始工单、车主数据、故障码字典、生产模型权重及完整生产基础设施。

## 为什么做这个项目

很多售后系统只做一件事：把客服文本分成「咨询 / 投诉 / 升级」。

真实的车辆售后风险研判要复杂得多。一个可落地的系统需要回答：

- 这段服务对话是否构成车辆风险事件；
- 风险严重程度有多高（低 / 中 / 高）；
- 应该信息回复、补采证据、服务跟进、建工单、专家复核，还是紧急人工确认；
- 对话语义与车辆信号、故障证据、服务历史能否互相印证；
- 证据不足时如何避免当成「正常」；
- 这个判断如何审计、监控、回滚和持续改进。

本仓库把这个问题拆成结构化、可评审、可复现的工程系统：

```text
服务事件
  -> 对话证据 + 车辆信号摘要 + 故障证据 + 服务历史
  -> LLM Judge
  -> 结构化研判结论
  -> 后处理 / 证据门禁
  -> 工单路由
  -> 审计 / 指标 / 样本回流
```

公开内容是可运行的工程骨架，不是原生产代码。使用者需自行准备有权使用且已脱敏的数据、模型权重和运行环境。

## 项目亮点

| 能力 | 已实现内容 |
| --- | --- |
| 多证据研判 | 服务对话、车辆信号摘要、故障证据、服务历史与结构化标签 |
| LLM Judge | 本地规则基线 Judge，以及 Transformers/SFT checkpoint 路径 |
| 训练链路 | completion-only SFT、LoRA/PEFT 配置、公开数据字段级 loss mask |
| 数据治理 | 公开数据接入、保守标签映射、数据拆分和质量审计 |
| 决策安全 | JSON 兜底解析、标签校验、紧急动作证据门禁、策略路由 |
| API 服务 | FastAPI、request_id、Token/RBAC、CORS、限流、请求大小限制 |
| 审计追踪 | JSONL/SQLite 审计后端、case/ticket 查询、版本化决策记录 |
| 监控告警 | Prometheus 指标、漂移报告、滑动窗口告警、SLO 文档 |
| 模型治理 | 模型注册表、晋级红线、回滚目标、审批元数据 |
| 交付门禁 | `make enterprise-check`、OpenAPI 契约、preflight、readiness、CI |

## 当前状态

| 阶段 | 状态 | 说明 |
| --- | --- | --- |
| 工程框架 | 可公开验证 | CLI、API、数据转换、训练入口、评测、监控、审计和部署模板 |
| 规则基线 | 可公开验证 | 用于检查解析、路由和服务流程，不代表模型效果 |
| tiny-gpt2 | 工程冒烟配置 | 只验证训练代码路径，不代表售后研判效果 |
| Qwen SFT/LoRA | 代码与配置公开 | 需要使用者自备合规数据、权重和匹配的 GPU 环境 |
| 生产接入 | 不在公开范围 | 生产权重、内部数据和完整基础设施不公开 |

公开仓库可验证工程链路；**不宣称**能直接复现内部生产指标，也不宣称示例配置已完成特定规模模型训练。效果评估需自备脱敏数据与权重。

## 系统架构

为了避免 GitHub 上 Mermaid 图出现额外缩放控件，README 使用稳定的文本架构说明。更详细的系统设计见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

```text
服务研判请求
  -> 证据构建：聚合对话、车辆信号、故障、服务历史
  -> Prompt/Feature 渲染：转换成模型可理解的输入
  -> LLM Judge：输出结构化研判 JSON
  -> JSON 解析：提取并修复模型输出
  -> 后处理保护：校验标签、紧急动作证据门禁
  -> 工单路由：信息流、补采、服务队列、工单、复核队列或兜底
  -> 审计与监控：记录 request_id、版本、指标和告警
  -> 样本回流：把误判和灰区样本用于下一轮训练
```

核心层级：

- **接入层**：请求处理、CLI、schema 校验。关键文件：`api.py`, `cli.py`, `schema.py`
- **证据层**：对话 / 车辆 / 故障证据渲染。关键文件：`prompting.py`, `data_audit.py`
- **模型层**：本地规则基线、SFT 训练、checkpoint 推理。关键文件：`inference.py`, `training.py`
- **决策层**：JSON 修复、标签校验、动作路由。关键文件：`parsing.py`, `postprocess.py`
- **治理层**：版本、审计、监控、模型注册。关键文件：`versioning.py`, `audit_store.py`, `monitoring.py`, `model_registry.py`
- **闭环层**：离线评测和 hard case 回流。关键文件：`evaluation.py`, `refinement.py`

## 快速开始

本地快速启动不需要 GPU，也不需要微调 checkpoint。系统会使用确定性的本地规则基线 Judge 跑通完整工程链路，便于开发者立即验证 API、路由、审计、监控和评测流程。

```bash
git clone https://github.com/NickWilde-AI/AI-IM-Guard-ML.git
cd AI-IM-Guard-ML

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,serve]"

python -m pytest tests/ -q
python -m compileall -q src

# 准备本地脱敏 JSONL 后再运行：
make predict-route INPUT=data/local/input.jsonl
make eval-report INPUT=data/local/input.jsonl
make readiness-check
```

启动 API：

```bash
PYTHONPATH=src im-guard --config configs/default.yaml serve --port 8000
```

提交研判请求（AutoCare 字段；旧字段 `ticket_id` / `chat_evidence_list` 等仍兼容）：

```bash
curl -X POST http://127.0.0.1:8000/judge \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: local-run-1" \
  -d '{
    "case_id": "local-run-1",
    "conversation_evidence": [
      {"role": "owner", "text": "充电中闻到焦糊味，车机提示高压异常。"}
    ],
    "vehicle_signal_summary": {
      "motion_state": "charging",
      "alert_summary": ["高压系统告警"],
      "thermal_status": "abnormal_rise"
    },
    "fault_evidence": [
      {"domain": "hv_system", "severity": "critical", "count": 2}
    ]
  }'
```

查看服务指标：

```bash
curl http://127.0.0.1:8000/metrics
```

## 输出协议

Judge 输出的是结构化研判结论，而不是单个二分类标签：

```json
{
  "risk_level": "low_risk | mid_risk | high_risk",
  "event_topic": "vehicle risk topic",
  "event_judgment": "risk_event | not_risk_event | insufficient_evidence",
  "recommended_action": "information_reply | collect_more_evidence | service_followup | create_work_order | expert_review | emergency_review",
  "evidence_refs": [{"source": "conversation_evidence|vehicle_signal_summary|fault_evidence|...", "index": 0, "field": "..."}],
  "correlation_analysis": "dialogue-vehicle evidence correlation",
  "uncertainty_reason": "missing or conflicting evidence explanation",
  "service_escalation_flags": ["repeated_complaint | unresolved_service_case | public_opinion_risk"],
  "route": "information_flow | collect_evidence | service_queue | work_order_queue | review_queue | fallback_or_review",
  "final_action": "information_reply_candidate | request_more_evidence | ... | await_human_confirmation"
}
```

`emergency_review` 等高影响动作会被视为审核建议，而不是不可逆的最终处置。系统包含车辆侧证据门禁和策略路由，避免模型输出被无脑执行；模型不直接控车。

## 训练

安装训练依赖：

```bash
pip install -e ".[train]"
```

训练前检查：

```bash
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 \
PYTHONPATH=src im-guard --config configs/default.yaml \
  train-readiness data/train/xguard_splits/train.jsonl \
  --out outputs/training_readiness.json
```

快速跑完整训练链路：

```bash
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 \
PYTHONPATH=src im-guard --config configs/local_fast_full_train.yaml \
  train data/train/xguard_splits/train.jsonl
```

Mac MPS 上跑 Qwen LoRA：

```bash
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 \
PYTHONPATH=src im-guard --config configs/local_mps_train.yaml \
  train data/train/xguard_splits/train.jsonl
```

GPU 上跑 Qwen 效果训练：

```bash
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 \
PYTHONPATH=src im-guard --config configs/default.yaml \
  train data/train/xguard_splits/train.jsonl
```

训练设计：

- completion-only SFT：只对 assistant JSON 输出算 loss，不让模型背用户输入；
- 公开数据字段 mask：公开二分类安全数据不训练完整 `risk_level` / `recommended_action`（尤其不训练 `emergency_review` / `expert_review`）；
- 保守公开标签：公开违规样本最多映射到中等风险与服务跟进类动作；
- LoRA/PEFT：通过 YAML 配置开启；
- Qwen 风格 prompt：训练和推理使用一致的 prompt 渲染路径。

## 模型效果路线

工程链路已经跑通。下一步重点是模型效果，而不是继续堆功能。

| 步骤 | 目标 |
| --- | --- |
| 准备 GPU | 统一口径：Qwen3-32B LoRA 多任务 SFT，建议多卡 80GB 级 GPU；本地冒烟可用 tiny-gpt2 / Qwen2.5-0.5B |
| 固定验证集 | 保留稳定 `val/test`，避免指标被训练集污染 |
| 训练 Qwen checkpoint | 使用 `Qwen/Qwen3-32B` 做 LoRA 多任务 SFT（r=16 / alpha=32 / q,k,v,o_proj / lr=1e-4 / 2 Epoch / 全局 Batch 64） |
| 严格评测 | 报告 `event_judgment` F1、`risk_level` macro-F1、`recommended_action` macro-F1、`emergency_review` FPR、critical-event recall |
| 误判分析 | 重点看误紧急、漏召、强处置误判和 `mid_risk` / `insufficient_evidence` 灰区 |
| 回灌 hard cases | 把错误样本整理成 refinement 数据，再进入下一轮训练 |

公开安全数据适合补识别覆盖。`expert_review` 与 `emergency_review` 等强处置标签，应来自人工审核过的售后/车辆类样本，而不是直接来自公开二分类数据。

## 企业级验收

运行完整本地门禁：

```bash
make enterprise-check
```

门禁覆盖单元测试、源码编译、OpenAPI 契约、生产配置 preflight、模型注册表、交付摘要和 readiness 检查。

GitHub Actions 会在 push 和 pull request 时运行同一套检查。具体结果以当前提交对应的 CI 记录为准。

## 项目结构

```text
.
├── configs/                 # 模型、训练、注册表、灰度配置
├── data/                    # 本地数据目录；业务数据默认不提交
├── deploy/                  # Docker、vLLM、环境变量和部署示例
├── docs/                    # 架构、运维、训练、治理文档
├── scripts/                 # 数据下载和 API 压测脚本
├── src/im_guard_ml/         # 核心 Python 包（历史命名）
├── tests/                   # 单测、契约、readiness、治理测试
├── Makefile
├── pyproject.toml
└── README.md
```

## 文档

| 需求 | 入口 |
| --- | --- |
| 项目地图 | [docs/PROJECT_INDEX.md](docs/PROJECT_INDEX.md) |
| 架构说明 | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| 命令手册 | [docs/COMMANDS.md](docs/COMMANDS.md) |
| API 使用 | [docs/API_USAGE.md](docs/API_USAGE.md) |
| 训练与评测 | [docs/TRAINING_AND_EVALUATION.md](docs/TRAINING_AND_EVALUATION.md) |
| 公开数据集 | [docs/PUBLIC_DATASET_XGUARD.md](docs/PUBLIC_DATASET_XGUARD.md) |
| 生产化评审 | [docs/ENTERPRISE_READINESS_REVIEW.md](docs/ENTERPRISE_READINESS_REVIEW.md) |
| 部署与运维 | [docs/DEPLOYMENT_AND_OPERATIONS.md](docs/DEPLOYMENT_AND_OPERATIONS.md) |
| SLO 与告警 | [docs/SLO_AND_ALERTING.md](docs/SLO_AND_ALERTING.md) |
| 模型治理 | [docs/MODEL_GOVERNANCE_PLAYBOOK.md](docs/MODEL_GOVERNANCE_PLAYBOOK.md) |

## 生产接入说明

这个仓库包含公开数据接入、训练代码、API 服务、审计日志、监控、部署模板和治理检查。进入真实业务环境时，通常需要接入或替换：

- 私有售后标注数据、工单反馈、安全复核样本和线上回流样本；
- 经过正式训练和评测的 Qwen 或同级模型 checkpoint；
- 企业网关、密钥轮换系统、集中审计仓库和人工复核平台；
- 线上灰度、A/B 实验、回滚和持续监控流程。

部署文件只表示接口和拓扑参考，不证明公开仓库已经部署到生产环境或达到特定吞吐、延迟与可用性目标。

## License

MIT License. See [LICENSE](LICENSE).
