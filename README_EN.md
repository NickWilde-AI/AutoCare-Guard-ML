<div align="center">

# AutoCare-Guard-ML

**After-sales vehicle risk judgment and work-order routing for NEV service**

Combine what the owner says with what the vehicle reported into one auditable Judge, then emit structured risk conclusions and routing recommendations.

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688)](https://fastapi.tiangolo.com/)
[![vLLM](https://img.shields.io/badge/Serving-vLLM-7c3aed)](https://github.com/vllm-project/vllm)
[![enterprise-check](https://github.com/NickWilde-AI/AutoCare-Guard-ML/actions/workflows/ci.yml/badge.svg)](https://github.com/NickWilde-AI/AutoCare-Guard-ML/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[中文](README.md) · [Quick Start](#quick-start) · [Architecture](#architecture) · [Output Protocol](#output-protocol) · [Training](#training--evaluation) · [Enterprise Checks](#enterprise-checks) · [Docs](#documentation)

</div>

---

This repository is a sanitized engineering implementation of **AutoCare**: multi-evidence dataset building, Qwen LoRA SFT, offline evaluation, inference serving, evidence gates, work-order routing, audit, and monitoring.

**Public boundary**: no raw tickets, owner PII, fault-code dictionaries, production weights, or full production infrastructure. You must supply authorized, redacted data and weights to measure real quality.

## Why This Exists

Many after-sales systems stop at text classification: inquiry / complaint / escalate.

Real vehicle risk judgment must answer:

| Question | Why it is hard |
| --- | --- |
| Is this a vehicle risk event? | “Cannot charge” may be a schedule setting or an HV alert with thermal rise |
| How severe is it? | Dialogue must be correlated with vehicle signals, fault evidence, and service history |
| What should happen next? | Reply, collect more evidence, follow up, create a work order, expert review, or emergency human confirmation |
| What if evidence is insufficient? | Do not treat it as safe; route to `insufficient_evidence` |
| How do we stay auditable? | Structured evidence refs, versioned decisions, alerts, and sample feedback loops |

```text
Service case
  -> conversation + vehicle signal summary + fault evidence + service history
  -> LLM Judge
  -> structured judgment JSON
  -> postprocess / vehicle-side evidence gate
  -> work-order routing
  -> audit / metrics / sample feedback
```

## Highlights

| Capability | What is implemented |
| --- | --- |
| Multi-evidence judgment | conversation, vehicle signals, faults, service history |
| LLM Judge | deterministic rule baseline; Transformers / SFT; OpenAI-compatible API |
| Training | completion-only SFT, LoRA/PEFT, field-level loss masks for public data |
| Decision safety | JSON repair, label validation, `emergency_review` vehicle evidence gate |
| Serving | FastAPI, request_id, token/RBAC, CORS, rate limits, body size limits |
| Audit | JSONL / SQLite, case lookup, versioned decision records |
| Monitoring | Prometheus metrics, drift reports, sliding-window alerts |
| Governance | model registry, promotion guardrails, rollback targets |
| Delivery gate | `make enterprise-check`, OpenAPI contract, preflight, readiness, CI |

## Quick Start

No GPU and no fine-tuned checkpoint are required for the local path. A deterministic rule baseline Judge exercises the full pipeline.

```bash
git clone https://github.com/NickWilde-AI/AutoCare-Guard-ML.git
cd AutoCare-Guard-ML

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,serve]"

python -m pytest tests/ -q
make readiness-check
```

Start the API:

```bash
PYTHONPATH=src autocare-guard --config configs/default.yaml serve --port 8000
```

Submit a judgment request:

```bash
curl -X POST http://127.0.0.1:8000/judge \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: local-run-1" \
  -d '{
    "case_id": "local-run-1",
    "conversation_evidence": [
      {"role": "owner", "text": "Smell of burning while charging; HV warning on the HMI."}
    ],
    "vehicle_signal_summary": {
      "motion_state": "charging",
      "warning_lights": ["HV system warning"],
      "thermal_status": "abnormal_rise",
      "data_freshness": "fresh"
    },
    "fault_evidence": [
      {"fault_domain": "hv_system", "severity_from_source": "critical", "occurrence_count": 2}
    ]
  }'
```

## Output Protocol

```json
{
  "risk_level": "low_risk | mid_risk | high_risk",
  "event_topic": "vehicle risk topic",
  "event_judgment": "risk_event | not_risk_event | insufficient_evidence",
  "recommended_action": "information_reply | collect_more_evidence | service_followup | create_work_order | expert_review | emergency_review",
  "evidence_refs": [{"source": "conversation_evidence", "index": 0, "field": "text"}],
  "correlation_analysis": "how dialogue and vehicle evidence support or conflict",
  "uncertainty_reason": "why evidence is missing, conflicting, or insufficient",
  "service_escalation_flags": ["repeated_complaint", "unresolved_service_case", "public_opinion_risk"],
  "route": "information_flow | collect_evidence | service_queue | work_order_queue | review_queue | fallback_or_review",
  "final_action": "information_reply_candidate | request_more_evidence | ... | await_human_confirmation"
}
```

`emergency_review` is a recommendation for human confirmation. The model does not control the vehicle. Vehicle-side evidence gates protect high-impact actions.

## Training & Evaluation

```bash
pip install -e ".[train]"

PYTHONPATH=src autocare-guard --config configs/default.yaml \
  train-readiness data/train/xguard_splits/train.jsonl \
  --out outputs/training_readiness.json

PYTHONPATH=src autocare-guard --config configs/default.yaml \
  train data/train/xguard_splits/train.jsonl
```

Recommended metrics: `event_judgment` F1, `risk_level` macro-F1, `recommended_action` macro-F1, `emergency_review` FPR, critical-event recall.

Public binary safety data may enrich recognition coverage, but must not supervise `expert_review` / `emergency_review`.

## Enterprise Checks

```bash
make enterprise-check
```

Covers unit tests, compileall, OpenAPI contract, production preflight, model registry, delivery summary, and readiness. The same gate runs in GitHub Actions.

## Documentation

| Need | Doc |
| --- | --- |
| Map | [docs/PROJECT_INDEX.md](docs/PROJECT_INDEX.md) |
| Architecture | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Commands | [docs/COMMANDS.md](docs/COMMANDS.md) |
| API | [docs/API_USAGE.md](docs/API_USAGE.md) |
| Training | [docs/TRAINING_AND_EVALUATION.md](docs/TRAINING_AND_EVALUATION.md) |
| Rubrics | [docs/RUBRIC_AND_LABELING_GUIDE.md](docs/RUBRIC_AND_LABELING_GUIDE.md) |
| Risk strategy | [docs/RISK_STRATEGY.md](docs/RISK_STRATEGY.md) |
| Ops | [docs/DEPLOYMENT_AND_OPERATIONS.md](docs/DEPLOYMENT_AND_OPERATIONS.md) |

## License

MIT License. See [LICENSE](LICENSE).
