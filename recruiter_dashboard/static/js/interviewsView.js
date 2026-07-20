import { createInterview, fetchInterviews, fetchRoles } from "./api.js";

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

export function createInterviewsView() {
  const roleSelect = document.getElementById("target-role");
  const labelInput = document.getElementById("invite-label");
  const form = document.getElementById("create-form");
  const btnCreate = document.getElementById("btn-create");
  const resultBox = document.getElementById("create-result");
  const urlInput = document.getElementById("candidate-url");
  const btnCopy = document.getElementById("btn-copy");
  const copyFeedback = document.getElementById("copy-feedback");
  const tbody = document.getElementById("invites-body");
  const btnRefresh = document.getElementById("btn-refresh-invites");

  async function loadRoles() {
    const data = await fetchRoles();
    const roles = data.roles || [];
    roleSelect.innerHTML = roles
      .map(
        (r) =>
          `<option value="${escapeHtml(r.key)}">${escapeHtml(r.display_title)}</option>`
      )
      .join("");
  }

  async function loadInvites() {
    const data = await fetchInterviews();
    const invites = data.invites || [];
    if (!invites.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty">No invites yet.</td></tr>`;
      return;
    }
    tbody.innerHTML = invites
      .map((inv) => {
        const status = inv.status || "pending";
        const url = inv.candidate_url || "";
        return `<tr>
          <td>${escapeHtml(formatWhen(inv.created_at))}</td>
          <td>${escapeHtml(inv.target_role)}</td>
          <td>${escapeHtml(inv.label || "—")}</td>
          <td><span class="badge ${escapeHtml(status)}">${escapeHtml(status)}</span></td>
          <td>
            <div class="actions">
              <button type="button" class="btn ghost btn-copy-row" data-url="${escapeHtml(url)}">Copy</button>
            </div>
          </td>
        </tr>`;
      })
      .join("");

    tbody.querySelectorAll(".btn-copy-row").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const url = btn.getAttribute("data-url") || "";
        if (!url) return;
        try {
          await navigator.clipboard.writeText(url);
          btn.textContent = "Copied";
          setTimeout(() => {
            btn.textContent = "Copy";
          }, 1500);
        } catch {
          window.prompt("Copy this link:", url);
        }
      });
    });
  }

  form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    btnCreate.disabled = true;
    copyFeedback.hidden = true;
    try {
      const invite = await createInterview({
        target_role: roleSelect.value,
        label: labelInput.value.trim(),
      });
      urlInput.value = invite.candidate_url || "";
      resultBox.hidden = false;
      await loadInvites();
    } catch (err) {
      alert(`Could not create interview: ${err.message}`);
    } finally {
      btnCreate.disabled = false;
    }
  });

  btnCopy?.addEventListener("click", async () => {
    const url = urlInput.value;
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      copyFeedback.textContent = "Copied to clipboard.";
      copyFeedback.hidden = false;
    } catch {
      urlInput.select();
      copyFeedback.textContent = "Select the link and copy manually (Ctrl+C).";
      copyFeedback.hidden = false;
    }
  });

  btnRefresh?.addEventListener("click", () => loadInvites().catch(console.error));

  return {
    async init() {
      await loadRoles();
      await loadInvites();
    },
    refresh: loadInvites,
  };
}
