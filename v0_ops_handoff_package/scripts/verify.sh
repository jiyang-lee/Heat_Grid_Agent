#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

docker compose up -d

ready=0
for _ in $(seq 1 30); do
  if docker compose exec -T postgres psql -U heatgrid -d heatgrid_ops -c "select 1" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done

if [ "$ready" -ne 1 ]; then
  docker compose logs postgres
  exit 1
fi

docker compose exec -T postgres psql -U heatgrid -d heatgrid_ops < queries/verify.sql

python - <<'PY'
import json
from pathlib import Path

payload = json.loads(Path("input.json").read_text(encoding="utf-8"))
raw = payload["raw_context"]
priority = payload["priority_context"]
calculation = priority["priority"]["calculation"]
explanation = priority["explanation"]

assert raw["current_best_sensor_values"]["top_n"] == 10
assert len(raw["current_best_sensor_values"]["values"]) == 10
assert raw["m1_specialist_features"]["feature_count"] == 13
assert len(raw["m1_specialist_features"]["features"]) == 13
assert "formula" not in priority
assert "review_reasons" not in priority
assert "review_required" not in priority["card"]
assert calculation["current_best_weight"] == 0.65
assert calculation["m1_specialist_weight"] == 0.35
assert "current_best_priority_score" not in calculation
assert "m1_specialist_priority_score" not in calculation
assert explanation["review_required"] is True
assert len(explanation["review_reasons"]) == 3

print("input.json OK: current-best=10, m1=13, weights=0.65/0.35")
PY
