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

// ── ESTADO ────────────────────────────────────────────────────────────────────
let predData = null;

// ── CONSTANTES ────────────────────────────────────────────────────────────────
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
function snap(N) {
  return Math.max(85, Math.min(300, Math.round(N / 5) * 5));
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
  const lc         = sc["Leite Condensado"]?.[pct];
  const cl         = sc["Creme de Leite"]?.[pct];
  const nutellaG   = sc["Nutella (g)"]?.[pct] ?? 0;
  const nutellaPot = nutellaG ? (nutellaG / 650).toFixed(1) : "—";
  const chocPo     = sc["Chocolate em Pó"]?.[pct];

  document.getElementById("kpi-lc").textContent        = fmt(lc);
  document.getElementById("kpi-cl").textContent        = fmt(cl);
  document.getElementById("kpi-nutella").textContent   = nutellaPot;
  document.getElementById("kpi-nutella-g").textContent = nutellaG ? `${nutellaG.toFixed(0)} g` : "—";
  document.getElementById("kpi-chocpo").textContent    = fmt(chocPo);
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
    // Largura relativa ao máximo global desse recheio
    const max  = Math.max(...years.map(y => byYear[y] ?? 0), 0.1);

    const cells = years.map(y => {
      const v   = byYear[y] ?? 0;
      const w   = ((v / max) * 72).toFixed(0);   // px, max 72px
      const val = v > 0 ? `${v.toFixed(1)}%` : "—";
      return `<td>
        <div class="trend-bar">
          ${v > 0 ? `<div class="trend-fill" style="width:${w}px;background:${cor}"></div>` : ""}
          <span>${val}</span>
        </div>
      </td>`;
    });

    return `<tr>
      <td style="font-weight:500">
        <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${cor};margin-right:6px;flex-shrink:0;vertical-align:middle"></span>${recheio}
      </td>
      ${cells.join("")}
    </tr>`;
  });

  tbody.innerHTML = rows.length
    ? rows.join("")
    : `<tr><td colspan="4" class="small">Sem dados.</td></tr>`;
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
    const base = window.location.pathname.replace(/\/[^/]*$/, "/");
    const res  = await fetch(`${base}data/prediction.json?t=${Date.now()}`);
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

init();
