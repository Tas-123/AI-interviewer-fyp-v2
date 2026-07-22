# Viva Preparation — Technical Q&A

**Project:** AI Powered Interview Simulation and Feedback Platform  
**Purpose:** Defend implementation choices verbally in the final viva / presentation.  
**How to use:** Learn the short answer first; use the “If they dig deeper” notes only when asked.

**Important corrections for examiners**
- LLM in the delivered system is **Llama 3.3 70B** via **Groq** (not Llama 3.1). If a question says “3.1”, answer with what you built and briefly correct the version.
- Primary live path is **Pipecat WebSocket on port 8765**, not the optional FastAPI text API on 8000.
- Product flow is **recruiter-primary**: invite → lobby → live adaptive voice interview → **Report V2**.

---

## A. Speech Processing & Audio Pipeline

### 1. Explain the complete voice processing pipeline from candidate speech to AI response.

**Answer:**  
Audio streams from the browser over a **WebSocket** to our Pipecat voice runtime (port **8765**). The pipeline is:

1. **Silero VAD** — detects when the candidate starts and stops speaking.  
2. **Deepgram STT (nova-2)** — converts speech to text in near real time.  
3. **InterviewProcessor → DialogueManager** — applies guards, coverage, and decision logic.  
4. **Groq LLM (Llama 3.3)** — scores / decides and generates the next interviewer utterance.  
5. **Cartesia TTS** — converts that text to speech.  
6. Audio is streamed back to the candidate over the same WebSocket.

So the “brain” is dialogue management + LLM; speech services only handle media conversion.

---

### 2. Why did you choose Deepgram over Whisper or Google Speech-to-Text?

**Answer:**  
We needed **streaming, low-latency STT** for a live interview, not batch transcription after the session. Deepgram’s **nova-2** streaming API fits Pipecat well, supports endpointing, punctuation, and keyword boosting for technical terms. Whisper is excellent for offline/batch accuracy but is less ideal as our primary live streaming STT without extra infrastructure. Google STT is viable, but Deepgram gave us a simpler streaming integration and acceptable latency for the FYP scope.

**If they dig deeper:** We also use keyword boosts (e.g. FastAPI, Python) to improve recognition of domain terms.

---

### 3. How does Speech-to-Text (STT) work internally?

**Answer (conceptual, viva-safe):**  
STT is an acoustic + language model pipeline: audio features are mapped to likely phonemes/tokens, then decoded into words using a language model that prefers fluent English. Modern cloud STT (like Deepgram) runs this as a **streaming** model: partial hypotheses update as audio arrives, and endpointing decides when an utterance is complete. Our system consumes the final transcript turn and feeds it into dialogue management.

---

### 4. What challenges arise when recognizing different accents and pronunciations?

**Answer:**  
Accents change phoneme realization, speaking rate, and stress patterns, which increases word-error rate. Technical vocabulary and names are especially fragile. We mitigate with: English-focused config, punctuation/smart formatting, keyword boosting, **transcript-quality** checks, and evaluation reweighting when the transcript looks noisy so communication scores are not unfairly punished by STT errors.

**Honest limit:** Full accent-robust multilingual ASR was out of scope.

---

### 5. How does your system handle background noise during interviews?

**Answer:**  
At the signal level, **VAD** (Silero) with confidence/volume thresholds reduces non-speech triggering. At the language level, **guards** and transcript-quality logic catch empty/fragmented/noisy text. We also nudge or rephrase on prolonged silence rather than inventing answers. We do **not** claim advanced noise-cancellation DSP; quiet environments and a decent mic still matter.

---

### 6. Explain the role of Text-to-Speech (TTS) in your platform.

**Answer:**  
TTS is the interviewer “voice.” After DialogueManager + LLM produce the next question or instruction, **Cartesia TTS** synthesizes audio so the candidate hears a natural spoken interviewer. The same TTS path is also used for **pre-interview lobby instructions**, so the experience stays voice-consistent before the interview starts.

---

### 7. Why was Cartesia selected instead of Google TTS or Amazon Polly?

**Answer:**  
Cartesia integrates cleanly with our **Pipecat** realtime pipeline and gave us low-latency streaming TTS suitable for turn-taking. Google/Amazon Polly are strong products, but Cartesia matched our streaming architecture and development speed for the FYP. Voice identity is configured via a Cartesia voice ID in environment settings.

---

### 8. How do you minimize latency in real-time voice communication?

**Answer:**  
Several choices reduce lag:

- **WebSockets** for bidirectional audio/control (no HTTP request-per-chunk).  
- **Streaming STT/TTS** instead of full-file batch.  
- **Groq** for fast LLM inference.  
- Tight VAD settings (e.g. stop seconds ~0.9) so turns end promptly.  
- Keeping dialogue logic in-process with the voice bot for the live path.

Latency is end-to-end: network + VAD + STT + LLM + TTS. We optimize each stage rather than only the LLM.

---

### 9. What happens if speech recognition incorrectly transcribes the candidate's answer?

**Answer:**  
Wrong transcripts can cause bad follow-ups or unfair scores. We handle this with:

- **Incomplete / fragment guards** (merge tail fragments, redirect incomplete text).  
- **Echo guard** (ignore bot hearing itself).  
- **Transcript quality** scoring; if noisy, evaluation weights shift toward more technical dimensions.  
- Short/empty turns trigger **probe / clarify** behaviour instead of hard scoring.

We do not claim perfect ASR; we design the dialogue and scoring to be **robust to ASR errors**.

---

### 10. How would you support multilingual interviews?

**Answer (future / design):**  
We would configure STT/TTS language codes, provide role prompts in the target language, ensure LLM prompts specify response language, and validate evaluation rubrics per language. We might use language detection at lobby time. **Today the delivered system is English-focused** (`language=en` for STT). Multilingual was intentionally out of scope.

---

## B. Large Language Models (LLMs)

### 11. Why did you choose Llama 3.1 through Groq instead of GPT-4 or Gemini?

**Answer:**  
**Correction:** we use **Llama 3.3 70B versatile via Groq**, not 3.1.  

Reasons for Groq + Llama:

- **Low latency** critical for live voice turns.  
- Strong instruction following for structured JSON evaluation and short interviewer questions.  
- Cost/control suitable for an academic prototype.  
- Easy API swap later (model name is config-driven).

GPT-4 / Gemini are excellent, but Groq’s speed fit the realtime interview UX better for our constraints.

---

### 12. Explain how an LLM generates interview questions.

**Answer:**  
The LLM does **not** freely chat. DialogueManager chooses an **action** (`intro`, `ask`, `followup`, `closing`) from coverage + decision engines. The LLM receives:

- role / blueprint domain,  
- conversation context,  
- last candidate answer / evaluation signals,  
- explicit instructions (short question, stay on domain, no leakage of scores).

It then generates the next interviewer utterance under those constraints. Adaptive behaviour comes from **policy + LLM**, not LLM alone.

---

### 13. What is prompt engineering, and how is it used in your system?

**Answer:**  
Prompt engineering is designing instructions, context, and output format so the model behaves reliably. We use it for:

- interviewer persona and role-specific blueprints,  
- constrained question generation,  
- **rubric-based JSON evaluation**,  
- guardrails (no answer keys, no unfair pressure, stay professional).

Different temperatures: roughly **0.2** for evaluation (more deterministic) and **~0.4** for question phrasing (slightly more natural).

---

### 14. How do you maintain interview context throughout the conversation?

**Answer:**  
An in-memory **InterviewContext** (via SessionService) stores state: current domain, turn counts, question history, evaluations, coverage progress, and flags (e.g. skips). Each turn, DialogueManager reads/updates that context before calling the LLM. The LLM sees a **controlled context window**, not the entire raw audio history.

---

### 15. How do you prevent hallucinations in LLM-generated questions?

**Answer:**  
We reduce hallucination risk by:

- grounding questions in **role blueprints / domains**,  
- using decision/coverage policy so the model isn’t free-form,  
- short max tokens for questions,  
- guards against meta/off-topic drift,  
- not asking the model to invent company facts or candidate CV details it doesn’t have.

Hallucinations can’t be eliminated 100%; we constrain generation so wrong “facts” are less likely and less harmful.

---

### 16. Explain the difference between Retrieval-Augmented Generation (RAG) and prompt-based generation.

**Answer:**  
**Prompt-based:** the model answers from the prompt + its pretrained knowledge.  
**RAG:** before generation, the system retrieves documents from a knowledge base and inserts them into the prompt.

Our interview questions are mostly **prompt + policy + session context**. We did **not** build a full RAG knowledge base for interviewing. RAG would help if we needed company handbook / JD-specific grounded questions at scale.

---

### 17. Why didn't you fine-tune the LLM?

**Answer:**  
Fine-tuning needs large high-quality interview datasets, compute, and continuous MLOps. For an FYP delivering an end-to-end product, **prompting + structured evaluation + dialogue policy** gave better ROI. Groq-hosted Llama already performs well enough for constrained interviewer behaviour. Fine-tuning remains a valid future improvement for rubric calibration.

---

### 18. What parameters influence the creativity of LLM responses?

**Answer:**  
Mainly **temperature** (higher = more random/creative), **top-p / top-k** (nucleus/candidate sampling), **max tokens**, and the prompt itself. We keep evaluation temperature low for consistency and question generation moderately higher for natural wording, with tight token limits so questions stay concise.

---

### 19. How do you prevent the LLM from asking repetitive questions?

**Answer:**  
Repetition is controlled by **coverage policy** (advance domains, limits on probes/follow-ups per domain), question history in context, and decision types like ADVANCE vs PROBE. Follow-up caps (e.g. max context follow-ups) and per-domain probe limits stop the model from looping on the same angle.

---

### 20. How would you evaluate the quality of AI-generated interview questions?

**Answer:**  
Mix of:

- **Coverage completeness** (domains hit),  
- human expert review (relevance, difficulty, bias),  
- candidate/recruiter feedback,  
- downstream signal quality (did answers allow fair scoring?),  
- regression tests on dialogue decisions.

Automated “question quality score” alone is insufficient; human review is essential for hiring use cases.

---

## C. Dialogue Management

### 21. Explain the role of the Dialogue Management Engine.

**Answer:**  
DialogueManager is the **orchestrator**. It prepares transcripts, runs the **guard pipeline**, consults **decision/coverage engines**, calls evaluation/question generation when needed, updates session state, and returns the next bot action. Speech services convert media; DialogueManager decides **interview behaviour**.

---

### 22. How does the system decide the next interview question?

**Answer:**  
Roughly:

1. Guards may short-circuit (echo, IDK, off-topic, incomplete).  
2. Otherwise evaluate the answer (when appropriate).  
3. Decision engine chooses **PROBE / ADVANCE / stay / closing** using score, coverage, and limits.  
4. Coverage engine picks the next **blueprint domain** if advancing.  
5. LLM generates the actual wording for that action.

So “next question” is a **policy decision first**, generation second.

---

### 23. What happens if the candidate gives an irrelevant answer?

**Answer:**  
**Intent/Domain guards** detect off-topic or skip intents and **redirect** back to the current question/domain instead of advancing coverage. We prefer staying on the assessment goal over following the candidate into unrelated chat. Meta requests (e.g. “change topic”) are handled as control intents, not as evidence of skill.

---

### 24. How do you detect when the interview should end?

**Answer:**  
Ending is policy-driven: domains covered, probe limits reached with no next domain, or a **safety turn ceiling** (around 28 turns). Then the system moves to **closing / wrap-up**. Report completeness also considers wrap-up plus enough evaluated turns and coverage for a “complete” Report V2.

---

### 25. Explain finite-state dialogue systems versus LLM-driven dialogue.

**Answer:**  
**Finite-state:** fixed states/transitions (rigid, predictable, limited adaptivity).  
**Pure LLM chat:** flexible but hard to control, evaluate, and audit.  

**Our hybrid:** structured state (domains, turns, coverage) + LLM for language and rubric scoring. That gives adaptivity with controllable assessment coverage.

---

### 26. How is interview history maintained during a session?

**Answer:**  
In **InterviewContext** held by SessionService for the live voice process: questions asked, answers/evals, domain progress, counters, and flags. The client also receives live conversation events for the transcript UI. Note: session store is **in-process** for the voice runtime (important for scaling discussion).

---

### 27. Can candidates interrupt the AI interviewer? How is this handled?

**Answer:**  
Yes — we support **barge-in**. The client detects candidate speech energy while the bot is talking and sends an interrupt signal. The server uses voice-turn policy with a short minimum bot-speak time and echo cooldown so we don’t cut the bot from its own audio or tiny noise spikes.

---

### 28. How would you recover from communication failures during an interview?

**Answer (current + design):**  
WebSocket reconnect UX, keep session tokens/invite context, resume from last InterviewContext if still in memory, and regenerate last bot prompt if needed. For production we would add durable session persistence (Redis/DB), heartbeat timeouts, and explicit “resume interview” flows. Today, process restart can lose in-memory session state — we should state that honestly.

---

### 29. How do you avoid infinite conversation loops?

**Answer:**  
Hard limits: max turns, max probes per domain, max follow-ups, max skips, coverage completion → closing. Guards prevent endless meta/off-topic loops by redirecting. Without these ceilings, an LLM could chat forever.

---

### 30. How would you support follow-up questions based on candidate responses?

**Answer:**  
Already implemented in adaptive mode: low scores (e.g. ≤ ~2.5) can trigger a **PROBE** follow-up (rationale / elaboration / clarification). Follow-ups are capped so they deepen one domain without blocking overall coverage.

---

## D. Backend Architecture & APIs

### 31. Why did you choose FastAPI instead of Flask or Django?

**Answer:**  
FastAPI gives native **async**, automatic OpenAPI docs, Pydantic validation, and high performance for API-style services. Django is heavier (batteries-included web apps/admin). Flask is minimal but needs more assembly for validation/async. For recruiter dashboard + optional REST brain, FastAPI fit best.

---

### 32. Why is WebSocket preferred over REST APIs for this application?

**Answer:**  
Live interviews need **continuous bidirectional audio and control events**. REST is request/response and poor for streaming PCM frames and barge-in interrupts. WebSockets keep one persistent connection for STT input, TTS output, and JSON events. REST remains useful for **invites, auth, and reports** (recruiter dashboard / report helper).

---

### 33. Explain the complete request-response lifecycle in your system.

**Answer (recruitment path):**  

1. Recruiter logs into dashboard (**8001**), selects role, creates invite.  
2. Candidate opens invite, completes lobby (**3000**).  
3. Browser connects to voice WebSocket (**8765**).  
4. Each spoken turn: VAD→STT→DialogueManager→LLM→TTS→audio back.  
5. On completion, **Report V2** is generated; recruiter fetches via report HTTP (**8766**) / dashboard.

Optional text/API testing can use FastAPI on **8000**, but that is not the primary delivered UX.

---

### 34. What is asynchronous programming, and why is it important here?

**Answer:**  
Async lets the server handle many I/O-bound tasks (network, API calls) without blocking a thread per wait. Voice bots call STT/LLM/TTS concurrently with connection handling. Without async, realtime pipelines stall on every external API call.

---

### 35. How does FastAPI improve application performance?

**Answer:**  
Async endpoints, efficient Starlette stack, less boilerplate overhead, and typed validation that fails fast. Performance also comes from architecture (WebSockets + Pipecat), not FastAPI alone. FastAPI helps the **HTTP control plane** stay lean.

---

### 36. Explain session management during interviews.

**Answer:**  
Live interview state lives in **SessionService / InterviewContext** inside the voice process. Recruiter auth uses a **signed session cookie** (`recruiter_session` via Starlette SessionMiddleware). Invites are stored as tokens in a local JSON store. Voice sessions and recruiter HTTP sessions are separate concerns.

---

### 37. How do you authenticate interview sessions?

**Answer:**  
Candidates enter through a **recruiter-generated invite token** (`secrets.token_urlsafe`). Resolving a valid invite authorizes starting the lobby/interview flow. Recruiters authenticate with configured credentials and a signed session cookie. We should not oversell JWT microservice auth — invite token + recruiter session is the delivered model.

---

### 38. How do you protect APIs from unauthorized access?

**Answer:**  
Recruiter routes require login/session. Invite creation is authenticated. Public invite resolve is intentionally limited. Secrets live in environment variables (API keys for Groq/Deepgram/Cartesia). For production hardening we would add rate limiting, HTTPS everywhere, stronger secret management, CSRF protections as needed, and audit logs.

---

### 39. How would you scale your backend for thousands of simultaneous interviews?

**Answer:**  
Horizontally scale voice workers behind a load balancer; move session state to **Redis**; isolate STT/LLM/TTS quotas; use queues for report generation; separate recruiter API from realtime workers; autoscaling; observability (metrics/tracing); possibly WebRTC SFU for media at very large scale. Current in-process sessions are the main scalability bottleneck to call out.

---

### 40. Explain how Pipecat integrates different AI services into one pipeline.

**Answer:**  
Pipecat composes **processors/services** into a directed pipeline: transport ↔ VAD ↔ STT ↔ our custom interview processor ↔ TTS. Each frame of audio/text flows through stages. Our custom processor is where DialogueManager plugs into that media graph, so vendor STT/TTS and our interview logic stay modular.

---

## E. Candidate Evaluation & AI Assessment

### 41. How does the system evaluate candidate responses?

**Answer:**  
After relevant turns, an LLM evaluator scores the answer against a **multi-dimension rubric** (method roughly `llm_rubric_ensemble_lite_v1`, with optional rethink in mid bands). Scores update session aggregates and influence PROBE vs ADVANCE. Final Report V2 summarizes the interview.

---

### 42. What evaluation criteria are used to score answers?

**Answer:**  
Weighted dimensions (sum to 1.0), including approximately:

- Structure (0.25)  
- Result orientation (0.20)  
- Ownership (0.20)  
- Leadership (0.15)  
- Clarity (0.10)  
- Confidence (0.10)  

**Hire bands:** ≥4.0 Strong Hire, ≥3.0 Hire, ≥2.5 Borderline, else No Hire.

Clarity/confidence are **text-proxy behavioural signals**, not SER/facial emotion models.

---

### 43. How do you ensure fairness in AI-based evaluation?

**Answer:**  
Structured rubric (same criteria per candidate), coverage-first interviewing so everyone faces similar domains, transcript-noise reweighting, guards against scoring empty/echo turns, and report limitations notes. Fairness is improved, not guaranteed. We avoid biometric emotion scoring that can encode bias.

---

### 44. How would you validate the correctness of AI-generated scores?

**Answer:**  
Human inter-rater studies: recruiters score the same transcripts blind; compare correlation with AI; calibrate rubric prompts; maintain a golden set regression suite. Our human-study export path supports this direction. Production would require ongoing monitoring for drift and subgroup fairness.

---

### 45. Explain how structured interview reports are generated.

**Answer:**  
On wrap-up/completion, reporting builds **Report V2** (`REPORT_VERSION=2.0`) with overall recommendation, dimension scores, coverage, transcript-derived evidence, and status (`complete|partial|incomplete|aborted`). HTML rendering and recruiter dashboard access make it usable for hiring decisions. Complete reports expect wrap-up + sufficient evaluated turns + full coverage.

---

### 46. What happens if the candidate remains silent for a long time?

**Answer:**  
Voice turn policy uses timed prompts: roughly an **8s silence nudge**, then a **15s rephrase** path, rather than hanging forever or auto-scoring silence as a full answer. Extended non-response can lead to incomplete/aborted interview outcomes depending on progress.

---

### 47. How do you detect incomplete or irrelevant answers?

**Answer:**  
**IncompleteGuard** (short/truncated transcripts, tail fragments), **IntentGuard** / **DomainGuard** (skip, off-topic, clarification), and short-answer heuristics (very short replies may probe without full scoring). Relevance is primarily policy/guard-driven, not a separate ML classifier.

---

### 48. How would you compare AI evaluation with human interviewer evaluation?

**Answer:**  
Run paired studies: same session transcript scored by humans and AI; measure agreement (correlation, MAE, hire-band match); analyze disagreements by dimension; refine prompts/weights. AI should assist humans, not silently replace accountability in high-stakes hiring.

---

### 49. What ethical concerns arise in AI-driven interviews, and how would you address them?

**Answer:**  
Bias/discrimination, opacity, candidate consent, data privacy, over-reliance on ASR errors, and stress from automated judgment. Mitigations: transparent purpose, human-in-the-loop final decisions, rubric documentation, data retention limits, no covert biometric emotion scoring, accessible alternatives, and clear reporting of system limits.

---

### 50. If deployed by a multinational for thousands of interviews daily — what would you improve?

**Answer (structured “senior” response):**  

**Architecture:** split realtime voice workers, API gateway, Redis/DB sessions, object storage for audio/reports, autoscaling, multi-region failover.  

**AI:** model routing, evaluation calibration per role/locale, optional RAG for JD grounding, human review queues for borderline bands, continuous eval datasets.  

**Security/compliance:** SSO, encryption in transit/rest, secrets vault, PII minimization, GDPR/local labour-law workflows, audit trails, retention policies, red-team testing.  

**Reliability:** SLOs, circuit breakers on STT/LLM/TTS vendors, graceful degradation (text fallback), chaos testing.  

**Fairness:** subgroup monitoring, accessibility, multilingual support, recruiter override always available.  

**Ops:** observability, cost controls on tokens/audio minutes, feature flags, staged rollouts.

This shows you understand the gap between an FYP prototype and production hiring infrastructure.

---

## Quick “don’t get trapped” lines

| Topic | Safe line |
|--------|-----------|
| Llama version | “We use **Llama 3.3 70B on Groq** for latency; the question’s 3.1 label is outdated relative to our build.” |
| Emotion AI | “We did **not** deliver SER/facial analysis; clarity/confidence are text rubric proxies.” |
| Self-practice | “Out of scope; product is recruiter-led live interviews.” |
| Port 8000 | “Optional REST/testing; live interviews use **8765**.” |
| Perfect accuracy | “ASR and LLM are probabilistic; we add guards, limits, and human-readable reports.” |
| Scaling today | “In-memory sessions work for demo; production needs shared state and horizontal workers.” |

---

## Suggested 30-second architecture closer (memorize)

> “Our platform is a modular realtime system: recruiter invites on FastAPI, candidate browser client, Pipecat WebSocket voice pipeline with Silero VAD, Deepgram STT, DialogueManager policy, Groq Llama 3.3 for adaptive questioning and rubric scoring, Cartesia TTS, and Report V2 for structured feedback. The key research contribution is controlled adaptive dialogue—not unconstrained chatbot interviewing.”

---

*Prepared for BS CS FYP viva defense. Align spoken answers with the report and demo; if a detail differs on your branch, prefer what you can show running.*
