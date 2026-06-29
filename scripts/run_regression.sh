#!/usr/bin/env bash
# Run core regression tests (Phase 3–5 + integration smoke).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="${ROOT}/backend${PYTHONPATH:+:$PYTHONPATH}"
export DEBUG_LIVE_LOGGING=false

PY=python3

echo "=== Phase 5 voice turn policy ==="
if $PY -m pytest backend/tests/test_voice_turn_policy.py -q 2>/dev/null; then
  :
else
  $PY backend/tests/test_voice_turn_policy.py
fi

echo "=== Phase 3 session flow ==="
$PY backend/tests/test_phase3_session_flow.py

echo "=== Phase 4 evaluation ==="
$PY backend/tests/test_phase4_evaluation.py

echo "=== Pipecat integration ==="
$PY backend/test_pipecat_integration.py

echo "=== Dialogue adapter ==="
$PY backend/test_dialogue_adapter.py

echo "=== All regression checks passed ==="
