from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .dataio import load_yaml, read_jsonl, stratified_summary, write_jsonl
from .inference import HeuristicJudge, TransformersJudge
from .training import run_sft


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="im-guard")
    parser.add_argument("--config", default="configs/default.yaml")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_summary = sub.add_parser("summary")
    p_summary.add_argument("jsonl")

    p_predict = sub.add_parser("predict")
    p_predict.add_argument("jsonl")
    p_predict.add_argument("--out")
    p_predict.add_argument("--model-path")
    p_predict.add_argument("--api", action="store_true", help="Use API-based judge (requires QWEN_API_KEY env)")
    p_predict.add_argument("--api-model", default="qwen-plus", help="API model name (default: qwen-plus)")
    p_predict.add_argument("--with-route", action="store_true")
    p_predict.add_argument("--with-version", action="store_true")
    p_predict.add_argument("--audit-log-out")

    p_eval = sub.add_parser("eval")
    p_eval.add_argument("pred_jsonl")

    p_eval_report = sub.add_parser("eval-report")
    p_eval_report.add_argument("pred_jsonl")
    p_eval_report.add_argument("--out", default="outputs/offline_eval_report.md")
    p_eval_report.add_argument("--title", default="AI-IM-Guard-ML 离线评测报告")

    p_ab = sub.add_parser("ab-report")
    p_ab.add_argument("--control", required=True, help="Control prediction JSONL with label/prediction fields.")
    p_ab.add_argument("--candidate", required=True, help="Candidate prediction JSONL with label/prediction fields.")
    p_ab.add_argument("--out", default="outputs/ab_report.md")
    p_ab.add_argument("--json-out", help="Optional machine-readable JSON report path.")
    p_ab.add_argument("--title", default="AI-IM-Guard-ML A/B 灰度对比报告")

    p_api_contract = sub.add_parser("api-contract")
    p_api_contract.add_argument("--out", default="outputs/openapi_contract.json")
    p_api_contract.add_argument("--fail-on-missing", action="store_true")

    p_preflight = sub.add_parser("production-preflight")
    p_preflight.add_argument("--env-file", default="deploy/audit_service.prod.env.example")
    p_preflight.add_argument("--out", default="outputs/production_preflight.json")
    p_preflight.add_argument("--fail-on-warn", action="store_true")

    p_registry = sub.add_parser("model-registry-check")
    p_registry.add_argument("--registry", default="configs/model_registry.yaml")
    p_registry.add_argument("--out", default="outputs/model_registry_check.json")
    p_registry.add_argument("--fail-on-warn", action="store_true")

    p_delivery = sub.add_parser("delivery-summary")
    p_delivery.add_argument("--out", default="outputs/enterprise_delivery_summary.md")
    p_delivery.add_argument("--project-root", default=".")

    p_readiness = sub.add_parser("readiness-check")
    p_readiness.add_argument("--project-root", default=".")
    p_readiness.add_argument("--out")
    p_readiness.add_argument("--fail-on-warn", action="store_true")

    p_train = sub.add_parser("train")
    p_train.add_argument("train_jsonl_or_dataset")

    p_train_ready = sub.add_parser("train-readiness")
    p_train_ready.add_argument("train_jsonl")
    p_train_ready.add_argument("--out", default="outputs/training_readiness.json")
    p_train_ready.add_argument("--max-scan-rows", type=int)
    p_train_ready.add_argument("--fail-on-warn", action="store_true")

    p_monitor = sub.add_parser("monitor")
    p_monitor.add_argument("prediction_jsonl")
    p_monitor.add_argument("--baseline-json")

    p_alerts = sub.add_parser("alerts")
    p_alerts.add_argument("prediction_jsonl")
    p_alerts.add_argument("--baseline-json")

    p_window_alerts = sub.add_parser("window-alerts")
    p_window_alerts.add_argument("prediction_jsonl")
    p_window_alerts.add_argument("--baseline-json")
    p_window_alerts.add_argument("--window-size", type=int, default=100)
    p_window_alerts.add_argument("--step-size", type=int)

    p_drift = sub.add_parser("drift-report")
    p_drift.add_argument("prediction_jsonl")
    p_drift.add_argument("--baseline-json", help="Monitoring report JSON produced by `monitor`.")
    p_drift.add_argument("--baseline-pred-jsonl", help="Historical prediction JSONL used to build the baseline report.")
    p_drift.add_argument("--out")

    p_audit = sub.add_parser("audit-data")
    p_audit.add_argument("jsonl")
    p_audit.add_argument("--eval-jsonl")

    p_serve = sub.add_parser("serve")
    p_serve.add_argument("--model-path")
    p_serve.add_argument("--api", action="store_true", help="Use API-based judge (requires QWEN_API_KEY env)")
    p_serve.add_argument("--api-model", default="qwen-plus", help="API model name (default: qwen-plus)")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", default=8000, type=int)

    args = parser.parse_args(argv)
    cfg = load_yaml(args.config)
    if args.cmd == "summary":
        print(json.dumps(stratified_summary(read_jsonl(args.jsonl)), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "predict":
        from .postprocess import route_policy
        from .versioning import build_audit_log, version_info_from_config

        rows = read_jsonl(args.jsonl)
        if args.api:
            from .inference import APIJudge
            judge = APIJudge(cfg.get("rubrics", {}), model=args.api_model)
        elif args.model_path:
            judge = TransformersJudge(args.model_path, cfg.get("rubrics", {}))
        else:
            judge = HeuristicJudge(cfg.get("rubrics", {}))
        versions = version_info_from_config(cfg, args.model_path)
        preds = []
        audit_logs = []
        for row in rows:
            pred = judge.predict(row)
            if args.with_route:
                route, final_action = route_policy(pred, row)
                pred = {**pred, "route": route, "final_action": final_action}
            if args.with_version:
                pred = {**versions.to_dict(), **pred}
            preds.append({**row, "prediction": pred})
            if args.audit_log_out:
                audit_logs.append(build_audit_log(row, pred, versions))
        if args.out:
            write_jsonl(args.out, preds)
        else:
            for row in preds:
                print(json.dumps(row, ensure_ascii=False))
        if args.audit_log_out:
            write_jsonl(args.audit_log_out, audit_logs)
        return 0
    if args.cmd == "eval":
        from .evaluation import eval_binary, eval_multi_field

        rows = read_jsonl(args.pred_jsonl)
        gold = [row["label"] for row in rows if "label" in row and "prediction" in row]
        pred = [row["prediction"] for row in rows if "label" in row and "prediction" in row]
        metas = [{"topic": row.get("label", {}).get("topic", "unknown")} for row in rows if "label" in row and "prediction" in row]
        binary_targets = [1 if x["final_judgment"] == "exist_violation" else 0 for x in gold]
        binary_preds = [1 if x["final_judgment"] == "exist_violation" else 0 for x in pred]
        result = {
            "binary": eval_binary(binary_targets, binary_preds),
            "multi_field": eval_multi_field(gold, pred, metas),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "eval-report":
        from .reporting import build_offline_eval_report

        report = build_offline_eval_report(read_jsonl(args.pred_jsonl), title=args.title)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(report, encoding="utf-8")
        print(args.out)
        return 0
    if args.cmd == "ab-report":
        from .rollout import build_ab_report, render_ab_report_markdown

        report = build_ab_report(read_jsonl(args.control), read_jsonl(args.candidate), config=cfg)
        markdown = render_ab_report_markdown(report, title=args.title)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(markdown, encoding="utf-8")
        if args.json_out:
            Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.json_out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(args.out)
        return 0
    if args.cmd == "api-contract":
        from .api_contract import build_openapi_contract

        contract = build_openapi_contract(args.config)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(args.out)
        if args.fail_on_missing and contract["x-im-guard-contract-status"]["status"] != "pass":
            return 1
        return 0
    if args.cmd == "production-preflight":
        from .preflight import build_production_preflight

        report = build_production_preflight(args.env_file)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(args.out)
        if report["status"] == "fail" or (args.fail_on_warn and report["status"] == "warn"):
            return 1
        return 0
    if args.cmd == "model-registry-check":
        from .model_registry import build_model_registry_report

        report = build_model_registry_report(args.registry)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(args.out)
        if report["status"] == "fail" or (args.fail_on_warn and report["status"] == "warn"):
            return 1
        return 0
    if args.cmd == "delivery-summary":
        from .reporting import build_delivery_summary

        report = build_delivery_summary(args.project_root)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(report, encoding="utf-8")
        print(args.out)
        return 0
    if args.cmd == "readiness-check":
        from .reporting import build_readiness_check

        report = build_readiness_check(args.project_root)
        text = json.dumps(report, ensure_ascii=False, indent=2)
        if args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(text + "\n", encoding="utf-8")
            print(args.out)
        else:
            print(text)
        if report["status"] == "fail" or (args.fail_on_warn and report["status"] == "warn"):
            return 1
        return 0
    if args.cmd == "train":
        run_sft(cfg, args.train_jsonl_or_dataset, cfg.get("rubrics", {}))
        return 0
    if args.cmd == "train-readiness":
        from .training_readiness import build_training_readiness_report

        report = build_training_readiness_report(
            args.train_jsonl,
            config_path=args.config,
            max_scan_rows=args.max_scan_rows,
        )
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(args.out)
        if report["status"] == "fail" or (args.fail_on_warn and report["status"] == "warn"):
            return 1
        return 0
    if args.cmd == "monitor":
        from .monitoring import build_monitoring_report, compare_reports

        rows = read_jsonl(args.prediction_jsonl)
        report = build_monitoring_report(rows)
        if args.baseline_json:
            with Path(args.baseline_json).open("r", encoding="utf-8") as fh:
                baseline = json.load(fh)
            report = {"current": report, "diff": compare_reports(report, baseline)}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "alerts":
        from .alerting import evaluate_alerts
        from .monitoring import build_monitoring_report, compare_reports

        rows = read_jsonl(args.prediction_jsonl)
        report = build_monitoring_report(rows)
        if args.baseline_json:
            with Path(args.baseline_json).open("r", encoding="utf-8") as fh:
                baseline = json.load(fh)
            report = {"current": report, "diff": compare_reports(report, baseline)}
        print(json.dumps(evaluate_alerts(report, cfg.get("alert_thresholds", {})), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "window-alerts":
        from .monitoring import build_monitoring_report, build_sliding_window_report

        rows = read_jsonl(args.prediction_jsonl)
        baseline = None
        if args.baseline_json:
            with Path(args.baseline_json).open("r", encoding="utf-8") as fh:
                baseline = json.load(fh)
        else:
            baseline = build_monitoring_report(rows)
        report = build_sliding_window_report(
            rows,
            window_size=args.window_size,
            step_size=args.step_size,
            baseline_report=baseline,
            thresholds=cfg.get("alert_thresholds", {}),
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "drift-report":
        from .drift_detection import detect_drift
        from .monitoring import build_monitoring_report

        current_rows = read_jsonl(args.prediction_jsonl)
        current_report = build_monitoring_report(current_rows)
        if args.baseline_json:
            with Path(args.baseline_json).open("r", encoding="utf-8") as fh:
                baseline_report = json.load(fh)
        elif args.baseline_pred_jsonl:
            baseline_report = build_monitoring_report(read_jsonl(args.baseline_pred_jsonl))
        else:
            baseline_report = current_report
        drift = detect_drift(current_report, baseline_report)
        report = {
            "status": drift.status,
            "summary": drift.summary,
            "current_total": current_report.get("total", 0),
            "baseline_total": baseline_report.get("total", 0),
            "tests": [asdict(test) for test in drift.tests],
        }
        text = json.dumps(report, ensure_ascii=False, indent=2)
        if args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(text + "\n", encoding="utf-8")
            print(args.out)
        else:
            print(text)
        return 0
    if args.cmd == "audit-data":
        from .data_audit import audit_dataset, split_leakage_report

        rows = read_jsonl(args.jsonl)
        report = {"dataset": audit_dataset(rows)}
        if args.eval_jsonl:
            report["leakage"] = split_leakage_report(rows, read_jsonl(args.eval_jsonl))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "serve":
        import uvicorn

        from .api import create_app

        uvicorn.run(create_app(args.config, args.model_path, api=getattr(args, 'api', False), api_model=getattr(args, 'api_model', 'qwen-plus')), host=args.host, port=args.port)
        return 0
    print("unknown command", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
