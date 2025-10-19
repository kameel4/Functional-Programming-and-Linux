#!/usr/bin/env bash
set -euo pipefail
python - <<'PY'
from app.report import build_report
out = build_report("./logs/events.jsonl", "./reports")
print("Report saved to:", out)
PY
