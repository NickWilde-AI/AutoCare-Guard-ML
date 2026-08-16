from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Protocol


class AuditStore(Protocol):
    def append(self, event: dict) -> None: ...
    def find_by_ticket(self, ticket_id: str, *, limit: int = 50) -> list[dict]: ...


class JsonlAuditStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(self, event: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")

    def find_by_ticket(self, ticket_id: str, *, limit: int = 50) -> list[dict]:
        if not self.path.exists():
            return []
        matches: list[dict] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                event = json.loads(line)
                if str(event.get("ticket_id", "")) == ticket_id:
                    matches.append(event)
        return matches[-limit:]


class SQLiteAuditStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def append(self, event: dict) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                INSERT INTO audit_events (
                    request_id, ticket_id, timestamp, model_mode,
                    model_version, prompt_version, rubric_version,
                    feature_schema_version, postprocess_version,
                    risk_level, topic, final_judgment,
                    handling_suggestion, route, final_action,
                    latency_ms, parse_non_ok, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.get("request_id", ""),
                    event.get("ticket_id", ""),
                    event.get("timestamp", ""),
                    event.get("model_mode", ""),
                    event.get("model_version", ""),
                    event.get("prompt_version", ""),
                    event.get("rubric_version", ""),
                    event.get("feature_schema_version", ""),
                    event.get("postprocess_version", ""),
                    event.get("risk_level", ""),
                    event.get("topic", ""),
                    event.get("final_judgment", ""),
                    event.get("handling_suggestion", ""),
                    event.get("route", ""),
                    event.get("final_action", ""),
                    float(event.get("latency_ms", 0) or 0),
                    1 if event.get("parse_non_ok") else 0,
                    json.dumps(event, ensure_ascii=False),
                ),
            )

    def find_by_ticket(self, ticket_id: str, *, limit: int = 50) -> list[dict]:
        with sqlite3.connect(self.path) as conn:
            rows = conn.execute(
                """
                SELECT payload_json
                FROM audit_events
                WHERE ticket_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (ticket_id, limit),
            ).fetchall()
        return [json.loads(row[0]) for row in reversed(rows)]

    def _init_schema(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    ticket_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    model_mode TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    rubric_version TEXT NOT NULL,
                    feature_schema_version TEXT NOT NULL,
                    postprocess_version TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    final_judgment TEXT NOT NULL,
                    handling_suggestion TEXT NOT NULL,
                    route TEXT NOT NULL,
                    final_action TEXT NOT NULL,
                    latency_ms REAL NOT NULL,
                    parse_non_ok INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_ticket_id ON audit_events(ticket_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_request_id ON audit_events(request_id)")


def create_audit_store(backend: str, path: str | Path) -> AuditStore:
    if backend.strip().lower() == "sqlite":
        return SQLiteAuditStore(path)
    return JsonlAuditStore(path)
