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

  // Deployed host: same-origin API requests
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

const $ = (sel) => document.querySelector(sel);
let adminKey = localStorage.getItem("promptforge_admin_key") || "";

function toast(message, type = "") {
  const el = $("#toast");
  if (!el) return;
  el.textContent = message;
  el.className = "toast show " + type;
  setTimeout(() => (el.className = "toast"), 3200);
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (adminKey) headers["X-Admin-Key"] = adminKey;
  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  } catch (_) {
    throw new Error("Backend unavailable. Please try again.");
  }
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      detail = (await res.json()).detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

function fmtIntOrNA(value) {
  return value === null || value === undefined ? "Not available" : value.toLocaleString();
}

function setPill(id, value) {
  const el = $(id);
  if (!el) return;
  el.textContent = value;
  el.className = "metric-value status-pill status-" + value;
}

function authenticate() {
  adminKey = $("#admin-key").value.trim();
  if (!adminKey) return toast("Enter the admin API key", "error");
  localStorage.setItem("promptforge_admin_key", adminKey);
  loadAll()
    .then(() => toast("Authenticated", "success"))
    .catch((err) => toast(`Admin connection failed: ${err.message}`, "error"));
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
  $("#m-attempts").textContent = fmtIntOrNA(m.total_attempts);
  $("#m-injections").textContent = fmtIntOrNA(m.successful_injections);
  $("#m-asr").textContent = `${(m.attack_success_rate * 100).toFixed(1)}%`;
  $("#m-rpm").textContent = m.requests_per_minute.toFixed(1);
  $("#m-avg-latency").textContent = m.average_latency_ms ? `${m.average_latency_ms.toFixed(0)} ms` : "—";
  $("#m-p95-latency").textContent = m.p95_latency_ms ? `${m.p95_latency_ms.toFixed(0)} ms` : "—";
  if (m.usage_available) {
    $("#m-input-tokens").textContent = fmtIntOrNA(m.total_input_tokens);
    $("#m-output-tokens").textContent = fmtIntOrNA(m.total_output_tokens);
  } else {
    $("#m-input-tokens").textContent = "Not available";
    $("#m-output-tokens").textContent = "Not available";
  }
  $("#m-cost").textContent = `₹${m.api_cost} ($0)`;
}

async function loadAll() {
  await Promise.all([loadSystemStatus(), loadMetrics()]);
}

async function runEvaluation() {
  const btn = $("#eval-btn");
  const summary = $("#eval-summary");
  const tbody = $("#eval-tbody");
  btn.disabled = true;
  btn.textContent = "Running Evaluation against REAL Ollama…";
  summary.textContent = "Evaluating 15 attack vectors against live llama3.2:3b…";
  tbody.innerHTML = "";

  try {
    const res = await api("/api/v1/admin/security/evaluate", { method: "POST" });
    const categories = Object.values(res.categories || {});
    let rows = "";
    for (const c of categories) {
      const rate = c.attempts > 0 ? ((c.successful / c.attempts) * 100).toFixed(0) : 0;
      const statusClass = c.successful > 0 ? "status-breached" : "status-defended";
      const statusLabel = c.successful > 0 ? "FLAG LEAKED" : "DEFENDED";
      rows += `
        <tr>
          <td><strong>${c.category}</strong></td>
          <td>${c.attempts}</td>
          <td>${c.successful}</td>
          <td>${rate}%</td>
          <td><span class="status-pill ${statusClass}">${statusLabel}</span></td>
        </tr>
      `;
    }
    tbody.innerHTML = rows;
    summary.textContent = `Completed in ${res.duration_seconds}s. Total Attacks: ${res.total_attacks} | Flag Disclosures: ${res.successful_attacks} | Robustness: ${(
      (1 - res.attack_success_rate) *
      100
    ).toFixed(1)}%`;
    toast("Security evaluation complete", "success");
    await loadMetrics();
  } catch (err) {
    summary.textContent = `Evaluation failed: ${err.message}`;
    toast(err.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Run 15-Category Adversarial Evaluation";
  }
}

updateApiEndpointUI();

$("#auth-btn").addEventListener("click", authenticate);
$("#eval-btn").addEventListener("click", runEvaluation);
$("#admin-key").addEventListener("keydown", (e) => {
  if (e.key === "Enter") authenticate();
});

if (adminKey) {
  $("#admin-key").value = adminKey;
  loadAll().catch(() => toast("Invalid or expired admin key", "error"));
}
