"""HTML presentation renderer for report v2 — recruiter-facing assessment."""

from __future__ import annotations

import html
import json
from typing import Any


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def _score_cell(block: dict | None, fallback_label: str = "N/A") -> tuple[str, str]:
    block = block or {}
    score = block.get("score")
    label = block.get("label") or fallback_label
    score_txt = "—" if score is None else f"{score}"
    return str(label), score_txt


def _format_generated_at(raw: str | None) -> str:
    if not raw:
        return "—"
    text = str(raw)
    # Prefer readable date/time without forcing timezone libraries.
    if "T" in text:
        date_part, _, time_part = text.partition("T")
        time_part = time_part.replace("Z", "").split("+")[0].split(".")[0]
        if len(time_part) >= 5:
            return f"{date_part} · {time_part[:5]} UTC"
        return date_part
    return text


def _signal_class(signal: str | None) -> str:
    s = (signal or "").lower()
    if s in ("n/a", "na", ""):
        return "signal-na"
    if "strong" in s:
        return "signal-strong"
    if "no hire" in s or s == "no_hire":
        return "signal-no"
    if "borderline" in s:
        return "signal-borderline"
    if "hire" in s:
        return "signal-hire"
    return "signal-na"


def render_report_html(report: dict) -> str:
    meta = report.get("report_meta", {}) or {}
    ratings = report.get("ratings_summary", {}) or {}
    rec = ratings.get("final_recommendation", {}) or {}
    completion = report.get("interview_completion", {}) or {}
    limitations = report.get("limitations_and_bias", {}) or {}
    methodology = report.get("evaluation_methodology", {}) or {}

    candidate = meta.get("candidate_display_name") or "Candidate"
    role = meta.get("role_title") or "Junior AI Engineer"
    report_type = meta.get("report_type") or "incomplete"
    session_id = meta.get("session_id") or ""
    short_session = session_id[:8] if session_id else "—"
    generated = _format_generated_at(meta.get("generated_at"))
    signal = rec.get("signal") or "N/A"
    signal_css = _signal_class(signal)

    overall_label, overall_score = _score_cell(ratings.get("overall_performance"))
    tech_label, tech_score = _score_cell(ratings.get("technical_performance"))
    comm_label, comm_score = _score_cell(ratings.get("communication_skills"))
    conf_block = ratings.get("confidence_professionalism") or {}
    conf_label = conf_block.get("label") or conf_block.get("rating") or "—"
    conf_score = conf_block.get("score")
    conf_score_txt = "—" if conf_score is None else str(conf_score)

    domain_rows = []
    for domain in report.get("domain_ratings", []) or []:
        domain_rows.append(
            "<tr>"
            f"<td>{_esc(domain.get('domain_label'))}</td>"
            f"<td><span class='pill'>{_esc(domain.get('status'))}</span></td>"
            f"<td>{_esc(domain.get('rating'))}</td>"
            f"<td class='muted'>{_esc(domain.get('brief_note'))}</td>"
            "</tr>"
        )
    domain_tbody = "".join(domain_rows) or (
        "<tr><td colspan='4' class='muted'>No domain ratings available.</td></tr>"
    )

    question_blocks = []
    for item in report.get("question_review", []) or []:
        status = item.get("review_status") or "scored"
        status_badge = ""
        if status != "scored":
            status_badge = (
                f"<span class='pill qa-status'>{_esc(status.replace('_', ' '))}</span>"
            )
        question_blocks.append(
            f"""
        <details class="qa-card">
          <summary>
            <span class="qa-turn">Turn {_esc(item.get('turn'))}</span>
            <span class="qa-domain">{_esc(item.get('domain_label'))}</span>
            {status_badge}
          </summary>
          <p><span class="qa-label">Question</span>{_esc(item.get('question'))}</p>
          <p><span class="qa-label">Answer</span>{_esc(item.get('candidate_answer_summary'))}</p>
          <p class="muted">{_esc(item.get('evaluation_summary'))}</p>
        </details>
        """
        )
    questions_html = "".join(question_blocks) or (
        '<p class="muted">No Q&amp;A turns recorded for this session.</p>'
    )

    strengths = "".join(
        f"<li>{_esc(s)}</li>" for s in (report.get("strengths") or [])
    ) or "<li class='muted'>None recorded</li>"
    improvements = "".join(
        f"<li>{_esc(s)}</li>" for s in (report.get("areas_for_improvement") or [])
    ) or "<li class='muted'>None recorded</li>"

    banner = ""
    if report_type == "aborted":
        note = completion.get("completion_note") or (
            "No scored turns — transcript only. Treat this as a session log, not a hiring assessment."
        )
        banner = f'<div class="banner banner-aborted" role="status">{_esc(note)}</div>'
    elif report_type != "complete":
        note = completion.get("completion_note") or (
            "Interview ended before a full assessment. Treat ratings as preliminary."
        )
        banner = f'<div class="banner" role="status">{_esc(note)}</div>'

    coverage = completion.get("coverage_percent")
    evaluated_turns = completion.get("evaluated_turns")
    termination = completion.get("termination_reason") or meta.get("termination_reason")

    footer_bits = []
    if methodology.get("framework"):
        footer_bits.append(f"Framework: {_esc(methodology.get('framework'))}")
    caveat = limitations.get("data_quality_caveat") or limitations.get("note")
    if caveat:
        footer_bits.append(_esc(caveat))
    footer_bits.append(
        "Decision-support signal only — not a final hiring decision."
    )
    footer_html = " · ".join(footer_bits)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{_esc(candidate)} — Interview Assessment</title>
  <style>
    :root {{
      --ink: #0f172a;
      --muted: #64748b;
      --line: #e2e8f0;
      --surface: #ffffff;
      --bg: #f1f5f9;
      --accent: #0f766e;
      --accent-soft: #ccfbf1;
      --warn-bg: #fffbeb;
      --warn-border: #f59e0b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
      color: var(--ink);
      background: var(--bg);
      line-height: 1.55;
    }}
    .page {{
      max-width: 920px;
      margin: 0 auto;
      padding: 2rem 1.25rem 3rem;
    }}
    .hero {{
      background: linear-gradient(135deg, #0f172a 0%, #134e4a 100%);
      color: #f8fafc;
      border-radius: 16px;
      padding: 2rem 1.75rem;
      margin-bottom: 1.25rem;
      box-shadow: 0 10px 30px rgba(15, 23, 42, 0.18);
    }}
    .hero-kicker {{
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 0.72rem;
      opacity: 0.8;
      margin: 0 0 0.5rem;
    }}
    .hero h1 {{
      margin: 0;
      font-size: clamp(1.75rem, 4vw, 2.35rem);
      font-weight: 700;
      letter-spacing: -0.02em;
      line-height: 1.15;
    }}
    .hero-meta {{
      margin-top: 1rem;
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem 1rem;
      font-size: 0.9rem;
      opacity: 0.92;
    }}
    .badge {{
      display: inline-block;
      padding: 0.2rem 0.65rem;
      border-radius: 999px;
      font-size: 0.75rem;
      font-weight: 600;
      background: rgba(255,255,255,0.15);
      border: 1px solid rgba(255,255,255,0.25);
      text-transform: capitalize;
    }}
    .banner {{
      background: var(--warn-bg);
      border: 1px solid var(--warn-border);
      border-radius: 10px;
      padding: 0.9rem 1rem;
      margin-bottom: 1.25rem;
      font-size: 0.92rem;
    }}
    .banner-aborted {{
      background: #fef2f2;
      border-color: #fecaca;
      color: #7f1d1d;
    }}
    .qa-status {{
      margin-left: 0.35rem;
      font-size: 0.7rem;
      background: #e2e8f0;
      color: #334155;
      border: none;
    }}
    .section {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 1.25rem 1.35rem;
      margin-bottom: 1rem;
    }}
    .section h2 {{
      margin: 0 0 0.85rem;
      font-size: 1.05rem;
      font-weight: 700;
      letter-spacing: -0.01em;
    }}
    .section p {{ margin: 0 0 0.75rem; }}
    .section p:last-child {{ margin-bottom: 0; }}
    .rec-band {{
      display: grid;
      gap: 0.75rem;
    }}
    .signal {{
      display: inline-block;
      font-size: 1.35rem;
      font-weight: 800;
      letter-spacing: -0.02em;
      padding: 0.35rem 0.85rem;
      border-radius: 10px;
    }}
    .signal-strong {{ background: #dcfce7; color: #166534; }}
    .signal-hire {{ background: #ccfbf1; color: #0f766e; }}
    .signal-borderline {{ background: #fef9c3; color: #854d0e; }}
    .signal-no {{ background: #fee2e2; color: #991b1b; }}
    .signal-na {{ background: #e2e8f0; color: #475569; }}
    .disclaimer {{ color: var(--muted); font-size: 0.85rem; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 0.75rem;
    }}
    .metric {{
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 0.9rem 1rem;
      background: #f8fafc;
    }}
    .metric .label {{
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--muted);
      margin-bottom: 0.35rem;
    }}
    .metric .value {{
      font-size: 1.15rem;
      font-weight: 700;
    }}
    .metric .sub {{
      color: var(--muted);
      font-size: 0.85rem;
      margin-top: 0.15rem;
    }}
    .two-col {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1rem;
    }}
    @media (max-width: 700px) {{
      .two-col {{ grid-template-columns: 1fr; }}
    }}
    ul {{
      margin: 0;
      padding-left: 1.15rem;
    }}
    li {{ margin-bottom: 0.4rem; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.92rem;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 0.65rem 0.5rem;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--muted);
      font-weight: 600;
    }}
    .pill {{
      display: inline-block;
      padding: 0.1rem 0.5rem;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent);
      font-size: 0.78rem;
      font-weight: 600;
      text-transform: capitalize;
    }}
    .qa-card {{
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 0.65rem 0.85rem;
      margin-bottom: 0.55rem;
      background: #f8fafc;
    }}
    .qa-card summary {{
      cursor: pointer;
      font-weight: 600;
      display: flex;
      gap: 0.75rem;
      align-items: baseline;
      list-style: none;
    }}
    .qa-card summary::-webkit-details-marker {{ display: none; }}
    .qa-turn {{ color: var(--accent); font-size: 0.85rem; }}
    .qa-domain {{ color: var(--ink); }}
    .qa-label {{
      display: block;
      font-size: 0.7rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--muted);
      margin-bottom: 0.2rem;
      margin-top: 0.65rem;
    }}
    .muted {{ color: var(--muted); }}
    .footer {{
      margin-top: 1.5rem;
      padding-top: 1rem;
      border-top: 1px solid var(--line);
      font-size: 0.8rem;
      color: var(--muted);
      line-height: 1.5;
    }}
    details.debug {{
      margin-top: 1rem;
      font-size: 0.85rem;
    }}
    details.debug pre {{
      background: #0f172a;
      color: #e2e8f0;
      padding: 1rem;
      overflow: auto;
      border-radius: 10px;
      max-height: 320px;
    }}
  </style>
</head>
<body>
  <div class="page">
    <header class="hero">
      <p class="hero-kicker">Recruiter interview assessment</p>
      <h1>{_esc(candidate)}</h1>
      <div class="hero-meta">
        <span>{_esc(role)}</span>
        <span class="badge">{_esc(report_type)}</span>
        <span>Generated {_esc(generated)}</span>
        <span>Session {_esc(short_session)}</span>
      </div>
    </header>

    {banner}

    <section class="section">
      <h2>Recommendation</h2>
      <div class="rec-band">
        <div><span class="signal {signal_css}">{_esc(signal)}</span></div>
        <p>{_esc(rec.get('rationale') or 'No recommendation rationale available.')}</p>
        <p class="disclaimer">{_esc(rec.get('disclaimer') or 'Decision-support signal only, not a final hiring decision.')}</p>
      </div>
    </section>

    <section class="section">
      <h2>Executive summary</h2>
      <p>{_esc(report.get('executive_summary') or 'No executive summary available.')}</p>
      <p class="muted">{_esc(report.get('overall_summary') or '')}</p>
    </section>

    <section class="section">
      <h2>Score overview</h2>
      <div class="grid">
        <div class="metric">
          <div class="label">Overall</div>
          <div class="value">{_esc(overall_label)}</div>
          <div class="sub">Score {_esc(overall_score)}</div>
        </div>
        <div class="metric">
          <div class="label">Technical</div>
          <div class="value">{_esc(tech_label)}</div>
          <div class="sub">Score {_esc(tech_score)}</div>
        </div>
        <div class="metric">
          <div class="label">Communication</div>
          <div class="value">{_esc(comm_label)}</div>
          <div class="sub">Score {_esc(comm_score)}</div>
        </div>
        <div class="metric">
          <div class="label">Confidence</div>
          <div class="value">{_esc(conf_label)}</div>
          <div class="sub">Score {_esc(conf_score_txt)}</div>
        </div>
      </div>
      <p class="muted" style="margin-top:0.85rem">
        Evaluated turns: {_esc(evaluated_turns if evaluated_turns is not None else '—')}
        · Coverage: {_esc(f'{coverage}%' if coverage is not None else '—')}
        · Ended: {_esc(termination or '—')}
      </p>
    </section>

    <div class="two-col">
      <section class="section">
        <h2>Strengths</h2>
        <ul>{strengths}</ul>
      </section>
      <section class="section">
        <h2>Areas for improvement</h2>
        <ul>{improvements}</ul>
      </section>
    </div>

    <section class="section">
      <h2>Domain assessment</h2>
      <table>
        <thead>
          <tr><th>Domain</th><th>Status</th><th>Rating</th><th>Note</th></tr>
        </thead>
        <tbody>{domain_tbody}</tbody>
      </table>
    </section>

    <section class="section">
      <h2>Question review</h2>
      <p class="muted" style="margin-bottom:0.75rem">Expand a turn to read the question, answer summary, and evaluation note.</p>
      {questions_html}
    </section>

    <footer class="footer">{footer_html}</footer>

    <details class="debug">
      <summary>Debug: detailed analytics JSON</summary>
      <pre>{_esc(json.dumps(report.get('detailed_analytics', {}), indent=2))}</pre>
    </details>
  </div>
</body>
</html>"""
