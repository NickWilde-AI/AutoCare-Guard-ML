<div align="center">

# AutoCare-Guard-ML

**AutoCare Risk Intelligence Platform** · 智能汽车服务风险决策平台

Fuse what the owner says with what the vehicle reported into one auditable Judge — structured risk conclusions and service routing recommendations.

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![vLLM](https://img.shields.io/badge/Serving-vLLM-111111)](https://github.com/vllm-project/vllm)
[![CI](https://github.com/NickWilde-AI/AutoCare-Guard-ML/actions/workflows/ci.yml/badge.svg)](https://github.com/NickWilde-AI/AutoCare-Guard-ML/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-MIT-2ea44f)](LICENSE)

[中文](README.md) · [Quick Start](#quick-start) · [Architecture](#architecture) · [Protocol](#output-protocol) · [Training](#training--evaluation) · [Docs](#documentation)

</div>

---

Sanitized engineering implementation of **AutoCare Risk Intelligence Platform** (智能汽车服务风险决策平台). Public repo: [AutoCare-Guard-ML](https://github.com/NickWilde-AI/AutoCare-Guard-ML). Package / CLI: `autocare_guard_ml` / `autocare-guard`. Covers multi-evidence datasets, Qwen LoRA SFT, offline eval, serving, evidence gates, work-order routing, audit, and monitoring.

> **Public boundary** — No raw tickets, owner PII, fault-code dictionaries, production weights, or full production infrastructure. Bring your own authorized, redacted data and weights to measure quality.

---

## Why It Exists

Most after-sales systems stop at text classification: inquiry / complaint / escalate.  
Real service risk decisions must answer five questions:

| Decision | Why it is hard |
| :--- | :--- |
| Is this a vehicle risk event? | “Cannot charge” may be a schedule setting or an HV alert with thermal rise |
| How severe is it? | Dialogue must correlate with vehicle signals, faults, and service history |
| What should happen next? | Reply → collect evidence → follow up → work order → expert review → emergency confirmation |
| What if evidence is insufficient? | Do not treat it as safe; use `insufficient_evidence` |
| How do we stay auditable? | Evidence refs, versioned decisions, alerts, and sample feedback |

```text
Service case
   │
   ▼
conversation + vehicle signals + faults + service history
   │
   ▼
LLM Judge  ──►  structured judgment JSON
   │
   ▼
postprocess / vehicle-side evidence gate
   │
   ▼
work-order routing  ──►  audit · metrics · feedback
```

---

## Highlights

| Area | What ships |
| :--- | :--- |
| Multi-evidence | conversation · vehicle signals · faults · service history |
| LLM Judge | rule baseline · Transformers / SFT · OpenAI-compatible API |
| Training | completion-only SFT · LoRA/PEFT · field-level loss masks |
| Decision safety | JSON repair · label validation · `emergency_review` gate |
| Serving & audit | FastAPI · request_id · Token/RBAC · JSONL/SQLite |
| Delivery | Prometheus · model registry · `make enterprise-check` |

---

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design.

```text
request → evidence → prompt → Judge → parse → postprocess → route → audit → feedback
```

---

## Quick Start

No GPU required for the local path. A deterministic rule baseline exercises the full pipeline.

```bash
git clone https://github.com/NickWilde-AI/AutoCare-Guard-ML.git
cd AutoCare-Guard-ML

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,serve]"

python -m pytest tests/ -q
make readiness-check
```

**Serve**

```bash
PYTHONPATH=src autocare-guard --config configs/default.yaml serve --port 8000
```

**Judge**

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

---

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

`emergency_review` is a human-confirmation recommendation. The model does **not** control the vehicle.

---

## Training & Evaluation

```bash
pip install -e ".[train]"

PYTHONPATH=src autocare-guard --config configs/default.yaml \
  train-readiness data/train/xguard_splits/train.jsonl \
  --out outputs/training_readiness.json

PYTHONPATH=src autocare-guard --config configs/default.yaml \
  train data/train/xguard_splits/train.jsonl
```

Recommended metrics: `event_judgment` F1 · `risk_level` macro-F1 · `recommended_action` macro-F1 · `emergency_review` FPR · critical-event recall.

---

## Enterprise Checks

```bash
make enterprise-check
```

Unit tests, compileall, OpenAPI contract, production preflight, model registry, delivery summary, readiness — also run in GitHub Actions.

---

## Documentation

| Topic | Doc |
| :--- | :--- |
| Map | [PROJECT_INDEX](docs/PROJECT_INDEX.md) |
| Architecture | [ARCHITECTURE](docs/ARCHITECTURE.md) |
| Commands | [COMMANDS](docs/COMMANDS.md) |
| API | [API_USAGE](docs/API_USAGE.md) |
| Training | [TRAINING_AND_EVALUATION](docs/TRAINING_AND_EVALUATION.md) |
| Rubrics | [RUBRIC_AND_LABELING_GUIDE](docs/RUBRIC_AND_LABELING_GUIDE.md) |
| Risk strategy | [RISK_STRATEGY](docs/RISK_STRATEGY.md) |
| Ops | [DEPLOYMENT_AND_OPERATIONS](docs/DEPLOYMENT_AND_OPERATIONS.md) |

---

<div align="center">

MIT License · [LICENSE](LICENSE)

</div>
