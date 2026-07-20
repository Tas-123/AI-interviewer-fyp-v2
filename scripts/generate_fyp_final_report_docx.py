"""
Generate FYP Final Report V04 (DOCX) from current implementation snapshot.
Run: python scripts/generate_fyp_final_report_docx.py
Output: docs/FYP_FINAL_REPORT_V04.docx
"""

from __future__ import annotations

import textwrap
from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
ASSETS = DOCS / "fyp_report_v04_assets"
OUT_DOCX = DOCS / "FYP_FINAL_REPORT_V04.docx"
SNAPSHOT_COMMIT = "612ae79"
SNAPSHOT_BRANCH = "uthman"


def _ensure_assets():
    ASSETS.mkdir(parents=True, exist_ok=True)


def _draw_box(ax, xy, w, h, text, fc="#e8f4fc", ec="#1e3a5f", fontsize=8):
    box = FancyBboxPatch(
        xy, w, h, boxstyle="round,pad=0.02,rounding_size=0.02",
        linewidth=1.2, edgecolor=ec, facecolor=fc,
    )
    ax.add_patch(box)
    ax.text(xy[0] + w / 2, xy[1] + h / 2, text, ha="center", va="center",
            fontsize=fontsize, wrap=True)


def _arrow(ax, p1, p2):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle="->", mutation_scale=12,
                                 linewidth=1.2, color="#334155"))


def fig_overall_architecture(path: Path):
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.axis("off")
    ax.set_title("Figure 3.1 — Overall System Architecture (Runtime)", fontsize=11, weight="bold")

    _draw_box(ax, (0.3, 4.2), 2.4, 1.0, "Manual Client\n(HTML/JS)\nPre-interview lobby", "#dbeafe")
    _draw_box(ax, (3.5, 4.5), 2.8, 0.7, "Pipecat Voice Bot\nWS :8765", "#ccfbf1")
    _draw_box(ax, (3.5, 3.2), 2.8, 0.7, "Report HTTP\n:latest-report\n:latest-report.html :8766", "#ccfbf1")
    _draw_box(ax, (7.0, 4.2), 2.5, 1.0, "FastAPI REST\n:8000\n(testing / reports)", "#fef3c7")

    _draw_box(ax, (3.2, 1.5), 3.4, 1.2, "SessionService → DialogueManager\nGuards · Eval · Decision · LLM", "#f1f5f9")
    _draw_box(ax, (0.5, 0.2), 2.2, 0.9, "Deepgram STT\nSilero VAD", "#fce7f3")
    _draw_box(ax, (3.5, 0.2), 2.2, 0.9, "Groq LLM\nLlama 3.3 70B", "#fce7f3")
    _draw_box(ax, (6.5, 0.2), 2.2, 0.9, "Cartesia TTS", "#fce7f3")
    _draw_box(ax, (7.2, 1.5), 2.3, 1.2, "Report v2\nJSON + HTML\nreports/", "#dcfce7")

    _arrow(ax, (2.7, 4.7), (3.5, 4.85))
    _arrow(ax, (2.7, 4.5), (3.5, 3.55))
    _arrow(ax, (6.3, 4.85), (7.0, 4.7))
    _arrow(ax, (4.9, 3.2), (4.9, 2.7))
    _arrow(ax, (4.0, 1.5), (1.6, 1.1))
    _arrow(ax, (5.0, 1.5), (4.6, 1.1))
    _arrow(ax, (6.0, 1.5), (7.5, 1.1))
    _arrow(ax, (6.5, 2.1), (7.2, 2.1))

    fig.tight_layout()
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def fig_voice_pipeline(path: Path):
    fig, ax = plt.subplots(figsize=(10, 2.8))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 2.5)
    ax.axis("off")
    ax.set_title("Figure 4.1 — Real-Time Voice Processing Pipeline", fontsize=11, weight="bold")
    labels = [
        "Browser\nMic PCM",
        "WebSocket\n:8765",
        "Silero\nVAD",
        "Deepgram\nSTT",
        "Interview\nProcessor",
        "Dialogue\nAdapter",
        "Dialogue\nManager",
        "Groq\nEval",
        "Cartesia\nTTS",
        "Browser\nSpeaker",
    ]
    x = 0.15
    w = 0.85
    for i, lab in enumerate(labels):
        _draw_box(ax, (x + i * 0.95, 0.8), w, 1.0, lab, fontsize=7)
        if i < len(labels) - 1:
            _arrow(ax, (x + i * 0.95 + w, 1.3), (x + (i + 1) * 0.95, 1.3))
    fig.tight_layout()
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def fig_guard_pipeline(path: Path):
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.set_xlim(0, 8)
    ax.set_ylim(0, 4)
    ax.axis("off")
    ax.set_title("Figure 4.2 — Pre-Evaluation Guard Pipeline (first trigger wins)", fontsize=11, weight="bold")
    guards = ["Echo", "Meta", "IDK", "Intent", "Incomplete", "Domain"]
    y = 2.5
    for i, g in enumerate(guards):
        _draw_box(ax, (0.4 + i * 1.2, y), 1.0, 0.7, g, fontsize=8)
        if i < len(guards) - 1:
            _arrow(ax, (1.4 + i * 1.2, y + 0.35), (0.4 + (i + 1) * 1.2, y + 0.35))
    _draw_box(ax, (2.5, 0.8), 3.0, 0.8, "Evaluator + EvaluationPipeline\n(primary + optional rethink)", "#dcfce7")
    _draw_box(ax, (2.5, 0.1), 3.0, 0.55, "DecisionEngine → LLMAdapter → TTS", "#fef3c7")
    _arrow(ax, (4.0, 2.5), (4.0, 1.6))
    _arrow(ax, (4.0, 0.8), (4.0, 0.65))
    ax.text(0.4, 3.5, "Transcript in", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def fig_report_flow(path: Path):
    fig, ax = plt.subplots(figsize=(9, 3.5))
    ax.set_xlim(0, 9)
    ax.set_ylim(0, 3.5)
    ax.axis("off")
    ax.set_title("Figure 4.3 — Report Generation and Presentation Flow", fontsize=11, weight="bold")
    steps = [
        ("WS disconnect\nor natural end", 0.3),
        ("get_final_report\nanalytics + sanitize", 2.0),
        ("build_report_v2", 3.7),
        ("save JSON\n+ HTML", 5.4),
        ("Candidate:\nthank-you +\nlink", 7.1),
    ]
    for text, x in steps:
        _draw_box(ax, (x, 1.2), 1.5, 1.1, text, fontsize=7)
    for i in range(len(steps) - 1):
        x1 = steps[i][1] + 1.5
        x2 = steps[i + 1][1]
        _arrow(ax, (x1, 1.75), (x2, 1.75))
    _draw_box(ax, (5.4, 0.1), 1.5, 0.75, "Recruiter HTML\n(FYP demo)", "#dcfce7", fontsize=7)
    _arrow(ax, (6.15, 1.2), (6.15, 0.85))
    fig.tight_layout()
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def fig_lobby_flow(path: Path):
    fig, ax = plt.subplots(figsize=(9, 2.5))
    ax.set_xlim(0, 9)
    ax.set_ylim(0, 2.5)
    ax.axis("off")
    ax.set_title("Figure 4.4 — Pre-Interview Lobby and Session Handshake", fontsize=11, weight="bold")
    steps = ["Welcome\n(name/resume)", "Connect WS\n(instructions)", "Cartesia\nspoken lines", "Ready\n+ mic", "start\npayload", "Live\ninterview"]
    for i, s in enumerate(steps):
        _draw_box(ax, (0.2 + i * 1.45, 0.7), 1.25, 1.0, s, fontsize=7)
        if i < len(steps) - 1:
            _arrow(ax, (1.45 + i * 1.45, 1.2), (0.2 + (i + 1) * 1.45, 1.2))
    fig.tight_layout()
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def fig_decision_flow(path: Path):
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.set_xlim(0, 7)
    ax.set_ylim(0, 4)
    ax.axis("off")
    ax.set_title("Figure 5.1 — Adaptive Decision Flow (PROBE / ADVANCE / WRAPUP)", fontsize=11, weight="bold")
    _draw_box(ax, (2.5, 3.0), 2.0, 0.7, "Scored answer", "#dbeafe")
    _draw_box(ax, (2.2, 1.9), 2.6, 0.7, "DecisionEngine", "#f1f5f9")
    _draw_box(ax, (0.3, 0.5), 1.5, 0.7, "PROBE\n(follow-up)", "#fef3c7")
    _draw_box(ax, (2.75, 0.5), 1.5, 0.7, "ADVANCE\n(next domain)", "#dcfce7")
    _draw_box(ax, (5.2, 0.5), 1.5, 0.7, "WRAPUP\n(close)", "#fee2e2")
    _arrow(ax, (3.5, 3.0), (3.5, 2.6))
    _arrow(ax, (2.8, 1.9), (1.05, 1.2))
    _arrow(ax, (3.5, 1.9), (3.5, 1.2))
    _arrow(ax, (4.2, 1.9), (5.95, 1.2))
    fig.tight_layout()
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def generate_diagrams() -> dict[str, Path]:
    _ensure_assets()
    mapping = {
        "fig_3_1": ASSETS / "fig_3_1_overall_architecture.png",
        "fig_4_1": ASSETS / "fig_4_1_voice_pipeline.png",
        "fig_4_2": ASSETS / "fig_4_2_guard_pipeline.png",
        "fig_4_3": ASSETS / "fig_4_3_report_flow.png",
        "fig_4_4": ASSETS / "fig_4_4_lobby_flow.png",
        "fig_5_1": ASSETS / "fig_5_1_decision_flow.png",
    }
    fig_overall_architecture(mapping["fig_3_1"])
    fig_voice_pipeline(mapping["fig_4_1"])
    fig_guard_pipeline(mapping["fig_4_2"])
    fig_report_flow(mapping["fig_4_3"])
    fig_lobby_flow(mapping["fig_4_4"])
    fig_decision_flow(mapping["fig_5_1"])
    return mapping


def _style_doc(doc: Document):
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(12)
    for level in range(1, 4):
        h = doc.styles[f"Heading {level}"]
        h.font.name = "Times New Roman"
        h.font.bold = True


def _add_para(doc, text: str, bold=False, align=None):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = bold
    if align:
        p.alignment = align
    return p


def _add_body(doc, text: str):
    for para in textwrap.dedent(text).strip().split("\n\n"):
        doc.add_paragraph(para.strip())


def _add_figure(doc, img: Path, caption: str):
    doc.add_picture(str(img), width=Inches(6.2))
    cap = doc.add_paragraph(caption)
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.runs[0].italic = True


def _add_table(doc, headers: list[str], rows: list[list[str]]):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = h
    for r_idx, row in enumerate(rows):
        cells = table.rows[r_idx + 1].cells
        for c_idx, val in enumerate(row):
            cells[c_idx].text = str(val)
    doc.add_paragraph()


def build_document(figs: dict[str, Path]) -> Document:
    doc = Document()
    _style_doc(doc)

    # Title block
    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = t.add_run("AI-Driven Real-Time Interview Platform\n")
    r.bold = True
    r.font.size = Pt(16)
    t.add_run("\nFinal Year Project Report — Version 4.0\n").bold = True
    t.add_run(f"\nImplementation snapshot: branch {SNAPSHOT_BRANCH}, commit {SNAPSHOT_COMMIT}\n")
    t.add_run(f"Generated: {date.today().isoformat()}\n\n")
    t.add_run("Hamdard University Islamabad\n")
    t.add_run("Supervisors: Engr. Usman Javed; Engr. M. Abdullah Umar\n")
    t.add_run("Team: Muhammad Usman Sajid, Taimur Ali Sakhawat, "
              "Eimaan Khan Bangash, Bismah Khan Bangash\n")
    doc.add_page_break()

    doc.add_heading("Abstract", level=1)
    _add_body(doc, """
    Artificial Intelligence has transformed recruitment, yet many interview tools remain text-based,
    scripted, or unable to adapt follow-ups to candidate answers in real time. This Final Year Project
    delivers an AI-driven voice interview platform for Junior AI Engineer candidates: the candidate speaks
    naturally in a browser; the system transcribes speech, manages a ten-domain structured interview,
    evaluates answers with a transparent six-dimension LLM rubric, and produces recruiter-oriented Report v2
    artifacts (JSON and HTML).

    The implementation integrates Pipecat for real-time orchestration, Deepgram nova-2 for streaming speech-to-text,
    Groq Llama 3.3 70B for question generation and evaluation, Cartesia for text-to-speech, and Silero voice activity
    detection. A guarded dialogue pipeline (echo, meta, IDK, intent, incomplete, domain) prevents non-answers from
    being scored. CoverageEngine and DecisionEngine coordinate PROBE and ADVANCE actions until the interview blueprint
    is covered or a safety turn ceiling is reached.

    Reporting separates candidate and recruiter experiences: after the session the candidate sees a professional
    thank-you message; detailed assessment is available as HTML for recruiters (FYP demo stand-in for a future dashboard).
    Evaluation calibration (July 2026) aligned hire thresholds and persona wording for junior voice interviews.
    Multimodal emotion recognition, Docker production deployment, and multi-tenant scaling were deferred to preserve
    a reliable end-to-end voice demo suitable for academic evaluation.
    """)

    doc.add_heading("Dedication", level=1)
    _add_body(doc, """
    We dedicate this project to our parents and families whose support made this work possible, and to our teachers
    who guided us throughout the Final Year Project journey at Hamdard University Islamabad.
    """)

    doc.add_heading("Acknowledgments", level=1)
    _add_body(doc, """
    We express sincere gratitude to our supervisors Engr. Usman Javed and Engr. M. Abdullah Umar for guidance,
    feedback, and support throughout this project. We thank Hamdard University Islamabad faculty and administration
    for providing an environment conducive to research and development, and our families and colleagues for
    encouragement during the degree program.
    """)

    doc.add_heading("Project Brief", level=1)
    _add_table(doc, ["Field", "Detail"], [
        ["Project name", "AI-Driven Real-Time Interview Platform"],
        ["Repository", "AI-interviewer-fyp-v2"],
        ["Primary branch", SNAPSHOT_BRANCH],
        ["Objective", "Adaptive voice technical interviews with automated evaluation and recruiter reports"],
        ["Tools", "Python, FastAPI, Pipecat, Deepgram, Groq, Cartesia, HTML/CSS/JS, GitHub, PostgreSQL (optional)"],
    ])

    doc.add_paragraph(
        "Note: In Microsoft Word, update the Table of Contents via References → Table of Contents → Update Table "
        "after opening this document."
    )

    doc.add_heading("List of Abbreviations", level=1)
    _add_table(doc, ["Abbreviation", "Meaning"], [
        ["ASR", "Automatic Speech Recognition"],
        ["LLM", "Large Language Model"],
        ["STT", "Speech-to-Text"],
        ["TTS", "Text-to-Speech"],
        ["VAD", "Voice Activity Detection"],
        ["WS", "WebSocket"],
        ["API", "Application Programming Interface"],
        ["JSON", "JavaScript Object Notation"],
        ["FYP", "Final Year Project"],
    ])

    doc.add_heading("List of Figures", level=1)
    _add_table(doc, ["Figure", "Title"], [
        ["3.1", "Overall system architecture (runtime entry points)"],
        ["4.1", "Real-time voice processing pipeline"],
        ["4.2", "Pre-evaluation guard pipeline"],
        ["4.3", "Report generation and presentation flow"],
        ["4.4", "Pre-interview lobby and session handshake"],
        ["5.1", "Adaptive decision flow (PROBE / ADVANCE / WRAPUP)"],
    ])
    doc.add_paragraph(
        "Replace placeholder screenshots in Appendix C with captures from your demo machine before submission."
    )

    doc.add_page_break()

    # CHAPTER 1
    doc.add_heading("Chapter 1 — Introduction", level=1)
    _add_body(doc, """
    Recruitment for technical roles increasingly relies on remote hiring and high application volumes.
    Human-conducted interviews remain the gold standard for assessing communication and problem-solving,
    but they are costly, difficult to scale, and subject to inconsistency. AI-assisted interviewing can
    standardize structure and evaluation if the system supports natural voice interaction, adaptive follow-ups,
    and honest reporting limitations.

    This project implements a real-time voice interviewer that simulates a senior engineer interviewing a
    junior candidate. Unlike static question banks, the platform evaluates each answer before deciding whether
    to probe deeper or advance across a fixed Junior AI Engineer blueprint (ten domains). The product demo path
    is a Pipecat WebSocket server with a modular browser client; FastAPI provides REST endpoints for testing and
    report retrieval.
    """)
    doc.add_heading("1.1 Problem Statement", level=2)
    _add_body(doc, """
    Existing tools often fail on latency, turn-taking, scoring of non-answers (echoes, meta-requests, IDK),
    unfair penalization due to speech recognition noise, and misleading “complete” reports after partial coverage.
    This project addresses these gaps with ordered guards, transcript fairness reweighting, coverage-first wrap-up,
    tiered Report v2 completion types, and live voice hardening (barge-in, silence handling, tail-fragment safety).
    """)
    doc.add_heading("1.2 Objectives and Scope", level=2)
    _add_table(doc, ["ID", "Objective", "Status"], [
        ["O1", "Real-time voice interview simulation", "Achieved"],
        ["O2", "Adaptive questioning across blueprint domains", "Achieved"],
        ["O3", "Interruption / barge-in handling", "Achieved with limits (RMS + VAD grace)"],
        ["O4", "Behavioural / communication evaluation", "Partial — text rubric proxies; no SER/facial models"],
        ["O5", "Automated recruiter reporting", "Achieved — Report v2 JSON + HTML"],
        ["O6", "Evaluation methodology and regression tests", "Achieved"],
    ])
    doc.add_heading("1.3 Organization of Report", level=2)
    _add_body(doc, """
    Chapter 2 reviews related work. Chapter 3 explains underlying technologies. Chapter 4 presents methodology
    and architecture. Chapter 5 discusses results. Chapter 6 details design and implementation. Chapter 7 concludes
    with limitations and future work. Appendices list configuration and report components.
    """)

    doc.add_page_break()

    # CHAPTER 2 — condensed literature
    doc.add_heading("Chapter 2 — Literature Review", level=1)
    _add_body(doc, """
    Prior research spans resume screening chatbots, LLM conversational interview agents, ASR-based mock interviews,
    adaptive dialogue managers, and multimodal behavioural analysis. Common gaps include lack of real-time voice loops,
    weak follow-up adaptivity, limited guardrails for spoken meta-dialogue, and insufficient recruiter-facing structured reports.

    Table 2.1 summarizes representative approaches. Our delivered system emphasizes voice robustness, deterministic guard
    ordering, blueprint coverage policy, and auditable LLM rubric scoring rather than multimodal emotion fusion.
    """)
    _add_table(doc, ["Study / approach", "Technique", "Limitation addressed by our work"], [
        ["LLM mock interview agents", "Contextual question generation", "Adds full voice loop + guards + coverage"],
        ["ASR interview platforms", "Speech input", "Adds adaptive dialogue + fairness + tiered reports"],
        ["Multimodal facial + speech", "Behaviour features", "Deferred — scope traded for stable voice MVP"],
        ["Rule-based chatbots", "Fixed flows", "Replaced by CoverageEngine + DecisionEngine + LLM bounds"],
        ["Proposed platform (this FYP)", "ASR+LLM+TTS+VAD+guards+Report v2", "End-to-end Junior AI Engineer voice path"],
    ])

    doc.add_page_break()

    # CHAPTER 3
    doc.add_heading("Chapter 3 — System Background", level=1)
    doc.add_heading("3.1 Speech and Voice Stack", level=2)
    _add_body(doc, """
    Deepgram nova-2 provides streaming transcription with interim and final hypotheses. Cartesia synthesizes
    interviewer speech with low latency. Silero VAD segments speech vs silence for debouncing and barge-in grace.
    Pipecat composes STT, custom InterviewProcessor, and TTS in a frame-based pipeline over WebSocket transport.
    """)
    doc.add_heading("3.2 Large Language Models", level=2)
    _add_body(doc, """
    Groq hosts Llama 3.3 70B Versatile for JSON-structured evaluation and bounded question generation. The system
    does not maintain a full chat messages[] history; each call uses constructed prompts with selective context
    (recent Q&A pairs, sliding question window, resume-by-domain evidence).
    """)
    doc.add_heading("3.3 Real-Time Communication", level=2)
    _add_body(doc, """
    The primary demo uses WebSocket binary PCM on port 8765. A separate report HTTP server on port 8766 serves
    latest JSON and HTML for FYP demonstrations. FastAPI on port 8000 supports REST testing when run in the same
    process as SessionService (in-memory sessions are not shared across separate processes).
    """)
    doc.add_heading("3.4 Overall Architecture", level=2)
    _add_figure(doc, figs["fig_3_1"], "Figure 3.1 — Overall system architecture (three runtime entry points).")

    doc.add_heading("3.5 Automatic Speech Recognition", level=2)
    _add_body(doc, """
    Streaming ASR converts candidate speech to text incrementally. Interim hypotheses support UI feedback; final
    hypotheses trigger turn submission after debouncing, grace windows, and echo suppression in InterviewProcessor.
    Domain keyword boosting improves recognition of technical terms (e.g. FastAPI, preprocessing). Residual errors
    are mitigated by transcript cleanup, incomplete guards, and STT fairness reweighting during evaluation.
    """)

    doc.add_heading("3.6 Text-to-Speech", level=2)
    _add_body(doc, """
    Interviewer speech is synthesized through Cartesia and streamed to the browser as audio frames. Spoken questions
    are kept short (soft ~25-word cap for domain primaries) to suit voice UX. Pre-interview instructions use the same
    Cartesia voice as the live interviewer for consistent candidate experience.
    """)

    doc.add_heading("3.7 Voice Activity Detection and Turn-Taking", level=2)
    _add_body(doc, """
    Silero VAD identifies speech segments. VoiceTurnPolicy configures debounce duration, short-answer grace, echo
    cooldown after bot speech, silence nudge/rephrase timers, and tail-fragment resume windows. Client-side RMS
    barge-in may send interrupt messages; server-side grace reduces false interrupts during bot speak-out.
    """)

    doc.add_heading("3.8 Evaluation Model", level=2)
    _add_table(doc, ["Dimension", "Default weight"], [
        ["structure", "0.25"],
        ["result_orientation", "0.20"],
        ["ownership", "0.20"],
        ["leadership", "0.15"],
        ["clarity", "0.10"],
        ["confidence", "0.10"],
    ])
    _add_body(doc, """
    Methodology identifier: llm_rubric_ensemble_lite_v1. Optional rethink pass runs on borderline weighted scores or
    high spread across dimensions. Hire signal thresholds (per answer and interview aggregate alignment): Strong Hire ≥ 4.0,
    Hire ≥ 3.0, Borderline ≥ 2.5. Communication and technical composites are derived for reporting profiles.
    """)

    doc.add_page_break()

    # CHAPTER 4
    doc.add_heading("Chapter 4 — Methodology", level=1)
    doc.add_heading("4.1 Development Approach", level=2)
    _add_table(doc, ["Phase", "Deliverable"], [
        ["1", "SessionService, config, interviewer policy"],
        ["2", "Guard pipeline, transcript utilities, sanitizer"],
        ["3", "CoverageEngine, role_registry, resume bootstrap"],
        ["4", "Rubric, rethink ensemble, human-study export"],
        ["5", "VoiceTurnPolicy, async Groq in Pipecat loop"],
        ["6A–6C", "Meta/IDK guards, transcript fairness, reporting profiles"],
        ["Post-6", "Report v2, full coverage, lobby, calibration, recruiter HTML UX"],
    ])
    _add_body(doc, """
    Development followed phased modularisation: unified SessionService (Phase 1), guard pipeline (Phase 2),
    coverage and resume bootstrap (Phase 3), evaluation rubric and rethink ensemble (Phase 4), voice operability
    (Phase 5), interview flow and transcript fairness (Phase 6A–6C), then July 2026 product fixes: Report v2 package,
    full blueprint coverage policy, canonical question store, pre-interview lobby, evaluation calibration, and
    candidate/recruiter reporting UX separation.
    """)
    doc.add_heading("4.1.1 Functional Requirements (implemented)", level=3)
    _add_table(doc, ["ID", "Requirement", "Implementation"], [
        ["FR-1", "Voice capture", "Browser mic PCM over WebSocket"],
        ["FR-2", "Speech recognition", "Deepgram nova-2 streaming"],
        ["FR-3", "Adaptive questions", "CoverageEngine + LLMAdapter + DecisionEngine"],
        ["FR-4", "Evaluation", "Six-dimension Groq rubric + guards"],
        ["FR-5", "Voice responses", "Cartesia TTS via Pipecat"],
        ["FR-6", "Reports", "Report v2 JSON/HTML + tiered completion"],
        ["FR-7", "Candidate UX", "Pre-interview lobby + thank-you completion"],
        ["FR-8", "Recruiter view (FYP demo)", "HTML assessment + /latest-report.html"],
    ])
    doc.add_paragraph(
        "Note: Full user authentication and multi-tenant recruiter portal are out of scope for this FYP delivery."
    )
    doc.add_heading("4.2 Interview Blueprint and Policy", level=2)
    _add_body(doc, """
    Junior AI Engineer domains (in order): project_overview, python, machine_learning, data_preprocessing,
    model_evaluation, nlp_speech_ai, apis_backend, deployment, debugging_problem_solving, behavioral_ownership.
    Policy highlights: one primary question and up to one probe per domain; max 28 total turns (safety ceiling);
    max 2 hard skips; coverage-first wrap-up requiring visited blueprint for “complete” reports (~100% coverage,
    wrap-up state, minimum evaluated turns).
    """)
    doc.add_heading("4.3 Voice Pipeline", level=2)
    _add_figure(doc, figs["fig_4_1"], "Figure 4.1 — Voice processing pipeline.")
    doc.add_heading("4.4 Guard and Evaluation Pipeline", level=2)
    _add_figure(doc, figs["fig_4_2"], "Figure 4.2 — Guard pipeline order.")
    _add_body(doc, """
    Six dimensions are weighted (structure, result_orientation, ownership, leadership, clarity, confidence).
    Borderline answers may trigger a rethink pass. STT fairness adjusts weights when noise, stutter, or tail-fragment
    signals are detected. Per-answer hire signals use thresholds hire ≥ 3.0 and strong hire ≥ 4.0 (calibrated July 2026).
    Evaluator persona: fair senior engineer for junior voice interviews.
    """)
    doc.add_heading("4.5 Pre-Interview Lobby", level=2)
    _add_figure(doc, figs["fig_4_4"], "Figure 4.4 — Lobby handshake (instructions then start).")
    _add_body(doc, """
    The manual client presents Welcome → Cartesia-spoken instructions (same voice as interviewer) → Ready.
    WebSocket connect does not auto-start the interview; explicit {type:instructions} and {type:start} messages
    separate preamble from scored dialogue.
    """)
    doc.add_heading("4.6 Reporting Methodology", level=2)
    _add_figure(doc, figs["fig_4_3"], "Figure 4.3 — Report generation flow.")
    _add_body(doc, """
    On disconnect, DialogueManager.get_final_report builds legacy analytics, sanitizes technical-interview wording,
    wraps Report v2 (report_meta, executive_summary, ratings_summary, domain_ratings, question_review,
    detailed_analytics), and persists JSON plus HTML (except aborted-only JSON under reports/aborted/).
    Recruiter HTML uses ratings_summary.final_recommendation; incomplete sessions show N/A recommendation with caveats.
    Candidates see a thank-you panel with a demo link to /latest-report.html — not in-panel scores.
    """)

    doc.add_page_break()

    # CHAPTER 5
    doc.add_heading("Chapter 5 — Results and Discussion", level=1)
    doc.add_heading("5.1 Testing Strategy", level=2)
    _add_body(doc, """
    Automated regression covers session service, guards, evaluation rubric, reporting v2, canonical question behaviour,
    voice UX fixes, and Pipecat integration smoke tests (scripts/run_regression.sh and backend/tests/). Live sessions
    validated STT merge quality, barge-in, lobby flow, and report persistence.
    """)
    doc.add_heading("5.2 Adaptive Decisions", level=2)
    _add_figure(doc, figs["fig_5_1"], "Figure 5.1 — DecisionEngine outcomes.")
    doc.add_heading("5.3 Illustrative Live Session Metrics", level=2)
    _add_body(doc, """
    The table below illustrates metrics from a representative incomplete session (early disconnect). Low scores
    reflect candidate performance, not pipeline failure; the session still produced Report v2 artifacts and adaptive trace.
    """)
    _add_table(doc, ["Metric", "Example value"], [
        ["Evaluated turns", "17"],
        ["Domains assessed", "4 / 10"],
        ["Coverage", "40%"],
        ["Report type", "incomplete"],
        ["Recruiter recommendation (v2)", "N/A (insufficient completion tier)"],
    ])
    doc.add_heading("5.4 Discussion", level=2)
    _add_body(doc, """
    The project demonstrates that a defensible FYP voice interviewer requires engineering investment in turn-taking and
    guardrails, not only LLM prompt tuning. Deferred proposal items (facial emotion, Docker/Kubernetes production,
    IRT/CAT psychometrics, React/Firebase frontend) were replaced by blueprint adaptivity, transcript fairness,
    canonical recoveries, and honest completion tiers — choices that improved demo reliability.

    Limitations remain: single concurrent voice client per bot process, cloud API dependency, ASR errors under noise,
    and barge-in based on energy/VAD rather than semantic interruption detection.
    """)

    doc.add_page_break()

    # CHAPTER 6
    doc.add_heading("Chapter 6 — System Design and Implementation", level=1)
    doc.add_heading("6.1 Layered Architecture", level=2)
    _add_table(doc, ["Layer", "Components"], [
        ["Presentation", "manual_client: lobby, live conversation, thank-you UX"],
        ["Voice transport", "interview_bot.py, InterviewProcessor, VoiceTurnPolicy"],
        ["Integration", "InterviewDialogueAdapter → SessionService"],
        ["Dialogue brain", "DialogueManager, guards, DecisionEngine, CoverageEngine, LLMAdapter"],
        ["AI services", "Deepgram, Groq, Cartesia, Silero via Pipecat"],
        ["Reporting", "backend/reporting/*, analytics.py, HTML renderer"],
        ["Storage", "reports/, optional PostgreSQL"],
    ])
    doc.add_heading("6.2 Key Modules", level=2)
    _add_body(doc, """
    SessionService holds in-process InterviewSession objects. DialogueManager.handle_turn orchestrates guards,
    EvaluationPipeline, decisions, and question commits via set_active_question (canonical store). rephrase_policy
    and idk_policy implement recovery speech without stacking duplicate questions in TTS. role_registry maps
    target_role junior_ai_engineer to blueprint (extension point for future roles).
    """)
    doc.add_heading("6.2.1 Canonical Question and Recovery Speech", level=3)
    _add_body(doc, """
    When a primary or probe question is committed, a canonical one-sentence intent is stored. Recoveries (repeat,
    clarify, redirect, IDK hint) rephrase that intent rather than concatenating prior TTS strings — preventing
    multi-question stacking heard in early live demos.
    """)
    doc.add_heading("6.2.2 Evaluation Calibration (July 2026)", level=3)
    _add_body(doc, """
    Evaluator prompts and Groq system messages were recalibrated for junior voice interviews (fair senior engineer
    persona). Per-answer hire thresholds were aligned to interview aggregates (Hire ≥ 3.0, Strong Hire ≥ 4.0). This
    was a calibration change only; weights, pipeline architecture, and DecisionEngine semantics were unchanged.
    """)
    doc.add_heading("6.2.3 Reporting UX", level=3)
    _add_body(doc, """
    Candidates see a thank-you message and an FYP-only link to open recruiter HTML. Recruiters (or examiners) review
    structured HTML generated from the same Report v2 JSON stored under reports/. See docs/RECRUITER_REPORT_CONTRACT.md
    in the repository for the presentation field contract.
    """)
    doc.add_heading("6.3 REST and Voice APIs", level=2)
    _add_table(doc, ["Endpoint", "Purpose"], [
        ["POST /start, POST /chat", "Text-mode interview testing"],
        ["GET /report/{id}", "Report v2 JSON"],
        ["GET /export/human-study/{id}", "Cohen's κ study export"],
        ["WS :8765", "Voice PCM + control messages"],
        ["GET :8766/latest-report", "Latest JSON envelope"],
        ["GET :8766/latest-report.html", "Latest recruiter HTML"],
    ])
    doc.add_heading("6.4 Report v2 Components", level=2)
    _add_table(doc, ["Component", "Description"], [
        ["report_meta", "Candidate, session, report_type, filename"],
        ["ratings_summary", "Overall, technical, communication, final_recommendation"],
        ["domain_ratings", "Per-blueprint-domain status"],
        ["question_review", "Condensed Q&A cards"],
        ["interview_completion", "Coverage %, evaluated turns, termination_reason"],
        ["detailed_analytics", "Legacy analytics blob for researchers"],
    ])

    doc.add_page_break()

    # CHAPTER 7
    doc.add_heading("Chapter 7 — Conclusion", level=1)
    _add_body(doc, """
    This Final Year Project delivered a working real-time AI voice interviewer with structured domain coverage,
    guarded dialogue, transparent LLM evaluation, resume-aware questioning, pre-interview candidate UX, and
    recruiter-oriented Report v2 output. Development evolved through six engineering phases plus focused July 2026
    calibration and reporting UX work on branch uthman (commit 612ae79).

    The system satisfies primary objectives for voice simulation, adaptive questioning, and automated reporting
    while honestly deferring multimodal emotion analysis and production multi-tenant deployment. Future work includes
    recruiter dashboard API, human κ validation using the export endpoint, optional Docker packaging, WebRTC transport,
    and additional role blueprints via role_registry without forking the dialogue engine.

    For viva defence: data (Report v2 JSON) is separated from presentation (HTML assessment); candidates receive
    completion confirmation; scoring methodology changes in July 2026 were calibration of persona and thresholds,
    not a rewrite of the evaluation pipeline architecture.
    """)

    doc.add_heading("References", level=1)
    refs = [
        "Groq Inc., Groq API Documentation, https://console.groq.com/docs",
        "Pipecat AI, Pipecat Documentation, https://docs.pipecat.ai",
        "Deepgram Inc., Speech-to-Text API Documentation, https://developers.deepgram.com",
        "Cartesia AI, Text-to-Speech Documentation, https://docs.cartesia.ai",
        "FastAPI, FastAPI Documentation, https://fastapi.tiangolo.com",
        "H. Sun et al., MockLLM: An LLM-Based Mock Interview System, arXiv:2405.18113, 2024.",
        "I. Sommerville, Software Engineering, 10th ed., Pearson, 2016.",
        "J. Cohen, A Coefficient of Agreement for Nominal Scales, Educational and Psychological Measurement, 1960.",
    ]
    for i, ref in enumerate(refs, 1):
        doc.add_paragraph(f"[{i}] {ref}")

    doc.add_page_break()
    doc.add_heading("Appendix A — Environment Variables (selected)", level=1)
    _add_table(doc, ["Variable", "Purpose"], [
        ["GROQ_API_KEY", "LLM authentication"],
        ["DEEPGRAM_API_KEY", "STT authentication"],
        ["CARTESIA_API_KEY / CARTESIA_VOICE_ID", "TTS authentication and voice"],
        ["PIPECAT_WS_PORT", "Voice WebSocket (default 8765)"],
        ["REPORT_HTTP_PORT", "Report server (default 8766)"],
        ["DATABASE_URL", "Optional PostgreSQL"],
        ["DEBUG_LIVE_LOGGING", "Optional Groq prompt/reply traces"],
    ])

    doc.add_heading("Appendix B — Git Evolution (summary)", level=1)
    _add_table(doc, ["Period", "Theme"], [
        ["Jun 2026", "Phases 1–5 modular refactor"],
        ["Jul 2026 early", "Phase 6 voice quality, Report v2, modular client"],
        ["Jul 2026 mid", "Full coverage, tail fragments, canonical Q, voice UX fixes"],
        ["Jul 2026 late", "Pre-interview lobby, eval calibration, recruiter HTML UX"],
    ])

    doc.add_heading("Appendix C — Suggested Screenshots for Submission", level=1)
    _add_table(doc, ["Figure", "Capture"], [
        ["C.1", "Pre-interview Welcome screen (name/resume)"],
        ["C.2", "Instructions panel with incremental bullet lines"],
        ["C.3", "Live conversation transcript during interview"],
        ["C.4", "Thank-you / After the interview panel"],
        ["C.5", "Recruiter HTML assessment (recommendation + domain table)"],
        ["C.6", "Sample JSON report file in reports/ folder"],
        ["C.7", "Terminal showing interview_bot and report HTTP server"],
    ])

    return doc


def main():
    print("Generating diagrams...")
    figs = generate_diagrams()
    print("Building DOCX...")
    doc = build_document(figs)
    doc.save(OUT_DOCX)
    print(f"Written: {OUT_DOCX}")
    print(f"Diagram assets: {ASSETS}")


if __name__ == "__main__":
    main()
