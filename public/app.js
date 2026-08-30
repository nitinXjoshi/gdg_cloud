function getApiBase() {
  if (typeof window.PROMPTFORGE_API_BASE === "string" && window.PROMPTFORGE_API_BASE.trim() !== "") {
    return window.PROMPTFORGE_API_BASE.trim().replace(/\/+$/, "");
  }

  const isLocal =
    window.location.hostname === "localhost" ||
    window.location.hostname === "127.0.0.1" ||
    window.location.hostname === "0.0.0.0";

  if (isLocal) {
    if (window.location.port === "8000" || window.location.port === "") {
      return "";
    }
    return "http://localhost:8000";
  }

  // Deployed host: same-origin API requests (never require ?api= or manual config)
  return "";
}

let API_BASE = getApiBase();

function updateApiEndpointUI() {
  const label = $("#api-endpoint-label");
  if (!label) return;
  if (API_BASE === "") {
    label.textContent = "Cloud (Same-Origin)";
  } else {
    label.textContent = "Localhost:8000";
  }
}

const state = {
  token: localStorage.getItem("promptforge_token") || null,
  challengeId: null,
};

const $ = (sel) => document.querySelector(sel);

function toast(message, type = "") {
  const el = $("#toast");
  if (!el) return;
  el.textContent = message;
  el.className = "toast show " + type;
  setTimeout(() => (el.className = "toast"), 3500);
}

async function api(path, options = {}, isRetry = false) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (state.token) headers["Authorization"] = `Bearer ${state.token}`;

  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  } catch (_) {
    throw new Error("Backend unavailable. Please try again.");
  }

  // Automatic token refresh / re-mint if session expired
  if (res.status === 401 && !isRetry && path !== "/api/v1/auth/session") {
    try {
      await createSession(true);
      return await api(path, options, true);
    } catch (_) {
      // Continue to handle 401 error below
    }
  }

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

async function createSession(silent = false) {
  const btn = $("#new-session-btn");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Connecting…";
  }
  try {
    const res = await api("/api/v1/auth/session", { method: "POST", body: "{}" }, true);
    state.token = res.api_token;
    localStorage.setItem("promptforge_token", res.api_token);
    const badge = $("#session-badge");
    if (badge) {
      badge.textContent = "SESSION ACTIVE";
      badge.className = "badge badge-active";
    }
    if (!silent) toast("Attacker session initialized", "success");
    return res.api_token;
  } catch (err) {
    const badge = $("#session-badge");
    if (badge) {
      badge.textContent = "SESSION IDLE";
      badge.className = "badge badge-idle";
    }
    if (!silent) toast(`Session initialization: ${err.message}`, "error");
    throw err;
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Initialize Session";
    }
  }
}

async function loadChallenge() {
  const challenges = await api("/api/v1/challenges");
  if (!challenges || !challenges.length) {
    throw new Error("No active challenges found");
  }
  const c = challenges[0];
  state.challengeId = c.challenge_id;
  $("#challenge-name").textContent = c.name;
  $("#challenge-difficulty").textContent = `DIFFICULTY: ${c.difficulty.toUpperCase()} · ${c.model.toUpperCase()}`;
  const descEl = $("#challenge-description");
  if (descEl) {
    descEl.textContent = c.description;
    if (descEl.style) descEl.style.display = "none";
  }
}

function fmtIntOrNA(value) {
  return value === null || value === undefined ? "Not available" : value.toLocaleString();
}

async function loadStats() {
  try {
    const s = await api("/api/v1/stats");
    $("#s-attempts").textContent = fmtIntOrNA(s.total_attempts);
    $("#s-rate").textContent = `${(s.success_rate * 100).toFixed(1)}%`;
    $("#s-participants").textContent = fmtIntOrNA(s.active_participants);
    $("#s-rpm").textContent = s.requests_per_minute.toFixed(1);
    $("#s-avg").textContent = s.avg_latency_ms ? `${s.avg_latency_ms.toFixed(0)} ms` : "—";
    $("#s-err").textContent = `${(s.error_rate * 100).toFixed(1)}%`;
  } catch (_) {}
}

async function submitPrompt() {
  const input = $("#prompt-input");
  const prompt = input.value.trim();
  if (!prompt) return toast("Attack payload cannot be empty", "error");

  // Ensure session is available
  if (!state.token) {
    try {
      await createSession(true);
    } catch (_) {
      return toast("Backend unavailable. Please try again.", "error");
    }
  }

  if (!state.challengeId) {
    try {
      await loadChallenge();
    } catch (_) {
      return toast("Backend unavailable. Please try again.", "error");
    }
  }

  const btn = $("#submit-btn");
  btn.disabled = true;
  btn.textContent = "Executing Attack…";

  try {
    const res = await api(`/api/v1/challenges/${state.challengeId}/attempt`, {
      method: "POST",
      body: JSON.stringify({ prompt }),
    });

    $("#response-output").textContent = res.response || "(empty response)";
    $("#response-output").classList.toggle("solved", res.challenge_solved);
    $("#latency-label").textContent = `Inference: ${res.latency_ms.toFixed(0)} ms`;

    const solvedChip = $("#solved-chip");
    if (res.challenge_solved) {
      solvedChip.classList.add("solved");
      solvedChip.innerHTML = '<span class="dot"></span><span>BREACH CONFIRMED</span>';
      toast("FLAG EXTRACTED — BREACH CONFIRMED!", "success");
    }

    $("#d-request-id").textContent = res.request_id;
    $("#d-latency").textContent = `${res.latency_ms.toFixed(1)} ms`;

    const usage = res.usage || {};
    if (usage.available) {
      $("#d-input").textContent = fmtIntOrNA(usage.input_tokens);
      $("#d-output").textContent = fmtIntOrNA(usage.output_tokens);
      $("#d-total").textContent = fmtIntOrNA(usage.total_tokens);
    } else {
      $("#d-input").textContent = "Not available";
      $("#d-output").textContent = "Not available";
      $("#d-total").textContent = "Not available";
    }

    $("#d-model").textContent = res.model || "—";
    $("#d-solved").textContent = res.challenge_solved ? "YES (Breach Confirmed)" : "NO";

    loadStats();
  } catch (err) {
    toast(err.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Send Attack";
  }
}

$("#new-session-btn").addEventListener("click", () => {
  localStorage.removeItem("promptforge_token");
  state.token = null;
  const chip = $("#solved-chip");
  if (chip) {
    if (chip.classList) chip.classList.remove("solved");
    chip.innerHTML = '<span class="dot"></span><span>LOCKED (UNSOLVED)</span>';
  }
  createSession();
});

$("#submit-btn").addEventListener("click", submitPrompt);
$("#prompt-input").addEventListener("input", (e) => {
  $("#char-count").textContent = `${e.target.value.length} chars`;
});
$("#prompt-input").addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") submitPrompt();
});

async function init() {
  updateApiEndpointUI();

  try {
    // 1. Ensure participant session is active (auto-mint on first arrival)
    if (!state.token) {
      try {
        await createSession(true);
      } catch (_) {
        // Will be caught below if backend is unreachable
      }
    } else {
      const badge = $("#session-badge");
      if (badge) {
        badge.textContent = "SESSION ACTIVE";
        badge.className = "badge badge-active";
      }
    }

    // 2. Probe live /health endpoint for real backend and Ollama status
    try {
      const h = await api("/health");
      const badge = $("#system-badge");
      const statusText = $("#system-status-text");
      if (badge && statusText) {
        if (h.ollama === "healthy" && h.model === "available") {
          badge.className = "system-badge";
          statusText.textContent = `LIVE OLLAMA · ${(h.model_name || "llama3.2:3b").toUpperCase()}`;
        } else if (h.ollama === "healthy") {
          badge.className = "system-badge badge-warning";
          statusText.textContent = `OLLAMA CONNECTED (${(h.model || "no model").toUpperCase()})`;
        } else {
          badge.className = "system-badge badge-warning";
          statusText.textContent = "OLLAMA OFFLINE";
        }
      }
    } catch (_) {
      // /health failure falls through
    }

    await loadChallenge();
    await loadStats();

    const descEl = $("#challenge-description");
    if (descEl && descEl.style) {
      descEl.style.color = "";
      descEl.style.display = "none";
    }
  } catch (err) {
    const badge = $("#system-badge");
    const statusText = $("#system-status-text");
    if (badge && statusText) {
      badge.className = "system-badge badge-offline";
      statusText.textContent = "BACKEND UNAVAILABLE";
    }
    $("#challenge-name").textContent = "PromptForge Challenge";
    $("#challenge-difficulty").textContent = "TARGET: CLOUD OLLAMA · CONNECTING…";
    const descEl = $("#challenge-description");
    if (descEl) {
      if (descEl.style) {
        descEl.style.display = "block";
        descEl.style.color = "var(--crimson, #ff4b4b)";
      }
      descEl.textContent = "Backend unavailable. Please try again.";
    }
    toast("Backend unavailable. Please try again.", "error");
  }
}

init();
