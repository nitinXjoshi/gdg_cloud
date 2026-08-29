function getApiBase() {
  if (typeof window.PROMPTFORGE_API_BASE === "string" && window.PROMPTFORGE_API_BASE.trim() !== "") {
    return window.PROMPTFORGE_API_BASE.trim().replace(/\/+$/, "");
  }

  try {
    const params = new URLSearchParams(window.location.search);
    const apiParam = params.get("api");
    if (apiParam) {
      const clean = apiParam.trim().replace(/\/+$/, "");
      localStorage.setItem("promptforge_api_base", clean);
      return clean;
    }
  } catch (_) {}

  try {
    const stored = localStorage.getItem("promptforge_api_base");
    if (stored && stored.trim() !== "") {
      return stored.trim().replace(/\/+$/, "");
    }
  } catch (_) {}

  const isLocal =
    window.location.hostname === "localhost" ||
    window.location.hostname === "127.0.0.1" ||
    window.location.hostname === "0.0.0.0";

  if (isLocal) {
    if (window.location.port === "8000") {
      return "";
    }
    return "http://localhost:8000";
  }

  // Deployed host without configured backend: do not call Vercel origin!
  return null;
}

let API_BASE = getApiBase();

function updateApiEndpointUI() {
  const label = $("#api-endpoint-label");
  if (!label) return;
  if (API_BASE === null) {
    label.textContent = "Not Configured";
    return;
  }
  if (!API_BASE) {
    label.textContent = "Localhost:8000";
  } else {
    try {
      const u = new URL(API_BASE);
      label.textContent = u.host;
    } catch (_) {
      label.textContent = API_BASE.replace(/^https?:\/\//, "");
    }
  }
}

const state = {
  token: localStorage.getItem("promptforge_token") || null,
  challengeId: null,
};

const $ = (sel) => document.querySelector(sel);

function toast(message, type = "") {
  const el = $("#toast");
  el.textContent = message;
  el.className = "toast show " + type;
  setTimeout(() => (el.className = "toast"), 3500);
}

async function api(path, options = {}) {
  if (API_BASE === null) {
    throw new Error("Backend endpoint not configured");
  }
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (state.token) headers["Authorization"] = `Bearer ${state.token}`;
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
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

async function createSession() {
  if (API_BASE === null) {
    toast("Backend endpoint not configured. Set your public backend URL via ?api=<URL> or the API button above.", "error");
    return;
  }
  const btn = $("#new-session-btn");
  btn.disabled = true;
  btn.textContent = "Connecting…";
  try {
    const res = await api("/api/v1/auth/session", { method: "POST", body: "{}" });
    state.token = res.api_token;
    localStorage.setItem("promptforge_token", res.api_token);
    $("#session-badge").textContent = "SESSION ACTIVE";
    $("#session-badge").className = "badge badge-active";
    toast("Attacker session initialized", "success");
  } catch (err) {
    $("#session-badge").textContent = "SESSION FAILED";
    $("#session-badge").className = "badge badge-idle";
    toast(`Session initialization failed: ${err.message}`, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Initialize Session";
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
  if (API_BASE === null) {
    toast("Backend endpoint not configured. Click the API button above to set your backend URL.", "error");
    return;
  }
  if (!state.token) {
    toast("Initialize an attacker session first", "error");
    return;
  }
  if (!state.challengeId) {
    toast("No active challenge loaded. Backend endpoint may be unreachable.", "error");
    return;
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

const apiBtn = $("#api-config-btn");
if (apiBtn) {
  apiBtn.addEventListener("click", () => {
    const current = localStorage.getItem("promptforge_api_base") || (API_BASE ? API_BASE : "");
    const entered = prompt(
      "Configure PromptForge Backend API URL:\n(e.g. https://api.yourdomain.com or http://localhost:8000)\n\nLeave empty to reset to automatic detection:",
      current
    );
    if (entered === null) return;
    const clean = entered.trim().replace(/\/+$/, "");
    if (!clean) {
      localStorage.removeItem("promptforge_api_base");
      toast("Reset API endpoint to default", "success");
    } else {
      localStorage.setItem("promptforge_api_base", clean);
      toast(`API endpoint set to: ${clean}`, "success");
    }
    API_BASE = getApiBase();
    init();
  });
}

async function init() {
  updateApiEndpointUI();

  if (API_BASE === null) {
    const badge = $("#system-badge");
    const statusText = $("#system-status-text");
    if (badge && statusText) {
      badge.className = "system-badge badge-warning";
      statusText.textContent = "NO BACKEND CONFIGURED";
    }
    $("#challenge-name").textContent = "Backend endpoint not configured";
    $("#challenge-difficulty").textContent = "TARGET: NO BACKEND CONFIGURED";
    const descEl = $("#challenge-description");
    if (descEl) {
      if (descEl.style) {
        descEl.style.display = "block";
        descEl.style.color = "var(--amber, #f59e0b)";
      }
      descEl.textContent =
        "Backend endpoint not configured. Expose your local FastAPI backend with a public tunnel (e.g. cloudflared tunnel --url http://localhost:8000), then open this page with ?api=<PUBLIC-BACKEND-URL> or click the 'API' button above.";
    }
    return;
  }

  try {
    if (state.token) {
      $("#session-badge").textContent = "SESSION ACTIVE";
      $("#session-badge").className = "badge badge-active";
    }

    // Probe live /health endpoint for real backend and Ollama status
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
      // /health failure is handled in outer catch
    }

    await loadChallenge();
    await loadStats();

    const descEl = $("#challenge-description");
    if (descEl && descEl.style) {
      descEl.style.color = "";
      descEl.style.display = "none";
    }
  } catch (err) {
    const targetEndpoint = API_BASE || "Localhost:8000";
    const badge = $("#system-badge");
    const statusText = $("#system-status-text");
    if (badge && statusText) {
      badge.className = "system-badge badge-offline";
      statusText.textContent = "BACKEND DISCONNECTED";
    }
    $("#challenge-name").textContent = "Backend Connection Error";
    $("#challenge-difficulty").textContent = `TARGET: UNREACHABLE · ${targetEndpoint}`;
    const descEl = $("#challenge-description");
    if (descEl) {
      if (descEl.style) {
        descEl.style.display = "block";
        descEl.style.color = "var(--crimson, #ff4b4b)";
      }
      descEl.textContent = `Could not connect to backend at ${targetEndpoint} (${err.message}). Ensure your local FastAPI server and public tunnel are running and CORS allows https://gdg-cloud.vercel.app.`;
    }
    toast(`Backend connection error: ${err.message}`, "error");
  }
}

init();
