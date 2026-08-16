import hashlib
import json

from fastapi.testclient import TestClient

from im_guard_ml.api import create_app


def test_api_without_token_keeps_demo_access(monkeypatch, tmp_path):
    monkeypatch.delenv("IM_GUARD_API_TOKEN", raising=False)
    monkeypatch.setenv("IM_GUARD_AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    client = TestClient(create_app())

    response = client.post("/judge", json={"ticket_id": "demo-1", "chat_evidence_list": ["正常聊天"]})

    assert response.status_code == 200
    assert "request_id" in response.json()


def test_api_with_token_requires_bearer(monkeypatch, tmp_path):
    monkeypatch.setenv("IM_GUARD_API_TOKEN", "secret")
    monkeypatch.setenv("IM_GUARD_AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    client = TestClient(create_app())

    assert client.post("/judge", json={"ticket_id": "demo-2"}).status_code == 401
    assert client.get("/dashboard/data").status_code == 401
    assert client.post(
        "/judge",
        headers={"Authorization": "Bearer wrong"},
        json={"ticket_id": "demo-2"},
    ).status_code == 401


def test_api_role_tokens_enforce_minimal_permissions(monkeypatch, tmp_path):
    monkeypatch.delenv("IM_GUARD_API_TOKEN", raising=False)
    monkeypatch.setenv("IM_GUARD_API_TOKENS", "writer-token:writer,reader-token:reader,audit-token:auditor")
    monkeypatch.setenv("IM_GUARD_AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    client = TestClient(create_app())

    assert client.post(
        "/judge",
        headers={"Authorization": "Bearer writer-token"},
        json={"ticket_id": "rbac-1"},
    ).status_code == 200
    assert client.get("/dashboard/data", headers={"Authorization": "Bearer reader-token"}).status_code == 200
    assert client.get("/audit/tickets/rbac-1", headers={"Authorization": "Bearer reader-token"}).status_code == 401
    assert client.get("/audit/tickets/rbac-1", headers={"Authorization": "Bearer audit-token"}).status_code == 200


def test_api_accepts_hashed_role_tokens(monkeypatch, tmp_path):
    token_hash = hashlib.sha256("hashed-writer-token".encode("utf-8")).hexdigest()
    monkeypatch.delenv("IM_GUARD_API_TOKEN", raising=False)
    monkeypatch.delenv("IM_GUARD_API_TOKENS", raising=False)
    monkeypatch.setenv("IM_GUARD_API_TOKEN_HASHES", f"{token_hash}:writer")
    monkeypatch.setenv("IM_GUARD_AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    client = TestClient(create_app())

    denied = client.post(
        "/judge",
        headers={"Authorization": "Bearer wrong-token"},
        json={"ticket_id": "hashed-1"},
    )
    accepted = client.post(
        "/judge",
        headers={"Authorization": "Bearer hashed-writer-token"},
        json={"ticket_id": "hashed-1"},
    )
    ready = client.get("/ready")

    assert denied.status_code == 401
    assert accepted.status_code == 200
    assert ready.json()["auth_roles"] == ["writer"]


def test_api_token_success_returns_request_id_and_writes_audit(monkeypatch, tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setenv("IM_GUARD_API_TOKEN", "secret")
    monkeypatch.setenv("IM_GUARD_AUDIT_LOG_PATH", str(audit_path))
    client = TestClient(create_app())

    response = client.post(
        "/judge",
        headers={"Authorization": "Bearer secret", "X-Request-ID": "req-123"},
        json={
            "ticket_id": "demo-3",
            "chat_evidence_list": ["加微信稳赚，带你投资。"],
            "behavior_abnormal_list": ["短时间高频私聊。"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["request_id"] == "req-123"
    audit_event = json.loads(audit_path.read_text(encoding="utf-8").strip())
    assert audit_event["request_id"] == "req-123"
    assert audit_event["ticket_id"] == "demo-3"
    assert audit_event["route"] == body["route"]
    assert audit_event["input_summary"]["chat_evidence_count"] == 1
    assert "chat_evidence_list" not in audit_event


def test_api_sqlite_audit_backend_writes_and_queries(monkeypatch, tmp_path):
    audit_path = tmp_path / "audit.sqlite"
    monkeypatch.setenv("IM_GUARD_API_TOKEN", "secret")
    monkeypatch.setenv("IM_GUARD_AUDIT_BACKEND", "sqlite")
    monkeypatch.setenv("IM_GUARD_AUDIT_LOG_PATH", str(audit_path))
    client = TestClient(create_app())

    response = client.post(
        "/judge",
        headers={"Authorization": "Bearer secret", "X-Request-ID": "sqlite-req"},
        json={"ticket_id": "sqlite-ticket", "chat_evidence_list": ["加微信稳赚。"]},
    )
    lookup = client.get("/audit/tickets/sqlite-ticket", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    assert audit_path.exists()
    assert lookup.status_code == 200
    assert lookup.json()["events"][0]["request_id"] == "sqlite-req"
    assert "input_summary" in lookup.json()["events"][0]


def test_ready_reports_production_guard_config(monkeypatch, tmp_path):
    monkeypatch.setenv("IM_GUARD_API_TOKEN", "secret")
    monkeypatch.setenv("IM_GUARD_AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("IM_GUARD_MAX_REQUEST_BYTES", "1234")
    monkeypatch.setenv("IM_GUARD_RATE_LIMIT_PER_MINUTE", "77")
    client = TestClient(create_app())

    response = client.get("/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["auth_enabled"] is True
    assert body["audit_backend"] == "jsonl"
    assert body["max_request_bytes"] == 1234
    assert body["rate_limit_per_minute"] == 77


def test_request_size_limit_returns_structured_error(monkeypatch, tmp_path):
    monkeypatch.delenv("IM_GUARD_API_TOKEN", raising=False)
    monkeypatch.setenv("IM_GUARD_AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("IM_GUARD_MAX_REQUEST_BYTES", "10")
    client = TestClient(create_app())

    response = client.post("/judge", json={"ticket_id": "too-large"})

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"
    assert "X-Request-ID" in response.headers


def test_rate_limit_returns_structured_error(monkeypatch, tmp_path):
    monkeypatch.delenv("IM_GUARD_API_TOKEN", raising=False)
    monkeypatch.setenv("IM_GUARD_AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("IM_GUARD_RATE_LIMIT_PER_MINUTE", "1")
    client = TestClient(create_app())

    payload = {"ticket_id": "rate-limit-test", "chat_evidence_list": ["synthetic test"]}
    assert client.post("/judge", json=payload).status_code == 200
    response = client.post("/judge", json=payload)

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"


def test_audit_ticket_lookup_requires_auth_and_returns_events(monkeypatch, tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setenv("IM_GUARD_API_TOKEN", "secret")
    monkeypatch.setenv("IM_GUARD_AUDIT_LOG_PATH", str(audit_path))
    client = TestClient(create_app())

    client.post(
        "/judge",
        headers={"Authorization": "Bearer secret"},
        json={"ticket_id": "audit-ticket-1", "chat_evidence_list": ["加微信稳赚。"]},
    )

    unauthorized = client.get("/audit/tickets/audit-ticket-1")
    response = client.get("/audit/tickets/audit-ticket-1", headers={"Authorization": "Bearer secret"})

    assert unauthorized.status_code == 401
    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["events"][0]["ticket_id"] == "audit-ticket-1"


def test_metrics_include_topic_risk_handling_and_route_labels(monkeypatch, tmp_path):
    monkeypatch.delenv("IM_GUARD_API_TOKEN", raising=False)
    monkeypatch.setenv("IM_GUARD_AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    client = TestClient(create_app())
    client.post("/judge", json={"ticket_id": "metric-1", "chat_evidence_list": ["加微信稳赚。"]})

    response = client.get("/metrics")
    text = response.text

    assert response.status_code == 200
    assert "im_guard_requests_by_risk_total" in text
    assert "im_guard_requests_by_topic_total" in text
    assert "im_guard_requests_by_handling_total" in text
    assert "im_guard_requests_by_route_total" in text


def test_config_endpoint_returns_full_introspection(monkeypatch, tmp_path):
    monkeypatch.delenv("IM_GUARD_API_TOKEN", raising=False)
    monkeypatch.setenv("IM_GUARD_AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    client = TestClient(create_app())

    response = client.get("/config")

    assert response.status_code == 200
    body = response.json()
    assert "config_path" in body
    assert "topics" in body and len(body["topics"]) > 0
    assert "risk_levels" in body
    assert "handling_suggestions" in body
    assert "alert_thresholds" in body
    assert "rubrics" in body
    assert "model" in body
    assert "model_version" in body
