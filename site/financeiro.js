// ── ESTADO (antes do initTheme para evitar temporal dead zone) ────────────────
let finPayload      = null;
let lastUpdatedIso  = null;
let chartGastos     = null;
let chartPagamentos = null;
let chartMetodo     = null;
let chartLoja       = null;
let isLocked        = !window.isAuth?.();

// ── TEMA ──────────────────────────────────────────────────────────────────────
(function initTheme() {
  const btn   = document.getElementById("btnTheme");
  const saved = localStorage.getItem("theme") || "dark";
  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    btn.textContent = theme === "dark" ? "☾" : "☀";
    localStorage.setItem("theme", theme);
    rebuildCharts();
  }
  applyTheme(saved);
  btn.addEventListener("click", () => {
    applyTheme(document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark");
  });
})();

// ── CONSTANTES ────────────────────────────────────────────────────────────────
const DISPATCH_URL = "https://pascoa-dispatch.luis-h-carvalho.workers.dev/";
const GITHUB_REPO  = "luishcarvalho/pascoa-dashboard";

const PALETTE_GASTOS  = ["#e85d04", "#3a86ff", "#8338ec", "#06d6a0", "#ffbe0b", "#ef4444"];
const PALETTE_PAGT    = ["#4ade80", "#f87171"];
const PALETTE_METODO  = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4"];
const PALETTE_LOJA    = ["#f97316", "#6366f1", "#14b8a6", "#ec4899", "#84cc16", "#facc15"];

const statusEl = document.getElementById("status-fin");

// ── HELPERS ───────────────────────────────────────────────────────────────────
function getCSSVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
function setStatus(msg) { statusEl.textContent = msg; }
function sleep(ms)      { return new Promise(res => setTimeout(res, ms)); }
function pad2(n)        { return String(n).padStart(2, "0"); }

function toBRDate(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  return new Date(d.getTime() - 3 * 60 * 60 * 1000);
}
function formatDateBR(iso) {
  const br = toBRDate(iso);
  if (!br) return "—";
  return `${pad2(br.getUTCDate())}/${pad2(br.getUTCMonth() + 1)}/${br.getUTCFullYear()} · ${pad2(br.getUTCHours())}:${pad2(br.getUTCMinutes())}`;
}
function formatBRL(v) {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(v || 0);
}
function formatPct(v) {
  return `${(v || 0).toFixed(1).replace(".", ",")}%`;
}
function getBaseUrl() {
  return document.querySelector("base")?.href ?? window.location.href.replace(/[^/]*$/, "");
}

// ── UPDATE FLOW ───────────────────────────────────────────────────────────────
async function waitForDeploy(dispatchedAt, onStatus, timeoutMs = 5 * 60 * 1000) {
  const url   = `https://api.github.com/repos/${GITHUB_REPO}/actions/runs?per_page=10`;
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    await sleep(10000);
    onStatus("Aguardando conclusão do workflow…");
    try {
      const res = await fetch(url, { headers: { Accept: "application/vnd.github+json" } });
      if (!res.ok) continue;
      const { workflow_runs } = await res.json();
      const done = workflow_runs?.find(r =>
        new Date(r.created_at).getTime() >= dispatchedAt - 30_000 &&
        r.status === "completed" && r.conclusion === "success"
      );
      if (done) return true;
    } catch (_) {}
  }
  return false;
}

function setButtonLoading(isLoading, label) {
  const btn = document.getElementById("btnRefresh");
  if (!btn) return;
  if (!btn.dataset.originalText) btn.dataset.originalText = btn.textContent;
  btn.disabled    = isLoading;
  btn.classList.toggle("is-loading", isLoading);
  btn.textContent = label || (isLoading ? "Atualizando…" : btn.dataset.originalText);
  btn.setAttribute("aria-busy", isLoading ? "true" : "false");
}

document.getElementById("btnRefresh").addEventListener("click", async () => {
  try {
    const dispatchedAt = Date.now();
    setStatus("Disparando atualização no servidor…");
    setButtonLoading(true, "Disparando…");
    const r = await fetch(DISPATCH_URL, { method: "POST", mode: "cors", cache: "no-store" });
    if (!r.ok) throw new Error((await r.text()) || `HTTP ${r.status}`);
    setButtonLoading(true, "Aguardando…");
    const done = await waitForDeploy(dispatchedAt, msg => { setStatus(msg); setButtonLoading(true, "Aguardando…"); });
    if (!done) throw new Error("Atualização demorou mais que o esperado.");
    setStatus("Concluído. Recarregando…");
    await sleep(2000);
    window.location.reload();
  } catch (e) {
    console.error(e);
    setStatus(`Erro: ${e.message}`);
    setButtonLoading(false);
  }
});

// ── KPI RENDER ────────────────────────────────────────────────────────────────
function kpiCard(label, value, sub, colorClass) {
  const extra = colorClass ? ` ${colorClass}` : "";
  return `
    <div class="kpi">
      <div class="label">${label}</div>
      <div class="value${extra}" style="font-size:22px">${value}</div>
      ${sub ? `<div class="kpi-unit">${sub}</div>` : ""}
    </div>`;
}

const HIDDEN = "•••";
const mask   = v => isLocked ? HIDDEN : v;

function renderKPIs(d) {
  // ── Receita ────────────────────────────────────────────────────────────────
  document.getElementById("kpi-receita").innerHTML =
    kpiCard("Receita bruta", mask(formatBRL(d.receita_bruta))) +
    kpiCard("Recebido", mask(formatBRL(d.recebido)), null, "kpi-value-green") +
    kpiCard("A receber", mask(formatBRL(d.faltante)), null, "kpi-value-red") +
    (d.n_pedidos
      ? kpiCard("Pedidos", d.n_pedidos, d.ticket_medio ? `Ticket médio ${mask(formatBRL(d.ticket_medio))}` : "")
      : "");

  // ── Saldo de caixa (investimento real) ─────────────────────────────────────
  const roi      = d.gastos_total > 0 ? (d.lucro_bruto || 0) / d.gastos_total * 100 : 0;
  const margem   = d.margem_lucro_pct || 0;
  const cxPos    = (d.lucro_bruto || 0) >= 0;

  document.getElementById("kpi-saldo").innerHTML =
    kpiCard("Investimento total", mask(formatBRL(d.gastos_total)), "Tudo que foi comprado (inclui estoque)") +
    kpiCard("Saldo disponível", mask(formatBRL(d.lucro_bruto)), "Receita − Investimento total", cxPos ? "kpi-value-green" : "kpi-value-red") +
    kpiCard("Margem de lucro", mask(formatPct(margem)), null, cxPos ? "kpi-value-green" : "kpi-value-red") +
    kpiCard("Retorno s/ investimento", mask(formatPct(roi)), "Lucro ÷ Investimento total", cxPos ? "kpi-value-green" : "kpi-value-red");
}

// ── TABLE DIAS ────────────────────────────────────────────────────────────────
function renderTabelaDias(receita_por_dia) {
  const el      = document.getElementById("tabelaDias");
  const entries = Object.entries(receita_por_dia || {});
  if (!entries.length) { el.innerHTML = "<p class='small'>Sem dados por dia.</p>"; return; }
  const total = entries.reduce((s, [, v]) => s + v, 0);
  const rows  = entries.map(([dia, val]) => {
    const pct = total > 0 ? ((val / total) * 100).toFixed(1) : "0.0";
    return `<tr><td>${dia}</td><td>${mask(formatBRL(val))}</td><td><span class="small">${pct}%</span></td></tr>`;
  }).join("");
  el.innerHTML = `
    <table>
      <tr><th>Dia de entrega</th><th>Receita</th><th>%</th></tr>
      ${rows}
      <tr><td><strong>Total</strong></td><td><strong>${mask(formatBRL(total))}</strong></td><td></td></tr>
    </table>`;
}

// ── CHARTS ────────────────────────────────────────────────────────────────────
function destroyCharts() {
  if (chartGastos)     { chartGastos.destroy();     chartGastos     = null; }
  if (chartPagamentos) { chartPagamentos.destroy();  chartPagamentos = null; }
  if (chartMetodo)     { chartMetodo.destroy();      chartMetodo     = null; }
  if (chartLoja)       { chartLoja.destroy();        chartLoja       = null; }
}

function buildDonutOptions(maskMoney = false) {
  const textColor = getCSSVar("--text2");
  return {
    cutout: "65%",
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: "right",
        align: "center",
        labels: { color: textColor, font: { family: "'DM Mono', monospace", size: 11 }, padding: 12, boxWidth: 12, boxHeight: 12 },
      },
      tooltip: {
        callbacks: {
          label(ctx) {
            const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
            const pct   = total > 0 ? ((ctx.raw / total) * 100).toFixed(1) : "0.0";
            const val   = (maskMoney && isLocked) ? HIDDEN : formatBRL(ctx.raw);
            return ` ${val} (${pct}%)`;
          },
        },
      },
    },
  };
}

function rebuildCharts() {
  if (!finPayload) return;
  destroyCharts();
  const borderCol  = getCSSVar("--surface");
  const optsLocked = buildDonutOptions(true);
  const optsOpen   = buildDonutOptions(false);

  const gastosPorCat = finPayload.gastos_por_categoria || {};
  const gastosLabels = Object.keys(gastosPorCat);
  const gastosValues = Object.values(gastosPorCat);
  if (gastosLabels.length > 0) {
    chartGastos = new Chart(document.getElementById("chartGastos"), {
      type: "doughnut",
      data: { labels: gastosLabels, datasets: [{ data: gastosValues, backgroundColor: PALETTE_GASTOS.slice(0, gastosLabels.length), borderColor: borderCol, borderWidth: 2, hoverOffset: 10 }] },
      options: optsLocked,
    });
  }

  const recebido = finPayload.recebido || 0;
  const faltante = finPayload.faltante || 0;
  if (recebido > 0 || faltante > 0) {
    chartPagamentos = new Chart(document.getElementById("chartPagamentos"), {
      type: "doughnut",
      data: { labels: ["Recebido", "A Receber"], datasets: [{ data: [recebido, faltante], backgroundColor: PALETTE_PAGT, borderColor: borderCol, borderWidth: 2, hoverOffset: 10 }] },
      options: optsLocked,
    });
  }

  const porMetodo  = finPayload.gastos_por_metodo || {};
  const metLabels  = Object.keys(porMetodo);
  const metValues  = Object.values(porMetodo);
  if (metLabels.length > 0) {
    chartMetodo = new Chart(document.getElementById("chartMetodo"), {
      type: "doughnut",
      data: { labels: metLabels, datasets: [{ data: metValues, backgroundColor: PALETTE_METODO.slice(0, metLabels.length), borderColor: borderCol, borderWidth: 2, hoverOffset: 10 }] },
      options: optsLocked,
    });
  }

  const porLoja    = finPayload.gastos_por_loja || {};
  const lojaLabels = Object.keys(porLoja);
  const lojaValues = Object.values(porLoja);
  if (lojaLabels.length > 0) {
    chartLoja = new Chart(document.getElementById("chartLoja"), {
      type: "doughnut",
      data: { labels: lojaLabels, datasets: [{ data: lojaValues, backgroundColor: PALETTE_LOJA.slice(0, lojaLabels.length), borderColor: borderCol, borderWidth: 2, hoverOffset: 10 }] },
      options: optsLocked,
    });
  }
}

// ── RENDER ────────────────────────────────────────────────────────────────────
function renderView(data) {
  finPayload = data;
  renderKPIs(data);
  renderTabelaDias(data.receita_por_dia || {});
  rebuildCharts();
}

// ── INIT ──────────────────────────────────────────────────────────────────────
async function loadFinanceiro() {
  try {
    setStatus("Carregando...");
    const res = await fetch(`${getBaseUrl()}data/financeiro.json?t=${Date.now()}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data     = await res.json();
    lastUpdatedIso = data.last_updated_utc ?? null;
    const el = document.getElementById("lastUpdated");
    if (el) el.textContent = `Atualizado: ${formatDateBR(lastUpdatedIso)}`;
    renderView(data);
    setStatus("Atualizado ✔");
  } catch (e) {
    console.error(e);
    setStatus(`Erro: ${e.message}`);
  }
}

// Set initial locked state (window.isAuth is defined in auth.js, loaded first)
document.querySelector(".page").classList.toggle("locked", isLocked);

window.addEventListener("authchange", ({ detail: { authenticated } }) => {
  isLocked = !authenticated;
  document.querySelector(".page").classList.toggle("locked", isLocked);
  if (finPayload) renderView(finPayload);
});

loadFinanceiro();
setInterval(loadFinanceiro, 10 * 60 * 1000);
