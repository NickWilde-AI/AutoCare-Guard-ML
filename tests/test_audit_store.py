from im_guard_ml.audit_store import JsonlAuditStore, SQLiteAuditStore, create_audit_store


def test_jsonl_audit_store_appends_and_finds_by_ticket(tmp_path):
    store = JsonlAuditStore(tmp_path / "audit.jsonl")
    store.append({"request_id": "r1", "ticket_id": "t1", "risk_level": "low_risk"})
    store.append({"request_id": "r2", "ticket_id": "t2", "risk_level": "mid_risk"})

    events = store.find_by_ticket("t1")

    assert len(events) == 1
    assert events[0]["request_id"] == "r1"


def test_sqlite_audit_store_appends_and_finds_by_ticket(tmp_path):
    store = SQLiteAuditStore(tmp_path / "audit.sqlite")
    store.append({
        "request_id": "r1",
        "ticket_id": "t1",
        "timestamp": "2026-06-06 00:00:00",
        "model_mode": "heuristic-demo",
        "model_version": "m",
        "prompt_version": "p",
        "rubric_version": "r",
        "feature_schema_version": "f",
        "postprocess_version": "post",
        "risk_level": "mid_risk",
        "topic": "诈骗引流",
        "final_judgment": "exist_violation",
        "handling_suggestion": "warning",
        "route": "auto_action",
        "final_action": "send_warning",
        "latency_ms": 12.3,
        "parse_non_ok": False,
    })

    events = store.find_by_ticket("t1")

    assert len(events) == 1
    assert events[0]["topic"] == "诈骗引流"


def test_create_audit_store_selects_sqlite(tmp_path):
    store = create_audit_store("sqlite", tmp_path / "audit.sqlite")

    assert isinstance(store, SQLiteAuditStore)
