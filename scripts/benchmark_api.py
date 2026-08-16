from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def post_json(url: str, payload: dict, token: str = "", *, timeout: float = 30.0) -> tuple[int, float]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
            status = resp.status
    except urllib.error.HTTPError as exc:
        exc.read()
        status = exc.code
    return status, (time.perf_counter() - t0) * 1000


def build_payload(ticket_id: str) -> dict:
    return {
        "ticket_id": ticket_id,
        "chat_evidence_list": ["加微信稳赚，带你投资。"],
        "behavior_abnormal_list": ["短时间高频私聊。"],
    }


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(int(len(ordered) * p), len(ordered) - 1)
    return round(ordered[idx], 2)


def summarize_results(requests: int, elapsed: float, status_counts: dict[int, int], latencies: list[float], *, concurrency: int = 1) -> dict:
    success_count = sum(count for status, count in status_counts.items() if 200 <= status < 300)
    return {
        "requests": requests,
        "concurrency": concurrency,
        "elapsed_seconds": round(elapsed, 3),
        "qps": round(requests / elapsed, 2) if elapsed > 0 else 0,
        "success_rate": round(success_count / requests, 4) if requests > 0 else 0,
        "status_counts": {str(status): count for status, count in sorted(status_counts.items())},
        "latency_ms": {
            "avg": round(statistics.mean(latencies), 2) if latencies else 0,
            "p50": percentile(latencies, 0.5),
            "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99),
            "max": round(max(latencies), 2) if latencies else 0,
        },
    }


def run_benchmark(
    url: str,
    requests: int,
    *,
    token: str = "",
    warmup: int = 0,
    timeout: float = 30.0,
    concurrency: int = 1,
    post_fn: Callable[[str, dict, str, float], tuple[int, float]] | None = None,
) -> dict:
    post = post_fn or (lambda post_url, payload, post_token, post_timeout: post_json(post_url, payload, post_token, timeout=post_timeout))
    for i in range(max(warmup, 0)):
        post(url, build_payload(f"bench-warmup-{i:05d}"), token, timeout)

    latencies: list[float] = []
    status_counts: dict[int, int] = {}

    if concurrency <= 1:
        started = time.perf_counter()
        for i in range(requests):
            status, latency = post(url, build_payload(f"bench-local-{i:05d}"), token, timeout)
            latencies.append(latency)
            status_counts[status] = status_counts.get(status, 0) + 1
        elapsed = time.perf_counter() - started
    else:
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = []
            for i in range(requests):
                fut = executor.submit(post, url, build_payload(f"bench-conc-{i:05d}"), token, timeout)
                futures.append(fut)
            for fut in as_completed(futures):
                status, latency = fut.result()
                latencies.append(latency)
                status_counts[status] = status_counts.get(status, 0) + 1
        elapsed = time.perf_counter() - started

    result = summarize_results(requests, elapsed, status_counts, latencies, concurrency=concurrency)
    result["url"] = url
    result["warmup_requests"] = max(warmup, 0)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark for the IM Guard API /judge endpoint. Supports sequential and concurrent modes.")
    parser.add_argument("--url", default="http://127.0.0.1:8000/judge")
    parser.add_argument("--requests", type=int, default=50)
    parser.add_argument("--concurrency", type=int, default=1, help="Number of concurrent workers (default: 1 = sequential)")
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--token", default="")
    parser.add_argument("--out", default="")
    parser.add_argument("--fail-on-non-2xx", action="store_true")
    parser.add_argument("--fail-on-p95-ms", type=float, default=0.0)
    args = parser.parse_args()
    if args.requests < 1:
        raise SystemExit("--requests must be >= 1")
    if args.concurrency < 1:
        raise SystemExit("--concurrency must be >= 1")

    result = run_benchmark(
        args.url, args.requests,
        token=args.token, warmup=args.warmup,
        timeout=args.timeout, concurrency=args.concurrency,
    )
    body = json.dumps(result, ensure_ascii=False, indent=2)
    print(body)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(body + "\n", encoding="utf-8")

    failed = False
    if args.fail_on_non_2xx and result["success_rate"] < 1.0:
        failed = True
    if args.fail_on_p95_ms and result["latency_ms"]["p95"] > args.fail_on_p95_ms:
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
