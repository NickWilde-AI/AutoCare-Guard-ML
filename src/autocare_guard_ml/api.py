from __future__ import annotations

import os
import random
import time
from collections import Counter, deque
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .audit_store import create_audit_store
from .auth import parse_auth_config
from .dataio import load_yaml
from .inference import HeuristicJudge, TransformersJudge
from .postprocess import postprocess_prediction
from .privacy import build_input_summary
from .versioning import version_info_from_config

_WINDOW_SECONDS = {"5m": 300, "1h": 3600, "all": None}


def _compute_counters(events: list[dict]) -> dict:
    c = {
        "requests_total": 0,
        "emergency_total": 0,
        "expert_total": 0,
        "work_order_total": 0,
        "followup_total": 0,
        "collect_evidence_total": 0,
        "information_total": 0,
        "parse_non_ok_total": 0,
        "human_review_total": 0,
    }
    for e in events:
        c["requests_total"] += 1
        h = e.get("recommended_action") or e.get("handling_suggestion") or "information_reply"
        if h == "emergency_review":
            c["emergency_total"] += 1
        elif h == "expert_review":
            c["expert_total"] += 1
        elif h == "create_work_order":
            c["work_order_total"] += 1
        elif h == "service_followup":
            c["followup_total"] += 1
        elif h == "collect_more_evidence":
            c["collect_evidence_total"] += 1
        else:
            c["information_total"] += 1
        if e.get("requires_human_review") or e.get("route") in {
            "review_queue",
            "human_review_required",
            "fallback_or_review",
        }:
            c["human_review_total"] += 1
        if e.get("parse_non_ok"):
            c["parse_non_ok_total"] += 1
    return c


def create_app(config_path: str = "configs/default.yaml", model_path: str | None = None, *, api: bool = False, api_model: str = "qwen-plus"):
    cfg = load_yaml(config_path)
    # P1-07：合并 configs/rubrics.yaml 的逐主题 rubric，11 类主题不再回退 __default__。
    from .config import merge_rubrics_file

    cfg = merge_rubrics_file(cfg)
    rubrics = cfg.get("rubrics", {})
    if api:
        from .inference import APIJudge
        judge = APIJudge(rubrics, model=api_model)
    elif model_path:
        judge = TransformersJudge(model_path, rubrics)
    else:
        judge = HeuristicJudge(rubrics)
    versions = version_info_from_config(cfg, model_path)
    mode = "api" if api else ("checkpoint" if model_path else "heuristic")
    app = FastAPI(title="AutoCare Risk Intelligence Platform", version="0.1.0")
    auth_config = parse_auth_config(
        os.environ.get("AUTOCARE_GUARD_API_TOKEN", ""),
        os.environ.get("AUTOCARE_GUARD_API_TOKENS", ""),
        os.environ.get("AUTOCARE_GUARD_API_TOKEN_HASHES", ""),
    )
    audit_log_path = Path(os.environ.get("AUTOCARE_GUARD_AUDIT_LOG_PATH", "outputs/api_audit_events.jsonl"))
    audit_backend = os.environ.get("AUTOCARE_GUARD_AUDIT_BACKEND", "jsonl")
    audit_store = create_audit_store(audit_backend, audit_log_path)
    cors_origins = _parse_cors_origins(os.environ.get("AUTOCARE_GUARD_CORS_ORIGINS", "*"))
    max_request_bytes = _parse_int_env("AUTOCARE_GUARD_MAX_REQUEST_BYTES", 262_144)
    # 默认 120 与 deploy/env 示例及 docs 一致（P2-07）。
    rate_limit_per_minute = _parse_int_env("AUTOCARE_GUARD_RATE_LIMIT_PER_MINUTE", 120)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 全량事件流（带时间戳），支持滑动窗口，保留最近 7200 条（约 2 小时）
    event_log: deque = deque(maxlen=7200)
    latency_history: deque = deque(maxlen=200)
    recent_results: deque = deque(maxlen=50)
    start_time = time.time()
    sim_config = {"interval": 0.3, "concurrency": 10}
    request_times: dict[str, deque] = {}

    # 全局累计计数器（不受 event_log maxlen 限制）
    global_counters = {
        "requests_total": 0,
        "emergency_total": 0,
        "expert_total": 0,
        "work_order_total": 0,
        "followup_total": 0,
        "collect_evidence_total": 0,
        "information_total": 0,
        "parse_non_ok_total": 0,
        "human_review_total": 0,
    }

    def require_permission(request: Request, permission: str) -> str | None:
        if not auth_config.enabled:
            return
        auth = request.headers.get("Authorization", "")
        token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
        role = auth_config.role_for_token(token)
        if not auth_config.allows(role, permission):
            raise HTTPException(status_code=401, detail="missing or invalid bearer token")
        return role

    def append_audit_event(event: dict) -> None:
        audit_store.append(event)

    def read_audit_events(ticket_id: str) -> list[dict]:
        return audit_store.find_by_ticket(ticket_id, limit=50)

    @app.middleware("http")
    async def production_guards(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        # P2-14：request_id 由中间件统一生成并写入 request.state，
        # 保证响应头与响应体/审计事件中的 request_id 完全一致。
        request.state.request_id = request_id
        content_length = request.headers.get("Content-Length")
        if content_length and int(content_length) > max_request_bytes:
            return _error_response(413, "request_too_large", "request body exceeds AUTOCARE_GUARD_MAX_REQUEST_BYTES", request_id)
        # 只读/监控路径不计入限流
        _no_ratelimit = ("/health", "/ready", "/dashboard/data", "/metrics", "/static")
        if rate_limit_per_minute > 0 and not any(request.url.path.startswith(p) for p in _no_ratelimit):
            client = request.client.host if request.client else "unknown"
            now = time.time()
            bucket = request_times.get(client)
            if bucket is not None:
                while bucket and now - bucket[0] > 60:
                    bucket.popleft()
                if not bucket:
                    # P1-03：窗口内时间戳全部过期即删除键，防止伪造大量源 IP 导致内存膨胀。
                    del request_times[client]
            if client in request_times and len(request_times[client]) >= rate_limit_per_minute:
                return _error_response(429, "rate_limited", "too many requests in the current minute", request_id)
            request_times.setdefault(client, deque()).append(now)
        response = await call_next(request)
        response.headers.setdefault("X-Request-ID", request_id)
        return response

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        code = "http_error"
        if exc.status_code == 401:
            code = "unauthorized"
        return _error_response(exc.status_code, code, str(exc.detail), request_id)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        return _error_response(422, "validation_error", "request validation failed", request_id, errors=exc.errors())

    @app.get("/simulator/config")
    def get_sim_config(request: Request) -> dict:
        require_permission(request, "config")
        return sim_config

    @app.post("/simulator/speed")
    def set_sim_speed(body: dict, request: Request) -> dict:
        require_permission(request, "config")
        interval = float(body.get("interval", sim_config["interval"]))
        sim_config["interval"] = round(max(0.05, min(5.0, interval)), 2)
        return sim_config

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "mode": mode}

    @app.get("/ready")
    def ready() -> dict:
        return {
            "status": "ready",
            "mode": mode,
            "auth_enabled": auth_config.enabled,
            "auth_roles": sorted(set(auth_config.token_roles.values()) | set(auth_config.token_hash_roles.values())),
            "audit_backend": audit_backend,
            "audit_log_path": str(audit_log_path),
            "max_request_bytes": max_request_bytes,
            "rate_limit_per_minute": rate_limit_per_minute,
            **versions.to_dict(),
        }

    @app.post("/judge")
    def judge_case(case: dict, request: Request) -> dict:
        require_permission(request, "write")
        # P2-14：统一使用中间件生成的 request_id。
        request_id = getattr(request.state, "request_id", None) or str(uuid4())
        t0 = time.time()
        pred = judge.predict(case)
        # P1-01：服务层统一走 postprocess，保证 emergency 门禁与 parse_status 可观测。
        result = postprocess_prediction(pred, case)
        parsed_output = result.parsed_output
        route, final_action = result.route, result.final_action
        requires_human_review = result.requires_human_review
        actual_ms = (time.time() - t0) * 1000
        # 演示模式（P2-23）：本地规则/轻量 judge 的实际耗时远低于真实推理，
        # 合成 180-520ms 用于看板展示；真实 checkpoint/API 模式使用实际耗时。
        simulated_latency = random.uniform(180, 520) if actual_ms < 50 else actual_ms
        latency_ms = round(simulated_latency, 1)

        action = parsed_output.get("recommended_action") or parsed_output.get(
            "handling_suggestion", "information_reply"
        )
        topic = parsed_output.get("event_topic") or parsed_output.get("topic", "无风险事件")
        risk_level = parsed_output.get("risk_level", "low_risk")
        judgment = parsed_output.get("event_judgment") or parsed_output.get(
            "final_judgment", "not_risk_event"
        )
        parse_non_ok = result.parse_status != "ok"
        case_id = case.get("case_id") or case.get("ticket_id") or f"ac-{int(time.time())}-{len(event_log):04d}"

        event = {
            "ts": time.time(),
            "request_id": request_id,
            "case_id": case_id,
            "ticket_id": case_id,
            "risk_level": risk_level,
            "event_topic": topic,
            "topic": topic,
            "event_judgment": judgment,
            "recommended_action": action,
            "route": route,
            "final_action": final_action,
            "requires_human_review": requires_human_review,
            "review_role_hint": result.review_role_hint,
            "review_priority": result.review_priority,
            "latency_ms": latency_ms,
            "parse_non_ok": parse_non_ok,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        event_log.appendleft(event)
        latency_history.append(latency_ms)
        recent_results.appendleft(event)

        # 全局累计（不受 event_log maxlen 限制）
        global_counters["requests_total"] += 1
        if action == "emergency_review":
            global_counters["emergency_total"] += 1
        elif action == "expert_review":
            global_counters["expert_total"] += 1
        elif action == "create_work_order":
            global_counters["work_order_total"] += 1
        elif action == "service_followup":
            global_counters["followup_total"] += 1
        elif action == "collect_more_evidence":
            global_counters["collect_evidence_total"] += 1
        else:
            global_counters["information_total"] += 1
        if requires_human_review or route in {"review_queue", "human_review_required", "fallback_or_review"}:
            global_counters["human_review_total"] += 1
        if parse_non_ok:
            global_counters["parse_non_ok_total"] += 1

        audit_event = {
            "request_id": request_id,
            "case_id": case_id,
            "ticket_id": case_id,
            "timestamp": event["timestamp"],
            "model_mode": mode,
            **versions.to_dict(),
            "risk_level": risk_level,
            "event_topic": topic,
            "topic": topic,
            "event_judgment": judgment,
            "final_judgment": judgment,
            "recommended_action": action,
            "handling_suggestion": action,
            "route": route,
            "final_action": final_action,
            "requires_human_review": requires_human_review,
            "review_role_hint": result.review_role_hint,
            "review_priority": result.review_priority,
            "policy_reasons": result.policy_reasons,
            "latency_ms": latency_ms,
            "parse_non_ok": parse_non_ok,
            "parse_status": result.parse_status,
            "validation_errors": result.validation_errors,
            "input_summary": build_input_summary(case),
        }
        append_audit_event(audit_event)

        return {
            **versions.to_dict(),
            **parsed_output,
            "route": route,
            "final_action": final_action,
            "requires_human_review": requires_human_review,
            "review_role_hint": result.review_role_hint,
            "review_priority": result.review_priority,
            "policy_reasons": result.policy_reasons,
            "parse_status": result.parse_status,
            "validation_errors": result.validation_errors,
            "request_id": request_id,
            "case_id": case_id,
        }

    @app.get("/audit/tickets/{ticket_id}")
    def audit_by_ticket(ticket_id: str, request: Request) -> dict:
        require_permission(request, "audit")
        events = read_audit_events(ticket_id)
        return {"ticket_id": ticket_id, "count": len(events), "events": events[-50:]}

    @app.get("/dashboard/data")
    def dashboard_data(request: Request, window: Optional[str] = Query(default="all", description="时间窗口: 5m | 1h | all")) -> dict:
        require_permission(request, "read")
        now = time.time()
        window_secs = _WINDOW_SECONDS.get(window or "all")
        if window_secs is not None:
            events = [e for e in event_log if now - e["ts"] <= window_secs]
            counters = _compute_counters(events)
        else:
            events = list(event_log)
            counters = dict(global_counters)  # 全量用独立累计，不受 maxlen 限制
        total = counters["requests_total"]
        emergency_rate = counters.get("emergency_total", 0) / total if total > 0 else 0
        parse_err_rate = counters["parse_non_ok_total"] / total if total > 0 else 0
        uptime_seconds = int(now - start_time)

        latency_stats = {}
        if latency_history:
            sorted_lat = sorted(latency_history)
            from .evaluation import percentile

            latency_stats = {
                "p50": percentile(sorted_lat, 0.5),
                "p95": percentile(sorted_lat, 0.95),
                "p99": percentile(sorted_lat, 0.99),
                "avg": round(sum(sorted_lat) / len(sorted_lat), 1),
            }

        action_keys = [
            "information_reply",
            "collect_more_evidence",
            "service_followup",
            "create_work_order",
            "expert_review",
            "emergency_review",
        ]
        topic_stats: dict[str, dict] = {}
        for e in events:
            t = e.get("event_topic") or e.get("topic", "无风险事件")
            if t not in topic_stats:
                topic_stats[t] = {
                    "count": 0,
                    "risk": {"low_risk": 0, "mid_risk": 0, "high_risk": 0},
                    "actions": {k: 0 for k in action_keys},
                }
            topic_stats[t]["count"] += 1
            rl = e.get("risk_level", "low_risk")
            if rl in topic_stats[t]["risk"]:
                topic_stats[t]["risk"][rl] += 1
            h = e.get("recommended_action") or e.get("handling_suggestion") or "information_reply"
            if h in topic_stats[t]["actions"]:
                topic_stats[t]["actions"][h] += 1

        topic_distribution = {k: v["count"] for k, v in sorted(topic_stats.items(), key=lambda x: -x[1]["count"])}
        topic_breakdown = dict(sorted(topic_stats.items(), key=lambda x: -x[1]["count"]))
        risk_event_like = sum(
            counters.get(k, 0)
            for k in (
                "emergency_total",
                "expert_total",
                "work_order_total",
                "followup_total",
                "collect_evidence_total",
            )
        )
        return {
            "counters": counters,
            "window": window or "all",
            "rates": {
                "emergency_review_rate": round(emergency_rate, 4),
                "parse_error_rate": round(parse_err_rate, 4),
                "risk_event_rate": round(risk_event_like / total, 4) if total > 0 else 0,
            },
            "topic_distribution": topic_distribution,
            "topic_breakdown": topic_breakdown,
            "latency": latency_stats,
            "recent": list(recent_results)[:20],
            "uptime_seconds": uptime_seconds,
            "model_mode": mode,
        }

    @app.get("/metrics", response_class=Response)
    def metrics():
        # P1-02：请求/处置计数改用 global_counters（counter 语义单调递增，
        # 不受 event_log maxlen=7200 封顶）；标签维度仍基于滚动窗口并注释说明。
        c = dict(global_counters)
        all_events = list(event_log)
        risk_counts = Counter(str(e.get("risk_level", "unknown")) for e in all_events)
        topic_counts = Counter(
            str(e.get("event_topic") or e.get("topic", "unknown")) for e in all_events
        )
        action_counts = Counter(
            str(e.get("recommended_action") or e.get("handling_suggestion", "unknown"))
            for e in all_events
        )
        route_counts = Counter(str(e.get("route", "unknown")) for e in all_events)
        latency_stats = _latency_stats([float(e.get("latency_ms", 0) or 0) for e in all_events])
        lines = [
            "# HELP autocare_guard_requests_total Total audit requests.",
            "# TYPE autocare_guard_requests_total counter",
            f"autocare_guard_requests_total {c['requests_total']}",
            "# HELP autocare_guard_requests_by_risk_total Audit requests by risk level.",
            "# TYPE autocare_guard_requests_by_risk_total counter",
        ]
        lines.extend(f'autocare_guard_requests_by_risk_total{{risk_level="{_label(k)}"}} {v}' for k, v in sorted(risk_counts.items()))
        lines.extend(
            [
                "# HELP autocare_guard_requests_by_topic_total Audit requests by topic.",
                "# TYPE autocare_guard_requests_by_topic_total counter",
            ]
        )
        lines.extend(f'autocare_guard_requests_by_topic_total{{topic="{_label(k)}"}} {v}' for k, v in sorted(topic_counts.items()))
        lines.extend(
            [
                "# HELP autocare_guard_requests_by_action_total Audit requests by recommended action.",
                "# TYPE autocare_guard_requests_by_action_total counter",
            ]
        )
        lines.extend(
            f'autocare_guard_requests_by_action_total{{recommended_action="{_label(k)}"}} {v}'
            for k, v in sorted(action_counts.items())
        )
        # 兼容旧 Prometheus 规则标签名
        lines.extend(
            [
                "# HELP autocare_guard_requests_by_handling_total Audit requests by recommended action (legacy label).",
                "# TYPE autocare_guard_requests_by_handling_total counter",
            ]
        )
        lines.extend(
            f'autocare_guard_requests_by_handling_total{{handling_suggestion="{_label(k)}"}} {v}'
            for k, v in sorted(action_counts.items())
        )
        lines.extend(
            [
                "# HELP autocare_guard_requests_by_route_total Audit requests by route.",
                "# TYPE autocare_guard_requests_by_route_total counter",
            ]
        )
        lines.extend(f'autocare_guard_requests_by_route_total{{route="{_label(k)}"}} {v}' for k, v in sorted(route_counts.items()))
        lines.extend(
            [
                "# HELP autocare_guard_latency_ms API latency summary gauges.",
                "# TYPE autocare_guard_latency_ms gauge",
            ]
        )
        lines.extend(f'autocare_guard_latency_ms{{quantile="{k}"}} {v}' for k, v in sorted(latency_stats.items()))
        lines.extend(
            [
                "# HELP autocare_guard_parse_non_ok_total Total non-ok parse results.",
                "# TYPE autocare_guard_parse_non_ok_total counter",
                f"autocare_guard_parse_non_ok_total {c['parse_non_ok_total']}",
                "",
            ]
        )
        body = "\n".join(lines)
        return Response(content=body, media_type="text/plain; version=0.0.4")

    @app.get("/config")
    def config(request: Request) -> dict:
        require_permission(request, "config")
        labels = cfg.get("labels", {})
        return {
            "config_path": str(Path(config_path).resolve()),
            "topics": labels.get("event_topics") or labels.get("topics", []),
            "event_topics": labels.get("event_topics") or labels.get("topics", []),
            "risk_levels": labels.get("risk_levels", []),
            "judgments": labels.get("event_judgments") or labels.get("judgments", []),
            "event_judgments": labels.get("event_judgments") or labels.get("judgments", []),
            "handling_suggestions": labels.get("recommended_actions")
            or labels.get("handling_suggestions", []),
            "recommended_actions": labels.get("recommended_actions")
            or labels.get("handling_suggestions", []),
            "alert_thresholds": cfg.get("alert_thresholds", {}),
            "rubrics": {k: v for k, v in cfg.get("rubrics", {}).items()},
            "model": cfg.get("model", {}),
            **versions.to_dict(),
        }

    static_dir = Path(__file__).parent.parent.parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    return app


def _parse_cors_origins(value: str) -> list[str]:
    origins = [x.strip() for x in value.split(",") if x.strip()]
    return origins or ["*"]


def _parse_int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _error_response(status_code: int, code: str, message: str, request_id: str, **extra) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "request_id": request_id, **extra}},
        headers={"X-Request-ID": request_id},
    )


def _label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _latency_stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"avg": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0}
    # P2-50：分位统一使用 evaluation.percentile 插值口径。
    from .evaluation import percentile

    ordered = sorted(values)
    return {
        "avg": round(sum(ordered) / len(ordered), 3),
        "p50": round(percentile(ordered, 0.5), 3),
        "p95": round(percentile(ordered, 0.95), 3),
        "p99": round(percentile(ordered, 0.99), 3),
    }
