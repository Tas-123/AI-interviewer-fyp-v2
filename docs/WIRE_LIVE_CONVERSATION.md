# Wire Live Conversation Transcript End-to-End

**Date:** 2026-07-15  
**Branch:** `uthman`  
**Why:** Commit `ec08d98` only pushed leftover modules after a hard reset; processor/serializer/client wiring was missing.

## Restored in this push

| Layer | Change |
|-------|--------|
| `interview_processor.py` | Emit user/assistant/system `conversation_event` + phase events; `_speak_to_client` |
| `interview_bot.py` | Serialize `OutputTransportMessageFrame`; greeting emits assistant bubble |
| `app.js` | Wire `conversationStore` |
| `voiceSession.js` | Handle `type: conversation_event` |
| `conversationView.js` | `message_id` / `updateMessage` / `clear` |
| `scripts/run_regression.sh` | Include `test_live_conversation_events.py` |
| Docs / README | Protocol + verification updated |

## Expected client behavior

1. Connect → Interviewer greeting bubble + audio  
2. Speak → pause → **You** bubble with finalized STT  
3. Next question → Interviewer bubble + audio  

Dialogue/scoring unchanged — outbound UI projection only.
