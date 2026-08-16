#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

INPUT_PATH="${1:-data/local/input.jsonl}"
if [ ! -f "$INPUT_PATH" ]; then
  echo "Prepare a local, redacted JSONL file and pass its path as the first argument." >&2
  exit 2
fi

python3 -m im_guard_ml.cli --config configs/default.yaml summary "$INPUT_PATH"
python3 -m im_guard_ml.cli --config configs/default.yaml predict "$INPUT_PATH" --out outputs/demo_predictions.jsonl
python3 -m im_guard_ml.cli --config configs/default.yaml eval outputs/demo_predictions.jsonl
