"""
Optional SMTP invitation email for the Recruiter Dashboard.

Uses stdlib smtplib only. If SMTP is not configured, create/copy-link
workflows still work; send endpoints return a clear error.
"""

from __future__ import annotations

import html
import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

logger = logging.getLogger(__name__)


def company_name() -> str:
    return (os.getenv("COMPANY_NAME") or "AI Interviewer").strip() or "AI Interviewer"


def smtp_settings() -> dict[str, Any]:
    port_raw = (os.getenv("SMTP_PORT") or "587").strip()
    try:
        port = int(port_raw)
    except ValueError:
        port = 587
    return {
        "host": (os.getenv("SMTP_HOST") or "").strip(),
        "port": port,
        "user": (os.getenv("SMTP_USER") or "").strip(),
        "password": os.getenv("SMTP_PASSWORD") or "",
        "email_from": (os.getenv("EMAIL_FROM") or "").strip(),
    }


def smtp_configured() -> bool:
    s = smtp_settings()
    return bool(s["host"] and s["user"] and s["password"] and s["email_from"])


def email_status() -> dict[str, Any]:
    return {
        "configured": smtp_configured(),
        "company_name": company_name(),
    }


def build_invite_email(
    *,
    candidate_url: str,
    display_title: str,
    description: str | None = None,
    candidate_name: str | None = None,
    suggested_skills: list[str] | None = None,
) -> dict[str, str]:
    """Return subject, text, and html bodies for an invite (no passwords)."""
    company = company_name()
    title = (display_title or "Interview").strip()
    name = (candidate_name or "").strip()
    greeting = f"Hello {name}," if name else "Hello,"
    desc = (description or "").strip() or (
        "A real-time voice interview with adaptive questions and an automated evaluation report."
    )
    skills = [s for s in (suggested_skills or []) if s]
    skills_line = ", ".join(skills[:8]) if skills else ""

    instructions = (
        "1. Open the interview link on a laptop or desktop if possible.\n"
        "2. Use a quiet place and allow microphone access when prompted.\n"
        "3. Complete the welcome steps, then start when you are ready.\n"
        "4. Speak clearly; the interviewer will ask follow-up questions."
    )

    subject = f"{company}: invitation — {title}"

    text_parts = [
        greeting,
        "",
        f"{company} invites you to a voice interview.",
        f"Interview: {title}",
        "",
        desc,
    ]
    if skills_line:
        text_parts.extend(["", f"Suggested focus areas: {skills_line}"])
    text_parts.extend(
        [
            "",
            f"Interview link:\n{candidate_url}",
            "",
            "Instructions:",
            instructions,
            "",
            "No account password is required — open the link to begin.",
            "",
            f"— {company}",
        ]
    )
    text = "\n".join(text_parts)

    skills_html = (
        f"<p><strong>Suggested focus areas:</strong> {html.escape(skills_line)}</p>"
        if skills_line
        else ""
    )
    name_html = html.escape(name) if name else "Candidate"
    html_body = f"""<!DOCTYPE html>
<html><body style="font-family:Segoe UI,system-ui,sans-serif;line-height:1.5;color:#1a1a1a;">
  <p>{html.escape(greeting)}</p>
  <p><strong>{html.escape(company)}</strong> invites you to a voice interview.</p>
  <p><strong>Interview:</strong> {html.escape(title)}<br/>
     <strong>Candidate:</strong> {name_html}</p>
  <p>{html.escape(desc)}</p>
  {skills_html}
  <p><a href="{html.escape(candidate_url)}" style="display:inline-block;padding:10px 16px;background:#3d8bfd;color:#fff;text-decoration:none;border-radius:6px;">
    Open interview link
  </a></p>
  <p style="word-break:break-all;font-size:13px;color:#555;">{html.escape(candidate_url)}</p>
  <p><strong>Instructions</strong></p>
  <ol>
    <li>Open the interview link on a laptop or desktop if possible.</li>
    <li>Use a quiet place and allow microphone access when prompted.</li>
    <li>Complete the welcome steps, then start when you are ready.</li>
    <li>Speak clearly; the interviewer will ask follow-up questions.</li>
  </ol>
  <p style="font-size:13px;color:#555;">No account password is required — open the link to begin.</p>
  <p>— {html.escape(company)}</p>
</body></html>"""

    return {"subject": subject, "text": text, "html": html_body}


def send_email(*, to_addr: str, subject: str, text: str, html_body: str) -> None:
    """Send multipart email via SMTP. Raises ValueError / smtplib errors."""
    to_addr = (to_addr or "").strip()
    if not to_addr or "@" not in to_addr:
        raise ValueError("A valid candidate email address is required.")
    if not smtp_configured():
        raise ValueError(
            "SMTP is not configured. Set SMTP_HOST, SMTP_USER, SMTP_PASSWORD, "
            "and EMAIL_FROM (Copy link still works without email)."
        )

    s = smtp_settings()
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = s["email_from"]
    msg["To"] = to_addr
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP(s["host"], s["port"], timeout=30) as server:
            server.ehlo()
            if s["port"] != 465:
                server.starttls(context=context)
                server.ehlo()
            server.login(s["user"], s["password"])
            server.sendmail(s["email_from"], [to_addr], msg.as_string())
    except smtplib.SMTPException as e:
        logger.warning("SMTP send failed to %s: %s", to_addr, type(e).__name__)
        raise ValueError(f"Failed to send email: {e}") from e
    except OSError as e:
        logger.warning("SMTP connection failed: %s", type(e).__name__)
        raise ValueError(f"Failed to connect to SMTP server: {e}") from e


def send_invite_email(invite: dict[str, Any], *, to_override: str | None = None) -> dict[str, str]:
    """Build and send invitation for an invite record. Returns {to, subject}."""
    to_addr = (to_override or invite.get("candidate_email") or "").strip()
    built = build_invite_email(
        candidate_url=invite.get("candidate_url") or "",
        display_title=invite.get("display_title")
        or invite.get("label")
        or invite.get("target_role")
        or "Interview",
        description=invite.get("description"),
        candidate_name=invite.get("candidate_name"),
        suggested_skills=invite.get("suggested_skills") or [],
    )
    send_email(
        to_addr=to_addr,
        subject=built["subject"],
        text=built["text"],
        html_body=built["html"],
    )
    return {"to": to_addr, "subject": built["subject"]}
