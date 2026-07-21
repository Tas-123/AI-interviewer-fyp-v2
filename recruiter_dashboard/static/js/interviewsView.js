import {
  createInterview,
  fetchEmailStatus,
  fetchInterviews,
  fetchRoles,
  sendInvitation,
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

export function createInterviewsView() {
  const roleSelect = document.getElementById("target-role");
  const labelInput = document.getElementById("invite-label");
  const nameInput = document.getElementById("candidate-name");
  const emailInput = document.getElementById("candidate-email");
  const form = document.getElementById("create-form");
  const btnCreate = document.getElementById("btn-create");
  const resultBox = document.getElementById("create-result");
  const urlInput = document.getElementById("candidate-url");
  const btnCopy = document.getElementById("btn-copy");
  const btnSend = document.getElementById("btn-send-invite");
  const sendHint = document.getElementById("send-hint");
  const copyFeedback = document.getElementById("copy-feedback");
  const sendFeedback = document.getElementById("send-feedback");
  const smtpHint = document.getElementById("email-smtp-hint");
  const tbody = document.getElementById("invites-body");
  const btnRefresh = document.getElementById("btn-refresh-invites");

  let rolesCache = [];
  let smtpConfigured = false;
  let lastInvite = null;

  function updateSendButtonState() {
    if (!btnSend) return;
    const email =
      (emailInput?.value || "").trim() ||
      (lastInvite?.candidate_email || "").trim();
    const canSend = Boolean(email && smtpConfigured && lastInvite?.invite_token);
    btnSend.disabled = !canSend;
    if (sendHint) {
      if (!smtpConfigured) {
        sendHint.textContent = "Configure SMTP in .env to enable Send invitation.";
      } else if (!email) {
        sendHint.textContent = "Enter a candidate email to send the invitation.";
      } else {
        sendHint.textContent = "Sends company name, title, link, and instructions (no password).";
      }
    }
  }

  async function loadEmailStatus() {
    try {
      const status = await fetchEmailStatus();
      smtpConfigured = Boolean(status.configured);
      if (smtpHint) {
        smtpHint.textContent = smtpConfigured
          ? `Email ready (${status.company_name || "company"}). Copy link always works.`
          : "Copy link always works. Send invitation needs SMTP in .env.";
      }
    } catch {
      smtpConfigured = false;
    }
    updateSendButtonState();
  }

  async function loadRoles() {
    const data = await fetchRoles();
    rolesCache = data.roles || [];
    if (!roleSelect) return;
    roleSelect.innerHTML = rolesCache
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
      tbody.innerHTML = `<tr><td colspan="6" class="empty">No invites yet.</td></tr>`;
      return;
    }
    tbody.innerHTML = invites
      .map((inv) => {
        const status = inv.status || "pending";
        const url = inv.candidate_url || "";
        const roleCell = escapeHtml(inv.display_title || inv.target_role);
        const emailCell = inv.email_sent_at
          ? `Sent ${escapeHtml(formatWhen(inv.email_sent_at))}`
          : escapeHtml(inv.candidate_email || "—");
        return `<tr>
          <td>${escapeHtml(formatWhen(inv.created_at))}</td>
          <td>${roleCell}</td>
          <td>${escapeHtml(inv.label || "—")}</td>
          <td><span class="badge ${escapeHtml(status)}">${escapeHtml(status)}</span></td>
          <td>${emailCell}</td>
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
    btnCreate && (btnCreate.disabled = true);
    if (copyFeedback) copyFeedback.hidden = true;
    if (sendFeedback) sendFeedback.hidden = true;
    try {
      const invite = await createInterview({
        target_role: roleSelect?.value || "junior_ai_engineer",
        label: labelInput?.value?.trim() || null,
        candidate_email: emailInput?.value?.trim() || null,
        candidate_name: nameInput?.value?.trim() || null,
      });
      lastInvite = invite;
      if (urlInput) urlInput.value = invite.candidate_url || "";
      if (resultBox) resultBox.hidden = false;
      updateSendButtonState();
      await loadInvites();
    } catch (err) {
      alert(`Could not create interview: ${err.message}`);
    } finally {
      btnCreate && (btnCreate.disabled = false);
    }
  });

  emailInput?.addEventListener("input", updateSendButtonState);

  btnCopy?.addEventListener("click", async () => {
    const url = urlInput.value;
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      if (copyFeedback) {
        copyFeedback.textContent = "Copied to clipboard.";
        copyFeedback.hidden = false;
      }
    } catch {
      urlInput.select();
      if (copyFeedback) {
        copyFeedback.textContent = "Select the link and copy manually (Ctrl+C).";
        copyFeedback.hidden = false;
      }
    }
  });

  btnSend?.addEventListener("click", async () => {
    if (!lastInvite?.invite_token) return;
    const email =
      (emailInput?.value || "").trim() ||
      (lastInvite.candidate_email || "").trim();
    if (!email) {
      updateSendButtonState();
      return;
    }
    btnSend.disabled = true;
    if (sendFeedback) sendFeedback.hidden = true;
    try {
      const result = await sendInvitation(lastInvite.invite_token, {
        candidate_email: email,
        candidate_name: (nameInput?.value || "").trim() || null,
      });
      lastInvite = {
        ...lastInvite,
        candidate_email: email,
        email_sent_at: result.email_sent_at,
      };
      if (sendFeedback) {
        sendFeedback.textContent = `Invitation sent to ${result.to}.`;
        sendFeedback.hidden = false;
      }
      await loadInvites();
    } catch (err) {
      if (sendFeedback) {
        sendFeedback.textContent = err.message || "Send failed.";
        sendFeedback.hidden = false;
      } else {
        alert(err.message);
      }
    } finally {
      updateSendButtonState();
    }
  });

  btnRefresh?.addEventListener("click", () => loadInvites().catch(console.error));

  return {
    async init() {
      await loadRoles();
      await loadEmailStatus();
      await loadInvites();
    },
    refresh: loadInvites,
  };
}
