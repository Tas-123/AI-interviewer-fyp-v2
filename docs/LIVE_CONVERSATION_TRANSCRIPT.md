# Live Conversation Transcript — Implementation Notes

**Date:** 2026-07-14  
**Scope:** Outbound UI projection only — dialogue, evaluation, and voice turn policy unchanged.

## Goal

Show a chat-style interview transcript on the manual client in real time:

1. AI question appears as a finalized Interviewer bubble.
2. Candidate answer appears once STT + turn logic finalize it.
3. Next AI response appears, and so on.

## Design

- Separate module: [`backend/pipecat_integration/conversation/`](../backend/pipecat_integration/conversation/)
  - `events.py` — versioned wire payload builders (`schema_version: 1`)
  - `publisher.py` — binds `session_id`, wraps Pipecat `OutputTransportMessageFrame`
- [`InterviewProcessor`](../backend/pipecat_integration/interview_processor.py) emits events at turn boundaries (not inside DialogueManager).
- [`JSONSerializer`](../backend/pipecat_integration/interview_bot.py) serializes transport messages; raw TTS `TextFrame`s are **not** used for chat (avoids fragmented bubbles).
- Client: `conversationStore.js` applies events by `message_id` → `conversationView.js`.

```text
STT final → InterviewProcessor
  → conversation_event (user, final)
  → phase: thinking
  → DialogueAdapter
  → conversation_event (assistant, final)
  → TTSSpeakFrame → Cartesia → WAV audio
```

## Wire format (v1)

```json
{
  "type": "conversation_event",
  "schema_version": 1,
  "event_id": "...",
  "session_id": "...",
  "ts": "ISO-8601",
  "kind": "message",
  "role": "assistant|user|system",
  "text": "...",
  "message_id": "...",
  "turn_id": "...",
  "status": "final"
}
```

Also supported: `kind: "phase"` (`listening|thinking|speaking`), `kind: "session"` (`started`).

## Future (no core logic change)

- Interim captions: same `message_id` with `status: "interim"` then `"final"` (store already supports replace).
- Persist the event log for export / replay / search.
- Recruiter observer role with the same stream.
