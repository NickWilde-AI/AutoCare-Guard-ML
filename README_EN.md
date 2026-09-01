<div align="center">

# AI-IM-Guard-ML

**After-sales vehicle risk judgment and work-order routing (working name: AutoCare-Guard-ML)**

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688)](https://fastapi.tiangolo.com/)
[![vLLM](https://img.shields.io/badge/Serving-vLLM-7c3aed)](https://github.com/vllm-project/vllm)
[![enterprise-check](https://github.com/NickWilde-AI/AI-IM-Guard-ML/actions/workflows/ci.yml/badge.svg)](https://github.com/NickWilde-AI/AI-IM-Guard-ML/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[中文](README.md) · [Quick Start](#quick-start) · [Architecture](#architecture) · [Training](#training) · [Enterprise Checks](#enterprise-checks) · [Docs](#documentation)

</div>

---

This repository is a sanitized engineering implementation derived from a new-energy-vehicle after-sales risk judgment project (working name **AutoCare-Guard-ML**). The repository name `AI-IM-Guard-ML`, Python package `im_guard_ml`, and CLI `im-guard` keep historical naming. It focuses on data processing, SFT, offline evaluation, inference serving, and work-order routing. **It does not include** raw work orders, owner PII, fault-code dictionaries, production model weights, or the complete production infrastructure.

## Why This Exists

Many after-sales systems stop at text classification: consult / complaint / escalate.

Real vehicle risk judgment is messier. A production system needs to decide:

- whether the service conversation constitutes a vehicle risk event;
- how severe the risk is (low / mid / high);
- whether the right action is information reply, evidence collection, service follow-up, work-order creation, expert review, or emergency human confirmation;
- whether dialogue evidence and vehicle signals / fault evidence / service history support each other;
- how to avoid treating missing evidence as “normal”;
- how the decision is audited, monitored, rolled back, and improved.

This repository turns that problem into a structured, reviewable engineering system:

```text
Service case
  -> conversation + vehicle signals + fault evidence + service history
  -> LLM Judge
  -> structured judgment
  -> postprocess / evidence gates
  -> work-order routing
  -> audit / metrics / feedback loop
```

The public content is a runnable engineering skeleton, not the original production code. Users must supply authorized, redacted data, model weights, and suitable compute.

## Highlights

| Area | What is implemented |
| --- | --- |
| Multi-evidence judgment | Conversation, vehicle signal summaries, fault evidence, service history, structured labels |
| LLM Judge | Local rule-based baseline Judge plus Transformers/SFT checkpoint path |
| Training pipeline | Completion-only SFT, LoRA/PEFT config, public-data field loss masking |
| Data governance | Public dataset ingestion, conservative label mapping, split/audit checks |
| Decision safety | JSON parsing fallback, label validation, emergency-action evidence gates, policy routing |
| API service | FastAPI, request ID, token/RBAC auth, CORS, rate limits, request-size limits |
| Auditability | JSONL/SQLite audit backends, case/ticket lookup, versioned decisions |
| Monitoring | Prometheus metrics, drift reports, sliding-window alerts, SLO documentation |
| Model governance | Model registry, promotion guardrails, rollback target, approval metadata |
| Delivery gates | `make enterprise-check`, OpenAPI contract, preflight, readiness checks, CI |

## Current Status

| Stage | Status | Notes |
| --- | --- | --- |
| Engineering framework | Publicly verifiable | CLI, API, data conversion, training entry points, evaluation, monitoring, audit, and deployment templates |
| Heuristic baseline | Publicly verifiable | Validates parsing, routing, and serving only; it is not a model-quality result |
| tiny-gpt2 | Pipeline smoke configuration | Validates training code paths only; it does not represent after-sales judgment quality |
| Qwen SFT/LoRA | Code and configuration available | Requires authorized data, weights, and suitable GPU resources |
| Production integration | Outside the public scope | Production weights, internal data, and complete infrastructure are not public |

The public repository verifies the engineering loop. It does **not** claim to reproduce internal production metrics or a particular large-model training run. Model quality evaluation requires your own redacted data and weights.

## Architecture

Stable text pipeline:

```text
Service judgment request
  -> evidence builder (conversation, vehicle signals, faults, service history)
  -> prompt / feature rendering
  -> LLM Judge
  -> JSON parsing
  -> postprocess guardrails / evidence gates
  -> work-order routing
  -> audit store + metrics + feedback loop
```

Core layers:

- **Access**: request handling, CLI, schema validation. Key files: `api.py`, `cli.py`, `schema.py`
- **Evidence**: conversation / vehicle / fault evidence rendering. Key files: `prompting.py`, `data_audit.py`
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

Submit a judgment request (AutoCare fields; legacy `ticket_id` / `chat_evidence_list` remain compatible):

```bash
curl -X POST http://127.0.0.1:8000/judge \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: local-run-1" \
  -d '{
    "case_id": "local-run-1",
    "conversation_evidence": [
      {"role": "owner", "text": "Charging smell of burning; HV alert on the screen."}
    ],
    "vehicle_signal_summary": {
      "motion_state": "charging",
      "alert_summary": ["high_voltage_alert"],
      "thermal_status": "abnormal_rise"
    },
    "fault_evidence": [
      {"domain": "hv_system", "severity": "critical", "count": 2}
    ]
  }'
```

Check service metrics:

```bash
curl http://127.0.0.1:8000/metrics
```

## Output Contract

The Judge returns a structured judgment instead of a single binary label:

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

High-impact actions such as `emergency_review` are treated as review recommendations, not irreversible enforcement. The system includes vehicle-side evidence gates and routing so model output is not blindly executed; the model never controls the vehicle directly.

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
- public-data field masking: public binary safety data does not teach full `risk_level` / `recommended_action` (especially not `emergency_review` / `expert_review`);
- conservative public labels: public violations are capped at mid-risk and service-follow-up-style actions;
- LoRA/PEFT support: configured from YAML;
- Qwen-style prompt rendering: aligned with the inference path.

## Model-Effect Roadmap

The engineering loop is now working. The next step is model quality, not more feature stacking.

| Step | Goal |
| --- | --- |
| Rent GPU capacity | Unified config: Qwen3-32B LoRA multi-task SFT, prefer multi-GPU 80GB-class hardware; local smoke runs use tiny-gpt2 / Qwen2.5-0.5B |
| Fix validation data | Keep stable `val/test` splits so metrics are not inflated |
| Train Qwen checkpoint | Use `Qwen/Qwen3-32B` with LoRA multi-task SFT (r=16 / alpha=32 / q,k,v,o_proj / lr=1e-4 / 2 epochs / global batch 64) |
| Evaluate rigorously | Report `event_judgment` F1, `risk_level` macro-F1, `recommended_action` macro-F1, `emergency_review` FPR, critical-event recall |
| Analyze errors | Focus on false emergencies, missed risk events, strong-action mistakes, and `mid_risk` / `insufficient_evidence` gray cases |
| Feed back hard cases | Convert mistakes into refinement samples and rerun training |

Public safety data is useful for recognition coverage. Strong actions such as `expert_review` and `emergency_review` should come from reviewed after-sales / vehicle samples, not raw public binary safety data.

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
├── src/im_guard_ml/         # core Python package (historical name)
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

- private after-sales labels, work-order feedback, safety-review samples, and online feedback loops;
- a formally trained and evaluated Qwen or comparable model checkpoint;
- enterprise gateway, secret rotation, centralized audit warehouse, and human-review platform;
- online canary, A/B testing, rollback, and continuous monitoring workflows.

Deployment files are reference templates; they do not prove a production deployment or a particular throughput, latency, or availability target.

## License

MIT License. See [LICENSE](LICENSE).
