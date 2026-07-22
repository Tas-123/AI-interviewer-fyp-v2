"""Insert a university-standard Table of Contents into final_fyp_report_01.docx.

Only the CONTENTS section is modified. Body chapters are left untouched.
Page numbers are taken from Microsoft Word (absolute pages), then mapped to
roman numerals for front matter and arabic pages restarting at Chapter 1.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import win32com.client
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, Twips

DOC = Path(r"d:\application_v01\AI-interviewer-fyp-v2\FYP_report\final_fyp_report_01.docx")
BACKUP = Path(
    r"d:\application_v01\AI-interviewer-fyp-v2\FYP_report\final_fyp_report_01_backup_before_toc.docx"
)

# Absolute Word page of CHAPTER 01 title → body arabic page 1
BODY_PAGE_OFFSET = 11

CHALLENGE_SUBS = {
    "Voice Processing",
    "Transcript Fragmentation",
    "Adaptive Interview Flow",
    "Meta Conversation",
    "Fair Evaluation",
    "Live Voice Reliability",
}
ENGINE_SUBS = {"Guard Pipeline", "Decision Engine", "Coverage Engine"}


def to_roman(n: int) -> str:
    vals = [
        (1000, "m"),
        (900, "cm"),
        (500, "d"),
        (400, "cd"),
        (100, "c"),
        (90, "xc"),
        (50, "l"),
        (40, "xl"),
        (10, "x"),
        (9, "ix"),
        (5, "v"),
        (4, "iv"),
        (1, "i"),
    ]
    out = []
    for v, s in vals:
        while n >= v:
            out.append(s)
            n -= v
    return "".join(out)


def format_page(abs_page: int, front: bool) -> str:
    if front:
        return to_roman(max(1, abs_page))
    return str(max(1, abs_page - BODY_PAGE_OFFSET))


def build_outline(doc: Document) -> list[dict]:
    """Canonical TOC hierarchy from report structure (excludes Contents itself)."""
    outline: list[dict] = [
        {"level": 0, "title": "Abstract", "find": "ABSTRACT", "front": True},
        {"level": 0, "title": "Dedication", "find": "DEDICATION", "front": True},
        {"level": 0, "title": "Acknowledgments", "find": "ACKNOWLEDGMENTS", "front": True},
        {"level": 0, "title": "Project Brief", "find": "PROJECT BRIEF", "front": True},
        {"level": 0, "title": "List of Figures", "find": "LIST OF FIGURES", "front": True},
        {"level": 0, "title": "List of Tables", "find": "LIST OF TABLES", "front": True},
        {
            "level": 0,
            "title": "List of Abbreviations",
            "find": "LIST OF ABBREVIATIONS",
            "front": True,
        },
    ]

    # Skip front-matter / TOC / LoF / LoT / abbreviations when scanning body
    start = None
    for i, para in enumerate(doc.paragraphs):
        if para.text.strip().upper() == "CHAPTER 01":
            start = i
            break
    if start is None:
        raise RuntimeError("CHAPTER 01 not found")

    seen_finds: set[str] = set()
    ch2_seen = ch3_seen = ch4_seen = ch5_seen = ch6_seen = ch7_seen = False
    app_b_seen = app_c_seen = False
    bib_seen = False

    for i in range(start, len(doc.paragraphs)):
        para = doc.paragraphs[i]
        t = para.text.strip()
        if not t or len(t) > 140:
            continue
        st = para.style.name

        if re.match(r"^CHAPTER\s*0?1$", t, re.I):
            outline.append(
                {"level": 1, "title": "1  Introduction", "find": "CHAPTER 01", "front": False}
            )
            continue
        if t.upper() == "INTRODUCTION" and st.startswith("Heading"):
            # Duplicate of chapter title — omit from TOC
            continue
        if re.match(r"^Chapter\s*0?2$", t, re.I) and not ch2_seen:
            ch2_seen = True
            outline.append(
                {
                    "level": 1,
                    "title": "2  Literature Review",
                    "find": "Chapter 02",
                    "front": False,
                }
            )
            continue
        if t == "Literature Review":
            continue
        if re.match(r"^Chapter\s*3$", t) and not ch3_seen:
            ch3_seen = True
            outline.append(
                {
                    "level": 1,
                    "title": "3  System Background",
                    "find": "Chapter 3",
                    "front": False,
                    "min_page": 20,
                }
            )
            continue
        if t == "System Background":
            continue
        if (t == "Chapter 4" or (st.startswith("Heading") and t.startswith("Chapter 4"))) and not ch4_seen:
            ch4_seen = True
            outline.append(
                {"level": 1, "title": "4  Methodology", "find": "Chapter 4", "front": False, "min_page": 40}
            )
            continue
        if t == "Methodology" and st.startswith("Heading"):
            continue
        if (t == "Chapter 5" or (st.startswith("Heading") and t.startswith("Chapter 5"))) and not ch5_seen:
            ch5_seen = True
            outline.append(
                {
                    "level": 1,
                    "title": "5  Results and Discussion",
                    "find": "Chapter 5",
                    "front": False,
                    "min_page": 55,
                }
            )
            continue
        if t == "Results and Discussion" and st.startswith("Heading"):
            continue
        if t == "Chapter 6" and not ch6_seen:
            ch6_seen = True
            outline.append(
                {
                    "level": 1,
                    "title": "6  System Design and Implementation",
                    "find": "Chapter 6",
                    "front": False,
                    "min_page": 65,
                }
            )
            continue
        if t == "System Design and Implementation":
            continue
        if t == "Chapter 7" and not ch7_seen:
            ch7_seen = True
            outline.append(
                {"level": 1, "title": "7  Conclusion", "find": "Chapter 7", "front": False, "min_page": 80}
            )
            continue
        if t == "Conclusion":
            continue
        if t == "Bibliography" and st.startswith("Heading") and not bib_seen:
            bib_seen = True
            outline.append(
                {
                    "level": 1,
                    "title": "Bibliography",
                    "find": "Bibliography",
                    "front": False,
                    "min_page": 85,
                }
            )
            continue
        if (t == "Chapter A" or t.startswith("Chapter A")) and st.startswith("Heading"):
            outline.append(
                {
                    "level": 1,
                    "title": "Appendix A  Project Configuration and System Information",
                    "find": "Chapter A",
                    "front": False,
                    "min_page": 90,
                }
            )
            continue
        if t == "Project Configuration and System Information":
            continue
        if t == "Appendix B" and not app_b_seen:
            app_b_seen = True
            outline.append(
                {
                    "level": 1,
                    "title": "Appendix B  Code Snippets",
                    "find": "Appendix B",
                    "front": False,
                    "min_page": 105,
                }
            )
            continue
        if t == "Code Snippets":
            continue
        if t == "Chapter C" and not app_c_seen:
            app_c_seen = True
            outline.append(
                {
                    "level": 1,
                    "title": "Appendix C  Sustainable Development Goals (SDGs)",
                    "find": "Chapter C",
                    "front": False,
                    "min_page": 125,
                }
            )
            continue
        if t.startswith("Alignment with Sustainable"):
            continue

        if re.match(r"^(Figure|Table|Fig\.|Listing|Transition|Phase )\b", t, re.I):
            continue

        m = re.match(r"^((?:\d+(?:\.\d+){1,3})|(?:[A-C]\.\d+(?:\.\d+)*))\s+(.+)$", t)
        if m and st.startswith("Heading"):
            num, rest = m.group(1), m.group(2)
            find = t
            if find in seen_finds:
                continue
            seen_finds.add(find)
            dots = num.count(".")
            level = 2 if dots == 1 else 3 if dots == 2 else 4
            outline.append({"level": level, "title": f"{num}  {rest}", "find": find, "front": False})
            continue

        if t in ENGINE_SUBS and st.startswith("Heading"):
            key = f"engine:{t}"
            if key not in seen_finds:
                seen_finds.add(key)
                outline.append({"level": 4, "title": t, "find": t, "front": False, "min_page": 70})
            continue
        if t in CHALLENGE_SUBS and st.startswith("Heading"):
            key = f"chal:{t}"
            if key not in seen_finds:
                seen_finds.add(key)
                outline.append({"level": 4, "title": t, "find": t, "front": False, "min_page": 100})
            continue

    return outline


def resolve_pages(outline: list[dict]) -> list[dict]:
    """Walk Word paragraphs once; assign first matching page in document order."""
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    path = str(DOC.resolve())
    wdoc = word.Documents.Open(path, ReadOnly=True)

    pending = list(outline)
    # index into pending for sequential assignment
    pi = 0
    n = wdoc.Paragraphs.Count
    print(f"Resolving pages across {n} Word paragraphs…")

    for i in range(1, n + 1):
        if pi >= len(pending):
            break
        p = wdoc.Paragraphs(i)
        t = p.Range.Text.replace("\r", "").replace("\x07", "").strip()
        if not t:
            continue
        # Skip dotted TOC lines in existing Contents
        if "...." in t or "…" in t:
            continue

        entry = pending[pi]
        find = entry["find"]
        min_page = entry.get("min_page", 0)
        matched = t == find or t.startswith(find)
        if matched:
            page = int(p.Range.Information(3))  # wdActiveEndPageNumber
            if page >= min_page:
                entry["abs_page"] = page
                entry["page"] = format_page(page, entry["front"])
                pi += 1

        if i % 400 == 0:
            print(f"  …para {i}/{n}, resolved {pi}/{len(pending)}")

    wdoc.Close(False)
    word.Quit()

    missing = [e for e in outline if "page" not in e]
    if missing:
        print("WARNING: unresolved TOC entries:")
        for e in missing:
            print(" ", e["title"], "find=", e["find"])
        # fallback: previous known pages or "?"
        for e in missing:
            e["page"] = "—"
            e["abs_page"] = None
    return outline


def set_run_font(run, *, bold: bool = False, size: float = 12):
    run.bold = bold
    run.font.name = "Times New Roman"
    run.font.size = Pt(size)
    r = run._element
    rPr = r.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    rFonts.set(qn("w:ascii"), "Times New Roman")
    rFonts.set(qn("w:hAnsi"), "Times New Roman")
    rFonts.set(qn("w:cs"), "Times New Roman")


def configure_toc_paragraph(paragraph, level: int):
    pf = paragraph.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(2)
    pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
    indent = {0: 0, 1: 0, 2: 0.25, 3: 0.5, 4: 0.75}.get(level, 0)
    pf.left_indent = Inches(indent)
    pf.first_line_indent = Inches(0)
    # Right-aligned tab with dot leaders near right margin (~6.5")
    tab_stops = pf.tab_stops
    # clear existing
    for ts in list(tab_stops):
        try:
            tab_stops.remove_tab_stop(ts.position)
        except Exception:
            pass
    tab_stops.add_tab_stop(Inches(6.3), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)


def clear_between(doc: Document, after_text: str, before_text: str) -> int:
    """Remove paragraphs strictly between two heading texts. Returns index of after heading."""
    after_i = before_i = None
    for i, para in enumerate(doc.paragraphs):
        t = para.text.strip().upper()
        if after_i is None and t == after_text.upper():
            after_i = i
        elif after_i is not None and before_i is None and t == before_text.upper():
            before_i = i
            break
    if after_i is None or before_i is None:
        raise RuntimeError(f"Could not locate CONTENTS window: {after_i}, {before_i}")
    # delete from before_i-1 down to after_i+1
    for i in range(before_i - 1, after_i, -1):
        el = doc.paragraphs[i]._element
        el.getparent().remove(el)
    return after_i


def insert_toc_entries(doc: Document, contents_idx: int, outline: list[dict]):
    contents = doc.paragraphs[contents_idx]
    # Ensure CONTENTS heading formatting
    contents.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in contents.runs:
        set_run_font(run, bold=True, size=14)

    # Insert blank line then entries after CONTENTS (insert in reverse so order is preserved)
    # First create all new paragraph elements after contents
    anchor = contents._element
    created = []
    # blank spacer
    spacer = OxmlElement("w:p")
    anchor.addnext(spacer)
    created.append(spacer)
    anchor = spacer

    for _ in outline:
        p = OxmlElement("w:p")
        anchor.addnext(p)
        created.append(p)
        anchor = p

    # Map Oxml elements back to paragraph objects and fill
    # After insertion, find CONTENTS again
    c_idx = None
    for i, para in enumerate(doc.paragraphs):
        if para.text.strip().upper() == "CONTENTS":
            c_idx = i
            break
    assert c_idx is not None

    # paragraph at c_idx+1 is spacer; c_idx+2 .. are entries
    spacer_para = doc.paragraphs[c_idx + 1]
    spacer_para.paragraph_format.space_after = Pt(6)

    for j, entry in enumerate(outline):
        para = doc.paragraphs[c_idx + 2 + j]
        # clear any inherited text
        para.clear()
        configure_toc_paragraph(para, entry["level"])
        bold = entry["level"] <= 1
        size = 12 if entry["level"] <= 1 else 11
        run_t = para.add_run(entry["title"])
        set_run_font(run_t, bold=bold, size=size)
        para.add_run("\t")
        run_p = para.add_run(entry["page"])
        set_run_font(run_p, bold=False, size=size)


def main():
    if not DOC.exists():
        raise SystemExit(f"Missing {DOC}")

    shutil.copy2(DOC, BACKUP)
    print(f"Backup: {BACKUP}")

    # Outline from python-docx structure
    doc = Document(str(DOC))
    outline = build_outline(doc)
    print(f"Outline entries: {len(outline)}")

    # Resolve pages via Word (read-only)
    outline = resolve_pages(outline)

    # Re-open with python-docx for TOC rewrite only
    doc = Document(str(DOC))
    contents_idx = clear_between(doc, "CONTENTS", "LIST OF FIGURES")
    insert_toc_entries(doc, contents_idx, outline)
    doc.save(str(DOC))
    print(f"Saved TOC into {DOC}")

    # Verify
    doc2 = Document(str(DOC))
    printing = False
    count = 0
    for para in doc2.paragraphs:
        t = para.text.strip()
        if t.upper() == "CONTENTS":
            printing = True
            print("--- CONTENTS preview ---")
            continue
        if printing:
            if t.upper() == "LIST OF FIGURES":
                break
            if t:
                print(t[:100])
                count += 1
    print(f"TOC lines: {count}")


if __name__ == "__main__":
    main()
