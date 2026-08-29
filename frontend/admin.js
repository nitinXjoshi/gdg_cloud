const API_BASE = window.PROMPTFORGE_API_BASE || "http://localhost:8000";

const $ = (sel) => document.querySelector(sel);
let adminKey = localStorage.getItem("promptforge_admin_key") || "";

function toast(message, type = "") {
  const el = $("#toast");
  el.textContent = message;
  el.className = "toast show " + type;
  setTimeout(() => (el.className = "toast"), 3200);
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (adminKey) headers["X-Admin-Key"] = adminKey;
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

function fmtIntOrNA(value) {
  return value === null || value === undefined ? "Not available" : value.toLocaleString();
}

function setPill(id, value) {
  const el = $(id);
  el.textContent = value;
  el.className = "metric-value status-pill status-" + value;
}

function authenticate() {
  adminKey = $("#admin-key").value.trim();
  if (!adminKey) return toast("Enter the admin API key", "error");
  localStorage.setItem("promptforge_admin_key", adminKey);
  loadAll().then(() => toast("Authenticated", "success"));
}

async function loadSystemStatus() {
  const s = await api("/api/v1/admin/system-status");
  setPill("#st-app", s.application);
  setPill("#st-db", s.database);
  setPill("#st-redis", s.redis);
  setPill("#st-ollama", s.ollama);
  setPill("#st-model", s.model || "unavailable");
  $("#st-provider").textContent = s.provider;
}

async function loadMetrics() {
  const m = await api("/api/v1/admin/metrics");
  $("#m-challenge").textContent = m.active_challenge || "—";
  $("#m-participants").textContent = m.total_participants;
  $("#m-attempts").textContent = m.total_attempts;
  $("#m-solved").textContent = m.successful_injections;
  $("#m-rate").textContent = `${(m.attack_success_rate * 100).toFixed(1)}%`;
  $("#m-avg").textContent = `${m.average_latency_ms}ms`;
  $("#m-p95").textContent = `${m.p95_latency_ms}ms`;
  $("#m-error").textContent = `${(m.error_rate * 100).toFixed(2)}%`;

  if (m.usage_available) {
    $("#m-tokens").textContent = fmtIntOrNA(
      (m.total_input_tokens || 0) + (m.total_output_tokens || 0)
    );
  } else {
    $("#m-tokens").textContent = "Not available";
  }
  $("#m-runtime").textContent = m.runtime || "Local";
  $("#m-cost").textContent = m.api_cost === "0" ? "₹0 / $0" : m.api_cost;
}

async function loadAll() {
  await Promise.all([loadSystemStatus(), loadMetrics()]);
}

async function runEvaluation() {
  const btn = $("#eval-btn");
  btn.disabled = true;
  btn.textContent = "Running attack suite…";
  $("#eval-status").textContent = "Executing injection attacks against the real Ollama model…";

  try {
    const result = await api("/api/v1/admin/security/evaluate", { method: "POST" });
    renderEvaluation(result);
    $("#eval-status").textContent =
      `${result.successful_attacks}/${result.total_attacks} attacks succeeded ` +
      `(${(result.overall_success_rate * 100).toFixed(1)}% overall) · ` +
      `${result.evaluation_kind}`;
  } catch (err) {
    toast(err.message, "error");
    $("#eval-status").textContent = "";
  } finally {
    btn.disabled = false;
    btn.textContent = "Run security evaluation";
  }
}

function renderEvaluation(result) {
  const body = $("#eval-body");
  body.innerHTML = "";
  for (const cat of result.by_category) {
    const tr = document.createElement("tr");
    const rate = cat.success_rate;
    const rateClass = rate >= 0.5 ? "rate-high" : rate > 0 ? "rate-low" : "";
    tr.innerHTML = `
      <td>${cat.category}</td>
      <td>${cat.attempts}</td>
      <td>${cat.successful}</td>
      <td class="${rateClass}">${(rate * 100).toFixed(1)}%</td>
    `;
    body.appendChild(tr);
  }
}

$("#auth-btn").addEventListener("click", authenticate);
$("#eval-btn").addEventListener("click", runEvaluation);
$("#admin-key").addEventListener("keydown", (e) => {
  if (e.key === "Enter") authenticate();
});

if (adminKey) {
  $("#admin-key").value = adminKey;
  loadAll().catch(() => toast("Invalid or expired admin key", "error"));
}
