"""HTML presentation renderer for report v2."""

from __future__ import annotations

import html
import json


def render_report_html(report: dict) -> str:
    meta = report.get("report_meta", {}) or {}
    ratings = report.get("ratings_summary", {}) or {}
    rec = ratings.get("final_recommendation", {}) or {}

    def esc(value) -> str:
        return html.escape(str(value if value is not None else ""))

    domain_rows = ""
    for domain in report.get("domain_ratings", []) or []:
        domain_rows += (
            f"<tr><td>{esc(domain.get('domain_label'))}</td>"
            f"<td>{esc(domain.get('status'))}</td>"
            f"<td>{esc(domain.get('rating'))}</td>"
            f"<td>{esc(domain.get('brief_note'))}</td></tr>"
        )

    question_blocks = ""
    for item in report.get("question_review", []) or []:
        question_blocks += f"""
        <article class="qa-card">
          <h4>Turn {esc(item.get('turn'))} — {esc(item.get('domain_label'))}</h4>
          <p><strong>Q:</strong> {esc(item.get('question'))}</p>
          <p><strong>A:</strong> {esc(item.get('candidate_answer_summary'))}</p>
          <p class="muted">{esc(item.get('evaluation_summary'))}</p>
        </article>
        """

    strengths = "".join(f"<li>{esc(s)}</li>" for s in report.get("strengths", []) or [])
    improvements = "".join(
        f"<li>{esc(s)}</li>" for s in report.get("areas_for_improvement", []) or []
    )

    banner = ""
    if meta.get("report_type") != "complete":
        banner = (
            f'<div class="banner">{esc(report.get("interview_completion", {}).get("completion_note"))}</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Interview Report — {esc(meta.get('candidate_display_name'))}</title>
  <style>
    body {{ font-family: Georgia, serif; margin: 2rem; color: #1e293b; line-height: 1.6; }}
    h1, h2, h3 {{ font-family: Arial, sans-serif; }}
    .banner {{ background: #fef3c7; border: 1px solid #f59e0b; padding: 1rem; margin-bottom: 1.5rem; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; }}
    .card {{ border: 1px solid #cbd5e1; border-radius: 8px; padding: 1rem; background: #f8fafc; }}
    table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
    th, td {{ border: 1px solid #e2e8f0; padding: 0.5rem; text-align: left; }}
    .qa-card {{ border-left: 4px solid #6366f1; padding-left: 1rem; margin: 1rem 0; }}
    .muted {{ color: #64748b; font-size: 0.95rem; }}
    details pre {{ background: #0f172a; color: #e2e8f0; padding: 1rem; overflow: auto; }}
  </style>
</head>
<body>
  {banner}
  <h1>Interview Report</h1>
  <p><strong>Candidate:</strong> {esc(meta.get('candidate_display_name'))} |
     <strong>Role:</strong> {esc(meta.get('role_title'))} |
     <strong>Type:</strong> {esc(meta.get('report_type'))}</p>
  <p><strong>Generated:</strong> {esc(meta.get('generated_at'))}</p>

  <h2>Executive Summary</h2>
  <p>{esc(report.get('executive_summary'))}</p>

  <h2>Overall Summary</h2>
  <p>{esc(report.get('overall_summary'))}</p>

  <h2>Ratings</h2>
  <div class="grid">
    <div class="card"><h3>Overall</h3><p>{esc(ratings.get('overall_performance', {}).get('label'))} ({esc(ratings.get('overall_performance', {}).get('score'))})</p></div>
    <div class="card"><h3>Technical</h3><p>{esc(ratings.get('technical_performance', {}).get('label'))} ({esc(ratings.get('technical_performance', {}).get('score'))})</p></div>
    <div class="card"><h3>Communication</h3><p>{esc(ratings.get('communication_skills', {}).get('label'))} ({esc(ratings.get('communication_skills', {}).get('score'))})</p></div>
    <div class="card"><h3>Recommendation</h3><p>{esc(rec.get('signal'))}</p><p class="muted">{esc(rec.get('rationale'))}</p></div>
  </div>

  <h2>Domain Ratings</h2>
  <table>
    <thead><tr><th>Domain</th><th>Status</th><th>Rating</th><th>Note</th></tr></thead>
    <tbody>{domain_rows}</tbody>
  </table>

  <h2>Strengths</h2>
  <ul>{strengths or '<li>None recorded</li>'}</ul>

  <h2>Areas for Improvement</h2>
  <ul>{improvements or '<li>None recorded</li>'}</ul>

  <h2>Question Review</h2>
  {question_blocks or '<p class="muted">No evaluated Q&A turns.</p>'}

  <details>
    <summary>Full JSON (debug)</summary>
    <pre>{esc(json.dumps(report.get('detailed_analytics', report), indent=2))}</pre>
  </details>
</body>
</html>"""
