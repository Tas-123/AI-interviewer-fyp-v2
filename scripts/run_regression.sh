#!/usr/bin/env bash
# Run core regression tests (Phase 3–5 + integration smoke).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="${ROOT}/backend${PYTHONPATH:+:$PYTHONPATH}"
export DEBUG_LIVE_LOGGING=false

PY=python3

echo "=== Phase 6A interview flow ==="
$PY backend/tests/test_phase6a_interview_flow.py

echo "=== Phase 6 silence / duplicate / merge / barge / natural ==="
$PY backend/tests/test_phase6_silence_handling.py
$PY backend/tests/test_phase6_duplicate_questions.py
$PY backend/tests/test_phase6_transcript_aggregation.py
$PY backend/tests/test_semantic_domain_guard.py
$PY backend/tests/test_phase6_barge_in.py
$PY backend/tests/test_voice_turn_taking_fixes.py
$PY backend/tests/test_phase6_natural_conversation.py
$PY backend/tests/test_guards/test_interview_flow_fixes.py

echo "=== Phase 6B transcript quality ==="
$PY backend/tests/test_phase6b_transcript_quality.py

echo "=== Phase 6C reporting ==="
$PY backend/tests/test_phase6c_reporting.py

echo "=== Report v2 module ==="
$PY backend/tests/test_reporting_v2.py

echo "=== Transcript utils ==="
$PY backend/tests/test_transcript_utils.py

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
