import {
  fetchReport,
  fetchReports,
  reportHtmlDownloadUrl,
  reportHtmlUrl,
} from "./api.js";

function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatWhen(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

function scoreCell(card) {
  if (card.overall_score == null || card.overall_score === "") return "—";
  const label = card.overall_label ? ` (${card.overall_label})` : "";
  return `${escapeHtml(card.overall_score)}${escapeHtml(label)}`;
}

function htmlActionLinks(sessionId, hasHtml, { primaryFull = false } = {}) {
  if (!hasHtml) {
    return `<span class="badge incomplete">No HTML</span>`;
  }
  const viewUrl = escapeHtml(reportHtmlUrl(sessionId));
  const dlUrl = escapeHtml(reportHtmlDownloadUrl(sessionId));
  const fullClass = primaryFull ? "btn primary" : "btn ghost";
  return `
    <a class="${fullClass}" href="${viewUrl}" target="_blank" rel="noopener">Full Report</a>
    <a class="btn ghost" href="${dlUrl}" download>Download</a>
  `;
}

function rowActionGroup(sessionId, hasHtml) {
  const sid = escapeHtml(sessionId);
  return `
    <div class="action-group">
      <button type="button" class="btn primary btn-view" data-session="${sid}">View</button>
      ${htmlActionLinks(sessionId, hasHtml)}
    </div>
  `;
}

export function createReportsView() {
  const tbody = document.getElementById("reports-body");
  const btnRefresh = document.getElementById("btn-refresh-reports");
  const modal = document.getElementById("report-modal");
  const detailTitle = document.getElementById("detail-title");
  const detailBody = document.getElementById("detail-body");
  const detailFooter = document.getElementById("detail-footer");
  const btnClose = document.getElementById("btn-close-detail");

  let lastFocus = null;

  function closeModal() {
    if (!modal || modal.hidden) return;
    modal.hidden = true;
    modal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("modal-open");
    if (detailBody) detailBody.innerHTML = "";
    if (detailFooter) {
      detailFooter.innerHTML = "";
      detailFooter.hidden = true;
    }
    if (lastFocus && typeof lastFocus.focus === "function") {
      lastFocus.focus();
    }
    lastFocus = null;
  }

  function openModalShell() {
    if (!modal) return;
    lastFocus = document.activeElement;
    modal.hidden = false;
    modal.setAttribute("aria-hidden", "false");
    document.body.classList.add("modal-open");
    btnClose?.focus();
  }

  async function showDetail(sessionId) {
    openModalShell();
    detailTitle.textContent = "Loading report…";
    detailBody.innerHTML = `<p class="narrative">Fetching Report v2…</p>`;
    if (detailFooter) {
      detailFooter.hidden = true;
      detailFooter.innerHTML = "";
    }

    try {
      const data = await fetchReport(sessionId);
      const report = data.report || {};
      const meta = report.report_meta || {};
      const ratings = report.ratings_summary || {};
      const rec = ratings.final_recommendation || {};
      const overall = ratings.overall_performance || {};
      const tech = ratings.technical_performance || {};
      const comm = ratings.communication_skills || {};
      const hasHtml = Boolean(data.html_file);

      detailTitle.textContent =
        meta.candidate_display_name || "Candidate report";

      detailBody.innerHTML = `
        <dl class="detail-grid">
          <div class="stat"><dt>Role</dt><dd>${escapeHtml(meta.role_title || "—")}</dd></div>
          <div class="stat"><dt>Type</dt><dd><span class="badge ${escapeHtml(meta.report_type || "")}">${escapeHtml(meta.report_type || "—")}</span></dd></div>
          <div class="stat"><dt>Hire signal</dt><dd>${escapeHtml(rec.signal || "N/A")}</dd></div>
          <div class="stat"><dt>Overall</dt><dd>${escapeHtml(overall.score ?? "—")} ${escapeHtml(overall.label || "")}</dd></div>
          <div class="stat"><dt>Technical</dt><dd>${escapeHtml(tech.score ?? "—")} ${escapeHtml(tech.label || "")}</dd></div>
          <div class="stat"><dt>Communication</dt><dd>${escapeHtml(comm.score ?? "—")} ${escapeHtml(comm.label || "")}</dd></div>
          <div class="stat"><dt>Generated</dt><dd>${escapeHtml(formatWhen(meta.generated_at))}</dd></div>
          <div class="stat"><dt>Session</dt><dd class="mono">${escapeHtml(meta.session_id || sessionId)}</dd></div>
        </dl>
        <p class="narrative"><strong>Executive summary</strong><br/>${escapeHtml(report.executive_summary || "—")}</p>
        <p class="narrative"><strong>Overall summary</strong><br/>${escapeHtml(report.overall_summary || "—")}</p>
        <p class="narrative"><strong>Recommendation rationale</strong><br/>${escapeHtml(rec.rationale || "—")}</p>
      `;

      if (detailFooter && hasHtml) {
        detailFooter.hidden = false;
        detailFooter.innerHTML = htmlActionLinks(sessionId, true, {
          primaryFull: true,
        });
      }
    } catch (err) {
      detailTitle.textContent = "Report unavailable";
      detailBody.innerHTML = `<p class="narrative">${escapeHtml(err.message)}</p>`;
    }
  }

  async function loadReports() {
    const data = await fetchReports();
    const reports = data.reports || [];
    if (!reports.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="empty">No reports found in the reports/ folder yet. Complete a voice interview to generate one.</td></tr>`;
      return;
    }
    tbody.innerHTML = reports
      .map((card) => {
        const sid = card.session_id || "";
        const type = card.report_type || "";
        return `<tr>
          <td>${escapeHtml(formatWhen(card.generated_at))}</td>
          <td>${escapeHtml(card.candidate_display_name)}</td>
          <td>${escapeHtml(card.role_title || "—")}</td>
          <td><span class="badge ${escapeHtml(type)}">${escapeHtml(type)}</span></td>
          <td>${escapeHtml(card.hire_signal || "N/A")}</td>
          <td>${scoreCell(card)}</td>
          <td>${rowActionGroup(sid, Boolean(card.has_html))}</td>
        </tr>`;
      })
      .join("");

    tbody.querySelectorAll(".btn-view").forEach((btn) => {
      btn.addEventListener("click", () => {
        const sid = btn.getAttribute("data-session");
        if (sid) showDetail(sid);
      });
    });
  }

  btnRefresh?.addEventListener("click", () => loadReports().catch(console.error));
  btnClose?.addEventListener("click", closeModal);

  modal?.querySelectorAll("[data-modal-close]").forEach((el) => {
    el.addEventListener("click", closeModal);
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal && !modal.hidden) {
      e.preventDefault();
      closeModal();
    }
  });

  return {
    async init() {
      await loadReports();
    },
    refresh: loadReports,
  };
}
