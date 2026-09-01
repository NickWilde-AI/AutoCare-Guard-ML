#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

INPUT_PATH="${1:-data/local/input.jsonl}"
if [ ! -f "$INPUT_PATH" ]; then
  mkdir -p "$(dirname "$INPUT_PATH")"
  cat > "$INPUT_PATH" <<'EOF'
{"case_id":"demo-battery-001","service_context":{"channel":"app","urgency":"high"},"vehicle_context":{"model":"AutoCare EV-Pro","mileage_km":28600},"conversation_evidence":[{"role":"customer","original_content":"充电时闻到焦糊味，仪表跳了电池相关告警。"}],"vehicle_signal_summary":{"alerts":["battery_thermal_warning"],"battery_temp_c":52.3},"fault_evidence":[{"fault_code":"BMS_THERMAL_WARN","description":"动力电池热管理告警"}],"service_history_summary":{"recent_visit_count_30d":0,"warranty_status":"in_warranty"}}
{"case_id":"demo-brake-002","service_context":{"channel":"hotline","urgency":"high"},"vehicle_context":{"model":"AutoCare SUV-AWD","mileage_km":41200},"conversation_evidence":[{"role":"customer","original_content":"刹车时有明显异响，踩下去行程变长了。"}],"vehicle_signal_summary":{"alerts":["brake_performance_warn"],"abs_events":2},"fault_evidence":[{"fault_code":"ABS_INTERMITTENT","description":"ABS 间歇性故障灯"}],"service_history_summary":{"recent_visit_count_30d":1,"warranty_status":"in_warranty"}}
{"case_id":"demo-safe-003","service_context":{"channel":"app","urgency":"low"},"vehicle_context":{"model":"AutoCare Sedan-RWD","mileage_km":15000},"conversation_evidence":[{"role":"customer","original_content":"想问一下下次保养大概什么时候？里程快到了。"}],"vehicle_signal_summary":{"alerts":[],"soc_pct":68},"fault_evidence":[],"service_history_summary":{"recent_visit_count_30d":0,"warranty_status":"in_warranty"}}
EOF
  echo "Generated AutoCare sample input at $INPUT_PATH"
fi

python3 -m autocare_guard_ml.cli --config configs/default.yaml summary "$INPUT_PATH"
python3 -m autocare_guard_ml.cli --config configs/default.yaml predict "$INPUT_PATH" --out outputs/demo_predictions.jsonl
python3 -m autocare_guard_ml.cli --config configs/default.yaml eval outputs/demo_predictions.jsonl

if [ "${DEMO_JUDGE_URL:-}" != "" ]; then
  curl -sS -X POST "${DEMO_JUDGE_URL}" \
    -H "Content-Type: application/json" \
    -d '{"case_id":"demo-curl-1","service_context":{"channel":"app"},"conversation_evidence":[{"original_content":"车辆无法启动，仪表只有供电没有 Ready。"}],"vehicle_signal_summary":{"alerts":["drive_ready_fail"]},"fault_evidence":[{"fault_code":"DRIVE_READY_FAIL","description":"Ready 状态建立失败"}]}' \
    | python3 -m json.tool
fi
