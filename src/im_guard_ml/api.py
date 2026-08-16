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
from .postprocess import route_policy
from .privacy import build_input_summary
from .versioning import version_info_from_config

_WINDOW_SECONDS = {"5m": 300, "1h": 3600, "all": None}


def _compute_counters(events: list[dict]) -> dict:
    c = {"requests_total": 0, "ban_total": 0, "limit_total": 0,
         "warning_total": 0, "ignore_total": 0, "parse_non_ok_total": 0,
         "human_review_total": 0}
    for e in events:
        c["requests_total"] += 1
        h = e.get("handling_suggestion", "ignore")
        if h == "ban_account":
            c["ban_total"] += 1
        elif h == "limit_account":
            c["limit_total"] += 1
        elif h == "warning":
            c["warning_total"] += 1
        else:
            c["ignore_total"] += 1
        if e.get("route") == "human_review_required":
            c["human_review_total"] += 1
        if e.get("parse_non_ok"):
            c["parse_non_ok_total"] += 1
    return c


def create_app(config_path: str = "configs/default.yaml", model_path: str | None = None, *, api: bool = False, api_model: str = "qwen-plus"):
    cfg = load_yaml(config_path)
    rubrics = cfg.get("rubrics", {})
    if api:
        from .inference import APIJudge
        judge = APIJudge(rubrics, model=api_model)
    elif model_path:
        judge = TransformersJudge(model_path, rubrics)
    else:
        judge = HeuristicJudge(rubrics)
    versions = version_info_from_config(cfg, model_path)
    mode = "api" if api else ("checkpoint" if model_path else "heuristic-demo")
    app = FastAPI(title="AI IM Guard ML", version="0.1.0")
    auth_config = parse_auth_config(
        os.environ.get("IM_GUARD_API_TOKEN", ""),
        os.environ.get("IM_GUARD_API_TOKENS", ""),
        os.environ.get("IM_GUARD_API_TOKEN_HASHES", ""),
    )
    audit_log_path = Path(os.environ.get("IM_GUARD_AUDIT_LOG_PATH", "outputs/api_audit_events.jsonl"))
    audit_backend = os.environ.get("IM_GUARD_AUDIT_BACKEND", "jsonl")
    audit_store = create_audit_store(audit_backend, audit_log_path)
    cors_origins = _parse_cors_origins(os.environ.get("IM_GUARD_CORS_ORIGINS", "*"))
    max_request_bytes = _parse_int_env("IM_GUARD_MAX_REQUEST_BYTES", 262_144)
    rate_limit_per_minute = _parse_int_env("IM_GUARD_RATE_LIMIT_PER_MINUTE", 600)

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
        "requests_total": 0, "ban_total": 0, "limit_total": 0,
        "warning_total": 0, "ignore_total": 0, "parse_non_ok_total": 0,
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
        content_length = request.headers.get("Content-Length")
        if content_length and int(content_length) > max_request_bytes:
            return _error_response(413, "request_too_large", "request body exceeds IM_GUARD_MAX_REQUEST_BYTES", request_id)
        # 只读/监控路径不计入限流
        _no_ratelimit = ("/health", "/ready", "/dashboard/data", "/metrics", "/static")
        if rate_limit_per_minute > 0 and not any(request.url.path.startswith(p) for p in _no_ratelimit):
            client = request.client.host if request.client else "unknown"
            now = time.time()
            bucket = request_times.setdefault(client, deque())
            while bucket and now - bucket[0] > 60:
                bucket.popleft()
            if len(bucket) >= rate_limit_per_minute:
                return _error_response(429, "rate_limited", "too many requests in the current minute", request_id)
            bucket.append(now)
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
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        t0 = time.time()
        pred = judge.predict(case)
        route, final_action = route_policy(pred, case)
        actual_ms = (time.time() - t0) * 1000
        simulated_latency = random.uniform(180, 520) if actual_ms < 50 else actual_ms
        latency_ms = round(simulated_latency, 1)

        handling = pred.get("handling_suggestion", "ignore")
        topic = pred.get("topic", "无主题")
        risk_level = pred.get("risk_level", "low_risk")
        parse_non_ok = pred.get("parse_status") not in (None, "ok")

        event = {
            "ts": time.time(),
            "request_id": request_id,
            "ticket_id": case.get("ticket_id", f"im-{int(time.time())}-{len(event_log):04d}"),
            "risk_level": risk_level,
            "topic": topic,
            "handling_suggestion": handling,
            "route": route,
            "final_action": final_action,
            "latency_ms": latency_ms,
            "parse_non_ok": parse_non_ok,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        event_log.appendleft(event)
        latency_history.append(latency_ms)
        recent_results.appendleft(event)

        # 全局累计（不受 event_log maxlen 限制）
        global_counters["requests_total"] += 1
        if handling == "ban_account": global_counters["ban_total"] += 1
        elif handling == "limit_account": global_counters["limit_total"] += 1
        elif handling == "warning": global_counters["warning_total"] += 1
        else: global_counters["ignore_total"] += 1
        if route == "human_review_required": global_counters["human_review_total"] += 1
        if parse_non_ok: global_counters["parse_non_ok_total"] += 1

        audit_event = {
            "request_id": request_id,
            "ticket_id": event["ticket_id"],
            "timestamp": event["timestamp"],
            "model_mode": mode,
            **versions.to_dict(),
            "risk_level": risk_level,
            "topic": topic,
            "final_judgment": pred.get("final_judgment", "not_exist_violation"),
            "handling_suggestion": handling,
            "route": route,
            "final_action": final_action,
            "latency_ms": latency_ms,
            "parse_non_ok": parse_non_ok,
            "input_summary": build_input_summary(case),
        }
        append_audit_event(audit_event)

        return {**versions.to_dict(), **pred, "route": route, "final_action": final_action, "request_id": request_id}

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
        ban_rate = counters["ban_total"] / total if total > 0 else 0
        parse_err_rate = counters["parse_non_ok_total"] / total if total > 0 else 0
        uptime_seconds = int(now - start_time)

        latency_stats = {}
        if latency_history:
            sorted_lat = sorted(latency_history)
            n = len(sorted_lat)
            latency_stats = {
                "p50": sorted_lat[int(n * 0.5)],
                "p95": sorted_lat[min(int(n * 0.95), n - 1)],
                "p99": sorted_lat[min(int(n * 0.99), n - 1)],
                "avg": round(sum(sorted_lat) / n, 1),
            }

        # 主题下钻：每个主题的 risk_level 分布 + handling 分布
        topic_stats: dict[str, dict] = {}
        for e in events:
            t = e.get("topic", "无主题")
            if t not in topic_stats:
                topic_stats[t] = {
                    "count": 0,
                    "risk": {"low_risk": 0, "mid_risk": 0, "high_risk": 0},
                    "handling": {"ignore": 0, "warning": 0, "limit_account": 0, "ban_account": 0},
                }
            topic_stats[t]["count"] += 1
            rl = e.get("risk_level", "low_risk")
            if rl in topic_stats[t]["risk"]:
                topic_stats[t]["risk"][rl] += 1
            h = e.get("handling_suggestion", "ignore")
            if h in topic_stats[t]["handling"]:
                topic_stats[t]["handling"][h] += 1

        topic_distribution = {k: v["count"] for k, v in sorted(topic_stats.items(), key=lambda x: -x[1]["count"])}
        topic_breakdown = dict(sorted(topic_stats.items(), key=lambda x: -x[1]["count"]))

        return {
            "counters": counters,
            "window": window or "all",
            "rates": {
                "ban_rate": round(ban_rate, 4),
                "parse_error_rate": round(parse_err_rate, 4),
                "violation_rate": round((counters["ban_total"] + counters["limit_total"] + counters["warning_total"]) / total, 4) if total > 0 else 0,
            },
            "topic_distribution": topic_distribution,
            "topic_breakdown": topic_breakdown,
            "latency": latency_stats,
            "recent": list(recent_results)[:20],
            "uptime_seconds": uptime_seconds,
            "model_mode": "checkpoint" if model_path else "heuristic",
        }

    @app.get("/metrics", response_class=Response)
    def metrics():
        all_events = list(event_log)
        c = _compute_counters(all_events)
        risk_counts = Counter(str(e.get("risk_level", "unknown")) for e in all_events)
        topic_counts = Counter(str(e.get("topic", "unknown")) for e in all_events)
        handling_counts = Counter(str(e.get("handling_suggestion", "unknown")) for e in all_events)
        route_counts = Counter(str(e.get("route", "unknown")) for e in all_events)
        latency_stats = _latency_stats([float(e.get("latency_ms", 0) or 0) for e in all_events])
        lines = [
            "# HELP im_guard_requests_total Total audit requests.",
            "# TYPE im_guard_requests_total counter",
            f"im_guard_requests_total {c['requests_total']}",
            "# HELP im_guard_requests_by_risk_total Audit requests by risk level.",
            "# TYPE im_guard_requests_by_risk_total counter",
        ]
        lines.extend(f'im_guard_requests_by_risk_total{{risk_level="{_label(k)}"}} {v}' for k, v in sorted(risk_counts.items()))
        lines.extend(
            [
                "# HELP im_guard_requests_by_topic_total Audit requests by topic.",
                "# TYPE im_guard_requests_by_topic_total counter",
            ]
        )
        lines.extend(f'im_guard_requests_by_topic_total{{topic="{_label(k)}"}} {v}' for k, v in sorted(topic_counts.items()))
        lines.extend(
            [
                "# HELP im_guard_requests_by_handling_total Audit requests by handling suggestion.",
                "# TYPE im_guard_requests_by_handling_total counter",
            ]
        )
        lines.extend(f'im_guard_requests_by_handling_total{{handling_suggestion="{_label(k)}"}} {v}' for k, v in sorted(handling_counts.items()))
        lines.extend(
            [
                "# HELP im_guard_requests_by_route_total Audit requests by route.",
                "# TYPE im_guard_requests_by_route_total counter",
            ]
        )
        lines.extend(f'im_guard_requests_by_route_total{{route="{_label(k)}"}} {v}' for k, v in sorted(route_counts.items()))
        lines.extend(
            [
                "# HELP im_guard_latency_ms API latency summary gauges.",
                "# TYPE im_guard_latency_ms gauge",
            ]
        )
        lines.extend(f'im_guard_latency_ms{{quantile="{k}"}} {v}' for k, v in sorted(latency_stats.items()))
        lines.extend(
            [
                "# HELP im_guard_parse_non_ok_total Total non-ok parse results.",
                "# TYPE im_guard_parse_non_ok_total counter",
                f"im_guard_parse_non_ok_total {c['parse_non_ok_total']}",
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
            "topics": labels.get("topics", []),
            "risk_levels": labels.get("risk_levels", []),
            "judgments": labels.get("judgments", []),
            "handling_suggestions": labels.get("handling_suggestions", []),
            "alert_thresholds": cfg.get("alert_thresholds", ),
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
    ordered = sorted(values)
    n = len(ordered)
    return {
        "avg": round(sum(ordered) / n, 3),
        "p50": round(ordered[int(n * 0.5)], 3),
        "p95": round(ordered[min(int(n * 0.95), n - 1)], 3),
        "p99": round(ordered[min(int(n * 0.99), n - 1)], 3),
    }
