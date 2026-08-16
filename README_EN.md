<div align="center">

# AI-IM-Guard-ML

**Sanitized multi-evidence engineering implementation for IM risk review**

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688)](https://fastapi.tiangolo.com/)
[![vLLM](https://img.shields.io/badge/Serving-vLLM-7c3aed)](https://github.com/vllm-project/vllm)
[![enterprise-check](https://github.com/NickWilde-AI/AI-IM-Guard-ML/actions/workflows/ci.yml/badge.svg)](https://github.com/NickWilde-AI/AI-IM-Guard-ML/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[中文](README.md) · [Quick Start](#quick-start) · [Architecture](#architecture) · [Training](#training) · [Enterprise Checks](#enterprise-checks) · [Docs](#documentation)

</div>

---

This repository is a sanitized engineering implementation derived from an enterprise IM risk-control project. It focuses on data processing, SFT, offline evaluation, inference serving, and policy routing. Raw business data, production weights, proprietary rules, and the complete production infrastructure are not included.

## Why This Exists

Many content-safety systems stop at a text classifier: `safe` or `unsafe`.

Real IM risk review is messier. A production system needs to decide:

- whether the conversation is actually violating policy;
- how severe the risk is;
- whether the right action is ignore, warning, limit, or ban review;
- whether chat evidence and behavior evidence support each other;
- how the decision is audited, monitored, rolled back, and improved.

AI-IM-Guard-ML turns that problem into a structured, reviewable engineering system:

```text
IM case
  -> chat evidence + behavior evidence
  -> LLM Judge
  -> structured risk output
  -> postprocess guardrails
  -> policy route
  -> audit / metrics / feedback loop
```

The public content is a runnable engineering skeleton, not the original production code or a complete replica of an internal environment. Users must supply authorized, redacted data, model weights, and suitable compute.

## Highlights

| Area | What is implemented |
| --- | --- |
| Multi-evidence review | Chat messages, scenario fields, behavior abnormalities, and structured labels |
| LLM Judge | Local rule-based baseline Judge plus Transformers/SFT checkpoint path |
| Training pipeline | Completion-only SFT, LoRA/PEFT config, public-data field loss masking |
| Data governance | XGuard public dataset ingestion, conservative label mapping, split/audit checks |
| Decision safety | JSON parsing fallback, label validation, strong-action guardrails, policy routing |
| API service | FastAPI, request ID, token/RBAC auth, CORS, rate limits, request-size limits |
| Auditability | JSONL/SQLite audit backends, ticket lookup, versioned decisions |
| Monitoring | Prometheus metrics, drift reports, sliding-window alerts, SLO documentation |
| Model governance | Model registry, promotion guardrails, rollback target, approval metadata |
| Delivery gates | `make enterprise-check`, OpenAPI contract, preflight, readiness checks, CI |

## Current Status

| Stage | Status | Notes |
| --- | --- | --- |
| Engineering framework | Publicly verifiable | CLI, API, data conversion, training entry points, evaluation, monitoring, audit, and deployment templates |
| Heuristic baseline | Publicly verifiable | Validates parsing, routing, and serving only; it is not a model-quality result |
| tiny-gpt2 | Pipeline smoke configuration | Validates training code paths only; it does not represent Chinese IM risk quality |
| Qwen SFT/LoRA | Code and configuration available | Requires authorized data, weights, and suitable GPU resources |
| Production integration | Outside the public scope | Production weights, internal data, and complete infrastructure are not public |

The repository does not claim to reproduce internal production metrics or a particular large-model training run.

## Architecture

Stable text pipeline:

```text
IM review request
  -> evidence builder
  -> prompt / feature rendering
  -> LLM Judge
  -> JSON parsing
  -> postprocess guardrails
  -> policy routing
  -> audit store + metrics + feedback loop
```

Core layers:

- **Access**: request handling, CLI, schema validation. Key files: `api.py`, `cli.py`, `schema.py`
- **Evidence**: chat and behavior evidence rendering. Key files: `prompting.py`, `data_audit.py`
- **Model**: local rule-based baseline, SFT training, checkpoint inference. Key files: `inference.py`, `training.py`
- **Decision**: JSON recovery, validation, action routing. Key files: `parsing.py`, `postprocess.py`
- **Governance**: versioning, audit, monitoring, registry. Key files: `versioning.py`, `audit_store.py`, `monitoring.py`, `model_registry.py`
- **Feedback**: evaluation and hard-case refinement. Key files: `evaluation.py`, `refinement.py`

## Quick Start

Local startup does not require a GPU or a fine-tuned checkpoint. The system uses a deterministic local baseline Judge to run the full engineering loop so developers can immediately validate API, routing, audit, monitoring, and evaluation flows.

```bash
git clone https://github.com/NickWilde-AI/AI-IM-Guard-ML.git
cd AI-IM-Guard-ML

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,serve]"

python -m pytest tests/ -q
python -m compileall -q src

# Run only after preparing a local redacted JSONL file:
make predict-route INPUT=data/local/input.jsonl
make eval-report INPUT=data/local/input.jsonl
make readiness-check
```

Run the API:

```bash
PYTHONPATH=src im-guard --config configs/default.yaml serve --port 8000
```

Submit a review request:

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

Check service metrics:

```bash
curl http://127.0.0.1:8000/metrics
```

## Output Contract

The Judge returns a structured review result instead of a single binary label:

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

High-impact actions are treated as review recommendations. The system includes postprocess guardrails and routing logic so model output is not blindly treated as irreversible enforcement.

## Training

Install training dependencies:

```bash
pip install -e ".[train]"
```

Run training readiness:

```bash
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 \
PYTHONPATH=src im-guard --config configs/default.yaml \
  train-readiness data/train/xguard_splits/train.jsonl \
  --out outputs/training_readiness.json
```

Run the fast full-pipeline training check:

```bash
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 \
PYTHONPATH=src im-guard --config configs/local_fast_full_train.yaml \
  train data/train/xguard_splits/train.jsonl
```

Run local Qwen LoRA training on Mac MPS:

```bash
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 \
PYTHONPATH=src im-guard --config configs/local_mps_train.yaml \
  train data/train/xguard_splits/train.jsonl
```

Run GPU-oriented Qwen training:

```bash
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 \
PYTHONPATH=src im-guard --config configs/default.yaml \
  train data/train/xguard_splits/train.jsonl
```

Training design:

- completion-only SFT: loss is applied to the assistant JSON output, not the user prompt;
- public-data field masking: public binary safety data does not teach `risk_level` or `handling_suggestion`;
- conservative public labels: public violations are capped at `mid_risk / warning`;
- LoRA/PEFT support: configured from YAML;
- Qwen-style prompt rendering: aligned with the inference path.

## Model-Effect Roadmap

The engineering loop is now working. The next step is model quality, not more feature stacking.

| Step | Goal |
| --- | --- |
| Rent GPU capacity | Use at least 24GB VRAM for small LoRA runs; prefer 48GB/80GB for 7B experiments |
| Fix validation data | Keep stable `val/test` splits so metrics are not inflated |
| Train Qwen checkpoint | Use `Qwen/Qwen2.5-7B-Instruct` or a smaller Qwen LoRA baseline |
| Evaluate rigorously | Report `final_judgment F1`, `risk_level macro-F1`, `handling macro-F1`, `ban_account FPR` |
| Analyze errors | Focus on false bans, missed violations, strong-action mistakes, and `mid_risk` gray cases |
| Feed back hard cases | Convert mistakes into refinement samples and rerun training |

Public XGuard data is useful for safety-recognition coverage. Strong actions such as `limit_account` and `ban_account` should come from reviewed IM-like samples, not raw public binary safety data.

## Enterprise Checks

Run the full local gate:

```bash
make enterprise-check
```

The gate covers unit tests, source compilation, OpenAPI contract validation, production preflight, model registry checks, delivery summary, and readiness checks.

GitHub Actions runs the same checks on push and pull request. Refer to the CI run for the current commit instead of a hard-coded result.

## Repository Layout

```text
.
├── configs/                 # model, training, registry, rollout configs
├── data/                    # local data; business data is not committed
├── deploy/                  # Docker, vLLM, env templates, deployment examples
├── docs/                    # architecture, operations, training, governance docs
├── scripts/                 # dataset download and API benchmark scripts
├── src/im_guard_ml/         # core Python package
├── tests/                   # unit, contract, readiness, and governance tests
├── Makefile
├── pyproject.toml
└── README.md
```

## Documentation

| Need | Start here |
| --- | --- |
| Project map | [docs/PROJECT_INDEX.md](docs/PROJECT_INDEX.md) |
| Architecture | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Commands | [docs/COMMANDS.md](docs/COMMANDS.md) |
| API usage | [docs/API_USAGE.md](docs/API_USAGE.md) |
| Training and evaluation | [docs/TRAINING_AND_EVALUATION.md](docs/TRAINING_AND_EVALUATION.md) |
| Public dataset | [docs/PUBLIC_DATASET_XGUARD.md](docs/PUBLIC_DATASET_XGUARD.md) |
| Production readiness | [docs/ENTERPRISE_READINESS_REVIEW.md](docs/ENTERPRISE_READINESS_REVIEW.md) |
| Deployment and operations | [docs/DEPLOYMENT_AND_OPERATIONS.md](docs/DEPLOYMENT_AND_OPERATIONS.md) |
| SLO and alerting | [docs/SLO_AND_ALERTING.md](docs/SLO_AND_ALERTING.md) |
| Model governance | [docs/MODEL_GOVERNANCE_PLAYBOOK.md](docs/MODEL_GOVERNANCE_PLAYBOOK.md) |

## Production Integration

This repository includes public-data ingestion, training code, API serving, audit logs, monitoring, deployment templates, and governance checks. For real business rollout, teams usually connect or replace:

- private IM labels, appeals, review tickets, and online feedback samples;
- a formally trained and evaluated Qwen or comparable model checkpoint;
- enterprise gateway, secret rotation, centralized audit warehouse, and human-review platform;
- online canary, A/B testing, rollback, and continuous monitoring workflows.

Deployment files are reference templates; they do not prove a production deployment or a particular throughput, latency, or availability target.

## License

MIT License. See [LICENSE](LICENSE).
