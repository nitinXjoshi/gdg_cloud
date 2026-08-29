const API_BASE = typeof window.PROMPTFORGE_API_BASE === "string" ? window.PROMPTFORGE_API_BASE : "";

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
  const res = await api("/api/v1/auth/session", { method: "POST", body: "{}" });
  state.token = res.api_token;
  localStorage.setItem("promptforge_token", res.api_token);
  $("#session-badge").textContent = "SESSION ACTIVE";
  $("#session-badge").className = "badge badge-active";
  toast("Attacker session initialized", "success");
}

async function loadChallenge() {
  const challenges = await api("/api/v1/challenges");
  if (!challenges.length) return;
  const c = challenges[0];
  state.challengeId = c.challenge_id;
  $("#challenge-name").textContent = c.name;
  $("#challenge-difficulty").textContent = `DIFFICULTY: ${c.difficulty.toUpperCase()} · ${c.model.toUpperCase()}`;
  if ($("#challenge-description")) {
    $("#challenge-description").textContent = c.description;
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
  if (!state.token) {
    toast("Initialize an attacker session first", "error");
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
  $("#solved-chip").classList.remove("solved");
  $("#solved-chip").innerHTML = '<span class="dot"></span><span>LOCKED (UNSOLVED)</span>';
  createSession();
});

$("#submit-btn").addEventListener("click", submitPrompt);
$("#prompt-input").addEventListener("input", (e) => {
  $("#char-count").textContent = `${e.target.value.length} chars`;
});
$("#prompt-input").addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") submitPrompt();
});

(async function init() {
  try {
    if (state.token) {
      $("#session-badge").textContent = "SESSION ACTIVE";
      $("#session-badge").className = "badge badge-active";
    }
    await loadChallenge();
    await loadStats();
  } catch (err) {
    toast(`Backend unavailable: ${err.message}`, "error");
  }
})();
