<div align="center">

# AI-IM-Guard-ML

**面向 IM 私聊风控技术交流的多证据审核工程实现**

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688)](https://fastapi.tiangolo.com/)
[![vLLM](https://img.shields.io/badge/Serving-vLLM-7c3aed)](https://github.com/vllm-project/vllm)
[![enterprise-check](https://github.com/NickWilde-AI/AI-IM-Guard-ML/actions/workflows/ci.yml/badge.svg)](https://github.com/NickWilde-AI/AI-IM-Guard-ML/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[English](README_EN.md) · [快速开始](#快速开始) · [系统架构](#系统架构) · [训练](#训练) · [企业级验收](#企业级验收) · [文档](#文档)

</div>

---

本仓库是基于企业 IM 风控项目整理的脱敏工程实现，重点展示数据处理、SFT 训练、离线评测、推理服务和风险策略链路。受数据安全、算力和公司代码权限限制，公开仓库不包含原始业务数据、生产模型权重及完整生产基础设施。

## 为什么做这个项目

很多内容安全系统只做一件事：判断文本是 `safe` 还是 `unsafe`。

真实的 IM 私聊风控要复杂得多。一个可落地的系统需要回答：

- 这段对话是否真的违规；
- 风险严重程度有多高；
- 应该忽略、警告、限流，还是进入封禁复核；
- 聊天语义和行为异常能不能互相印证；
- 这个判断如何审计、监控、回滚和持续改进。

AI-IM-Guard-ML 把这个问题拆成一个结构化、可评审、可复现的工程系统：

```text
IM 审核样本
  -> 聊天证据 + 行为证据
  -> LLM Judge
  -> 结构化风险结论
  -> 后处理保护
  -> 策略路由
  -> 审计 / 指标 / 样本回流
```

公开内容是可运行的工程骨架，不是原生产代码，也不是内部环境的完整镜像。使用者需要自行准备有权使用且已脱敏的数据、模型权重和运行环境。

## 项目亮点

| 能力 | 已实现内容 |
| --- | --- |
| 多证据审核 | 支持聊天文本、场景字段、行为异常和结构化标签 |
| LLM Judge | 支持本地规则基线 Judge，也支持 Transformers/SFT checkpoint 路径 |
| 训练链路 | completion-only SFT、LoRA/PEFT 配置、公开数据字段级 loss mask |
| 数据治理 | XGuard 公开数据接入、保守标签映射、数据拆分和质量审计 |
| 决策安全 | JSON 兜底解析、标签校验、强处置保护、策略路由 |
| API 服务 | FastAPI、request_id、Token/RBAC、CORS、限流、请求大小限制 |
| 审计追踪 | JSONL/SQLite 审计后端、ticket 查询、版本化决策记录 |
| 监控告警 | Prometheus 指标、漂移报告、滑动窗口告警、SLO 文档 |
| 模型治理 | 模型注册表、晋级红线、回滚目标、审批元数据 |
| 交付门禁 | `make enterprise-check`、OpenAPI 契约、preflight、readiness、CI |

## 当前状态

| 阶段 | 状态 | 说明 |
| --- | --- | --- |
| 工程框架 | 可公开验证 | CLI、API、数据转换、训练入口、评测、监控、审计和部署模板 |
| 规则基线 | 可公开验证 | 用于检查解析、路由和服务流程，不代表模型效果 |
| tiny-gpt2 | 工程冒烟配置 | 只验证训练代码路径，不代表中文 IM 风控效果 |
| Qwen SFT/LoRA | 代码与配置公开 | 需要使用者自备合规数据、权重和匹配的 GPU 环境 |
| 生产接入 | 不在公开范围 | 生产权重、内部数据和完整基础设施不公开 |

公开仓库不宣称能够直接复现内部生产指标，也不宣称示例配置已经完成特定规模模型的训练。

## 系统架构

为了避免 GitHub 上 Mermaid 图出现额外缩放控件，README 使用稳定的文本架构说明。更详细的系统设计见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

```text
审核请求
  -> 证据构建：聚合聊天、行为、场景信息
  -> Prompt/Feature 渲染：转换成模型可理解的输入
  -> LLM Judge：输出结构化审核 JSON
  -> JSON 解析：提取并修复模型输出
  -> 后处理保护：校验标签、保护强处置
  -> 策略路由：自动关闭、自动警告、策略动作或人审复核
  -> 审计与监控：记录 request_id、版本、指标和告警
  -> 样本回流：把误判和灰区样本用于下一轮训练
```

核心层级：

- **接入层**：请求处理、CLI、schema 校验。关键文件：`api.py`, `cli.py`, `schema.py`
- **证据层**：聊天和行为证据渲染。关键文件：`prompting.py`, `data_audit.py`
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

提交审核请求：

```bash
curl -X POST http://127.0.0.1:8000/judge \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: local-run-1" \
  -d '{
    "ticket_id": "local-run-1",
    "chat_evidence_list": ["加微信稳赚，带你投资。"],
    "behavior_abnormal_list": ["短时间高频私聊。"]
  }'
```

查看服务指标：

```bash
curl http://127.0.0.1:8000/metrics
```

## 输出协议

Judge 输出的是结构化审核结论，而不是单个二分类标签：

```json
{
  "risk_level": "low_risk | mid_risk | high_risk",
  "topic": "business risk topic",
  "correlation_analysis": "semantic-behavior evidence correlation",
  "final_judgment": "exist_violation | not_exist_violation",
  "judgment_basis": "decision basis with evidence references",
  "handling_suggestion": "ignore | warning | limit_account | ban_account",
  "route": "auto_close | auto_action | policy_action | human_review_required",
  "final_action": "ignore | send_warning | limit_account_candidate | review_before_ban"
}
```

高影响动作会被视为审核建议，而不是不可逆的最终处置。系统包含后处理保护和策略路由，避免模型输出被无脑执行。

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
- 公开数据字段 mask：公开二分类安全数据不训练 `risk_level` 和 `handling_suggestion`；
- 保守公开标签：公开违规样本最多映射到 `mid_risk / warning`；
- LoRA/PEFT：通过 YAML 配置开启；
- Qwen 风格 prompt：训练和推理使用一致的 prompt 渲染路径。

## 模型效果路线

工程链路已经跑通。下一步重点是模型效果，而不是继续堆功能。

| 步骤 | 目标 |
| --- | --- |
| 准备 GPU | 小模型 LoRA 建议至少 24GB 显存，7B 实验更建议 48GB/80GB |
| 固定验证集 | 保留稳定 `val/test`，避免指标被训练集污染 |
| 训练 Qwen checkpoint | 使用 `Qwen/Qwen2.5-7B-Instruct` 或更小的 Qwen LoRA baseline |
| 严格评测 | 报告 `final_judgment F1`、`risk_level macro-F1`、`handling macro-F1`、`ban_account FPR` |
| 误判分析 | 重点看误封、漏召、强处置误判和 `mid_risk` 灰区 |
| 回灌 hard cases | 把错误样本整理成 refinement 数据，再进入下一轮训练 |

公开 XGuard 数据适合补安全识别覆盖。`limit_account` 和 `ban_account` 这类强处置标签，应该来自人工审核过的 IM 类样本，而不是直接来自公开二分类数据。

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
├── src/im_guard_ml/         # 核心 Python 包
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

- 私有 IM 标注数据、申诉数据、人审工单和线上反馈样本；
- 经过正式训练和评测的 Qwen 或同级模型 checkpoint；
- 企业网关、密钥轮换系统、集中审计仓库和人审平台；
- 线上灰度、A/B 实验、回滚和持续监控流程。

部署文件只表示接口和拓扑参考，不证明公开仓库已经部署到生产环境或达到特定吞吐、延迟与可用性目标。

## License

MIT License. See [LICENSE](LICENSE).
