/**
 * settings.js — Provider connection panel.
 *
 * Drives the auth pipelines (Phase 4):
 *  - Codex: POST /api/auth/codex/login → the server opens the authUrl in a
 *    browser; codex owns the callback and writes ~/.codex; this panel polls
 *    GET /api/auth/codex/status until the account appears.
 *  - Mistral: POST /api/auth/mistral/start returns a sign_in_url (opened
 *    here), GET /api/auth/mistral/poll is polled (3s, upstream cadence) and
 *    POST /api/auth/mistral/complete exchanges + stores the key when the
 *    flow reports completed. The key itself never crosses this API.
 *  - Model list + usage come from GET /api/models and GET /api/usage.
 */

(() => {
  const $ = (id) => document.getElementById(id);
  const dialog = $("settings-dialog");
  if (!dialog) return;

  const POLL_MS = 3000; // upstream wizard cadence

  async function api(path, opts) {
    const response = await fetch(path, opts);
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.error || `HTTP ${response.status}`);
    }
    return response.json();
  }

  async function refreshModels() {
    const { models } = await api("/api/models");
    const list = $("settings-models");
    list.innerHTML = "";
    for (const model of models) {
      const li = document.createElement("li");
      li.className = model.available ? "available" : "unavailable";
      li.textContent = `${model.display_name} — ${model.available ? "connected" : "not configured"}`;
      list.appendChild(li);
    }
  }

  async function refreshCodexStatus() {
    const status = await api("/api/auth/codex/status");
    $("codex-status").textContent = status.authenticated
      ? `Signed in: ${status.email || status.type} (${status.planType || "?"})`
      : (status.error || "Not signed in");
    return status;
  }

  async function refreshUsage() {
    const totals = await api("/api/usage").catch(() => null);
    if (!totals) return;
    const cost = totals.cost_usd != null ? ` · $${totals.cost_usd.toFixed(4)}` : "";
    $("usage-summary").textContent =
      `Tokens: ${totals.total_tokens.toLocaleString()} · Calls: ${totals.calls}${cost}`;
  }

  async function refreshAll() {
    try {
      await Promise.all([refreshModels(), refreshCodexStatus(), refreshUsage()]);
    } catch (error) {
      $("mistral-status").textContent = error.message;
    }
  }

  async function connectCodex() {
    $("codex-status").textContent = "Opening browser…";
    try {
      await api("/api/auth/codex/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ open_browser: true }),
      });
    } catch (error) {
      $("codex-status").textContent = error.message;
      return;
    }
    const poll = setInterval(async () => {
      const status = await refreshCodexStatus();
      if (status.authenticated) {
        clearInterval(poll);
        refreshAll();
      }
    }, POLL_MS);
  }

  async function connectMistral() {
    $("mistral-status").textContent = "Starting browser sign-in…";
    let summary;
    try {
      summary = await api("/api/auth/mistral/start", { method: "POST" });
    } catch (error) {
      $("mistral-status").textContent = error.message;
      return;
    }
    if (summary.sign_in_url) window.open(summary.sign_in_url, "_blank");
    $("mistral-status").textContent = "Waiting for sign-in…";
    const poll = setInterval(async () => {
      try {
        const state = await api("/api/auth/mistral/poll");
        $("mistral-status").textContent = `Mistral: ${state.status}`;
        if (state.status === "completed") {
          clearInterval(poll);
          const result = await api("/api/auth/mistral/complete", { method: "POST" });
          $("mistral-status").textContent = `Mistral connected (${result.health})`;
          refreshAll();
        } else if (["expired", "denied", "error"].includes(state.status)) {
          clearInterval(poll);
          $("mistral-status").textContent = `Mistral: ${state.message || state.status}`;
        }
      } catch (error) {
        clearInterval(poll);
        $("mistral-status").textContent = error.message;
      }
    }, POLL_MS);
  }

  $("settings-btn").addEventListener("click", () => {
    dialog.showModal();
    refreshAll();
  });
  $("settings-close-btn").addEventListener("click", () => dialog.close());
  $("codex-login-btn").addEventListener("click", connectCodex);
  $("mistral-login-btn").addEventListener("click", connectMistral);
})();
