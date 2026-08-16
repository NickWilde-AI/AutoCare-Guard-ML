from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_benchmark_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_api.py"
    spec = importlib.util.spec_from_file_location("benchmark_api_script", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_summarize_results_reports_success_rate_and_latency_percentiles():
    benchmark = _load_benchmark_module()

    result = benchmark.summarize_results(
        4,
        2.0,
        {200: 3, 500: 1},
        [10.0, 20.0, 30.0, 40.0],
    )

    assert result["qps"] == 2.0
    assert result["success_rate"] == 0.75
    assert result["status_counts"] == {"200": 3, "500": 1}
    assert result["latency_ms"]["p50"] == 30.0
    assert result["latency_ms"]["p95"] == 40.0


def test_run_benchmark_excludes_warmup_from_reported_requests():
    benchmark = _load_benchmark_module()
    calls: list[str] = []

    def fake_post(_url: str, payload: dict, _token: str, _timeout: float):
        calls.append(payload["ticket_id"])
        return 200, 10.0

    result = benchmark.run_benchmark(
        "http://127.0.0.1:8000/judge",
        2,
        warmup=3,
        post_fn=fake_post,
    )

    assert result["requests"] == 2
    assert result["warmup_requests"] == 3
    assert result["status_counts"] == {"200": 2}
    assert calls[:3] == ["bench-warmup-00000", "bench-warmup-00001", "bench-warmup-00002"]
    assert calls[3:] == ["bench-local-00000", "bench-local-00001"]


def test_run_benchmark_concurrent_mode():
    benchmark = _load_benchmark_module()

    def fake_post(_url: str, payload: dict, _token: str, _timeout: float):
        return 200, 15.0

    result = benchmark.run_benchmark(
        "http://127.0.0.1:8000/judge",
        10,
        warmup=0,
        concurrency=5,
        post_fn=fake_post,
    )

    assert result["requests"] == 10
    assert result["concurrency"] == 5
    assert result["success_rate"] == 1.0
    assert result["status_counts"] == {"200": 10}
    assert result["latency_ms"]["p50"] == 15.0


def test_main_writes_report_and_fails_when_p95_exceeds_threshold(tmp_path, monkeypatch):
    benchmark = _load_benchmark_module()
    out = tmp_path / "api_benchmark.json"

    def fake_run_benchmark(*_args, **_kwargs):
        return {
            "requests": 1,
            "elapsed_seconds": 0.01,
            "qps": 100.0,
            "success_rate": 1.0,
            "status_counts": {"200": 1},
            "latency_ms": {"avg": 1500.0, "p50": 1500.0, "p95": 1500.0, "p99": 1500.0, "max": 1500.0},
            "url": "http://127.0.0.1:8000/judge",
            "warmup_requests": 0,
        }

    monkeypatch.setattr(benchmark, "run_benchmark", fake_run_benchmark)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "benchmark_api.py",
            "--requests",
            "1",
            "--warmup",
            "0",
            "--out",
            str(out),
            "--fail-on-p95-ms",
            "1200",
        ],
    )

    assert benchmark.main() == 1
    assert '"p95": 1500.0' in out.read_text(encoding="utf-8")
