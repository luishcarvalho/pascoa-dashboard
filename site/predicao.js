// ── TEMA ──────────────────────────────────────────────────────────────────────
(function initTheme() {
  const btn   = document.getElementById("btnTheme");
  const saved = localStorage.getItem("theme") || "dark";
  function applyTheme(t) {
    document.documentElement.setAttribute("data-theme", t);
    btn.textContent = t === "dark" ? "☾" : "☀";
    localStorage.setItem("theme", t);
  }
  applyTheme(saved);
  btn.addEventListener("click", () => {
    applyTheme(document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark");
  });
})();

// ── CONSTANTES ────────────────────────────────────────────────────────────────
const DISPATCH_URL = "https://pascoa-dispatch.luis-h-carvalho.workers.dev/";
const GITHUB_REPO  = "luishcarvalho/pascoa-dashboard";

// ── ESTADO ────────────────────────────────────────────────────────────────────
let predData = null;

// ── CONFIG ────────────────────────────────────────────────────────────────────
// Mapeamento de chave → rótulo de exibição. A maioria é identidade;
// "Nutella (g)" é abreviado para evitar a unidade na UI.
const INGREDIENTE_LABEL = {
  "Leite Condensado": "Leite Condensado",
  "Creme de Leite":   "Creme de Leite",
  "Chocolate em Pó":  "Chocolate em Pó",
  "Leite em Pó":      "Leite em Pó",
  "Pó de Maracujá":   "Pó de Maracujá",
  "Coco Ralado":      "Coco Ralado",
  "Nutella (g)":      "Nutella",
};

const INGREDIENTE_UNIT = {
  "Leite Condensado": "cx",
  "Creme de Leite":   "cx",
  "Chocolate em Pó":  "col",
  "Leite em Pó":      "col",
  "Pó de Maracujá":   "col",
  "Coco Ralado":      "pct",
  "Nutella (g)":      "g",
};

// Cor por ingrediente
const INGREDIENTE_COR = {
  "Leite Condensado": "#2060a8",
  "Creme de Leite":   "#1a7a5e",
  "Chocolate em Pó":  "#6b3a1a",
  "Leite em Pó":      "#b87010",
  "Pó de Maracujá":   "#7a5ea8",
  "Coco Ralado":      "#4a8a4a",
  "Nutella (g)":      "#c84b1e",
};

// Cor por recheio
const RECHEIO_COR = {
  "Brigadeiro":       "#2060a8",
  "Ferrero Rocher":   "#c84b1e",
  "Kids":             "#7a5ea8",
  "Maracujá":         "#b87010",
  "Ninho":            "#4a8a4a",
  "Ninho com Nutella":"#1a7a5e",
  "Prestígio":        "#a09c96",
};

// ── HELPERS ───────────────────────────────────────────────────────────────────
function getBaseUrl() {
  return document.querySelector("base")?.href ?? window.location.href.replace(/[^/]*$/, "");
}

function sleep(ms) {
  return new Promise(res => setTimeout(res, ms));
}

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
        r.status     === "completed" &&
        r.conclusion === "success"
      );
      if (done) return true;
    } catch (_) {}
  }
  return false;
}

function snap(N) {
  return Math.max(0, Math.min(300, Math.round(N / 10) * 10));
}

function getScenario(N) {
  return predData?.scenarios?.[String(snap(N))];
}

function badge(cv) {
  if (cv < 0.03) return '<span class="badge badge-low">baixa</span>';
  if (cv < 0.12) return '<span class="badge badge-med">média</span>';
  return '<span class="badge badge-high">alta</span>';
}

function fmt(v, decimals = 1) {
  return typeof v === "number" ? v.toFixed(decimals) : "—";
}

// ── RENDER: KPI CARDS ─────────────────────────────────────────────────────────
function renderKpis(sc, pct) {
  const lc       = sc["Leite Condensado"]?.[pct];
  const cl       = sc["Creme de Leite"]?.[pct];
  const nutellaG = sc["Nutella (g)"]?.[pct] ?? 0;
  const chocPo   = sc["Chocolate em Pó"]?.[pct];

  document.getElementById("kpi-lc").textContent      = fmt(lc);
  document.getElementById("kpi-cl").textContent      = fmt(cl);
  document.getElementById("kpi-nutella").textContent = nutellaG ? nutellaG.toFixed(0) : "—";
  document.getElementById("kpi-chocpo").textContent  = fmt(chocPo);
}

// ── RENDER: TABELA DE INGREDIENTES ────────────────────────────────────────────
function renderTable(sc, pct) {
  const tbody = document.getElementById("ingr-tbody");

  const rows = Object.keys(INGREDIENTE_LABEL)
    .filter(k => sc[k] && sc[k].mean > 0)
    .map(k => {
      const d    = sc[k];
      const cv   = d.std / d.mean;
      const unit = INGREDIENTE_UNIT[k];
      const cor  = INGREDIENTE_COR[k] || "var(--accent)";

      // Barras: valor atual (sólido) + faixa P50–P95 (transparente)
      const ref        = d.p95 * 1.05;
      const barVal     = Math.min((d[pct] / ref) * 100, 100).toFixed(1);
      const barRangeL  = ((d.p50  / ref) * 100).toFixed(1);
      const barRangeW  = Math.min(((d.p95 - d.p50) / ref) * 100, 100 - barRangeL).toFixed(1);

      return `<tr>
        <td style="font-weight:500">${INGREDIENTE_LABEL[k]}</td>
        <td>
          <div class="ingr-val-main" style="color:${cor}">${fmt(d[pct])} <span class="ingr-unit">${unit}</span></div>
          <div class="ingr-bar-wrap">
            <div class="ingr-bar-range" style="left:${barRangeL}%;width:${barRangeW}%;background:${cor}"></div>
            <div class="ingr-bar-val"   style="width:${barVal}%;background:${cor}"></div>
          </div>
        </td>
        <td class="ingr-faixa">${fmt(d.p50)} – ${fmt(d.p95)}</td>
        <td>${badge(cv)}</td>
      </tr>`;
    });

  tbody.innerHTML = rows.length
    ? rows.join("")
    : `<tr><td colspan="4" class="small">Sem dados.</td></tr>`;
}

// ── RENDER: TENDÊNCIA HISTÓRICA ───────────────────────────────────────────────
function renderHistorico() {
  const hist  = predData?.model?.historico;
  const tbody = document.getElementById("hist-tbody");
  if (!hist) return;

  const years = ["2024", "2025", "2026"];

  // Ordena por valor 2026 decrescente
  const entries = Object.entries(hist).sort(
    ([, a], [, b]) => (b["2026"] ?? 0) - (a["2026"] ?? 0)
  );

  const rows = entries.map(([recheio, byYear]) => {
    const cor  = RECHEIO_COR[recheio] || "var(--accent)";
    const max  = Math.max(...years.map(y => byYear[y] ?? 0), 0.1);

    const cells = years.map(y => {
      const v   = byYear[y] ?? 0;
      const w   = ((v / max) * 72).toFixed(0);
      const val = v > 0 ? `${v.toFixed(1)}%` : "—";
      return `<td>
        <div class="trend-bar">
          ${v > 0 ? `<div class="trend-fill" style="width:${w}px;background:${cor}"></div>` : ""}
          <span>${val}</span>
        </div>
      </td>`;
    });

    // Tendência: compara 2026 vs 2025 (ou 2024 se 2025=0)
    const v24 = byYear["2024"] ?? 0;
    const v25 = byYear["2025"] ?? 0;
    const v26 = byYear["2026"] ?? 0;
    let tendLabel, tendColor;
    if (v24 === 0 && v25 === 0) {
      tendLabel = "✦ Novo";
      tendColor = "var(--accent)";
    } else {
      const prev  = v25 > 0 ? v25 : v24;
      const delta = v26 - prev;
      if (delta > 3) {
        tendLabel = "↑ Crescendo";
        tendColor = "#4ade80";
      } else if (delta < -3) {
        tendLabel = "↓ Caindo";
        tendColor = "#f87171";
      } else {
        tendLabel = "→ Estável";
        tendColor = "var(--text3)";
      }
    }

    return `<tr>
      <td style="font-weight:500">
        <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${cor};margin-right:6px;flex-shrink:0;vertical-align:middle"></span>${recheio}
      </td>
      ${cells.join("")}
      <td style="color:${tendColor};white-space:nowrap;font-size:0.82rem">${tendLabel}</td>
    </tr>`;
  });

  tbody.innerHTML = rows.length
    ? rows.join("")
    : `<tr><td colspan="5" class="small">Sem dados.</td></tr>`;
}

// ── RENDER PRINCIPAL ──────────────────────────────────────────────────────────
function render() {
  if (!predData) return;

  const N   = parseInt(document.getElementById("slider-n").value);
  const pct = document.getElementById("select-pct").value;

  document.getElementById("label-n").textContent = N;

  const sc = getScenario(N);
  if (!sc) return;

  renderKpis(sc, pct);
  renderTable(sc, pct);
}

// ── INIT ──────────────────────────────────────────────────────────────────────
async function init() {
  const statusEl = document.getElementById("status-pred");
  statusEl.textContent = "Carregando…";

  try {
    const res  = await fetch(`${getBaseUrl()}data/prediction.json?t=${Date.now()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    predData = await res.json();
  } catch (e) {
    statusEl.textContent = `Erro ao carregar predição: ${e.message}`;
    return;
  }

  statusEl.textContent = "";
  renderHistorico();
  render();
}

document.getElementById("slider-n").addEventListener("input", render);
document.getElementById("select-pct").addEventListener("change", render);

document.getElementById("btnRefresh")?.addEventListener("click", async () => {
  const statusEl   = document.getElementById("status-pred");
  const btn        = document.getElementById("btnRefresh");
  const previousTs = predData?.last_updated_utc ?? null;

  const setLoading = (label) => { btn.disabled = true; btn.classList.add("is-loading"); btn.textContent = label; };

  try {
    const dispatchedAt = Date.now();
    setLoading("Disparando…");
    statusEl.textContent = "Disparando atualização no servidor…";
    const r = await fetch(DISPATCH_URL, { method: "POST", mode: "cors", cache: "no-store" });
    if (!r.ok) throw new Error(`Dispatch HTTP ${r.status}`);

    setLoading("Aguardando…");
    const done = await waitForDeploy(dispatchedAt, msg => {
      statusEl.textContent = msg;
      setLoading("Aguardando…");
    });
    if (!done) throw new Error("Atualização demorou mais que o esperado. Tente novamente em instantes.");

    statusEl.textContent = "Concluído. Recarregando…";
    await sleep(2000);
    window.location.reload(); return;
  } catch (e) {
    console.error(e);
    statusEl.textContent = `Erro: ${e.message}`;
  } finally {
    btn.disabled = false;
    btn.classList.remove("is-loading");
    btn.textContent = "Atualizar agora";
  }
});

init();
