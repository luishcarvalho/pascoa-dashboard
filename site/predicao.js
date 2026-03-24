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
  "Leite Condensado": "latas",
  "Creme de Leite":   "cx",
  "Chocolate em Pó":  "col",
  "Leite em Pó":      "col",
  "Pó de Maracujá":   "col",
  "Coco Ralado":      "pct",
  "Nutella (g)":      "g",
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

  document.getElementById("kpi-lc").textContent      = fmt(lc);
  document.getElementById("kpi-cl").textContent      = fmt(cl);
  document.getElementById("kpi-nutella").textContent = nutellaPot;
  document.getElementById("kpi-nutella-g").textContent = nutellaG ? `${nutellaG.toFixed(0)} g` : "—";
  document.getElementById("kpi-chocpo").textContent  = fmt(chocPo);
}

// ── RENDER: TABELA DE INGREDIENTES ────────────────────────────────────────────
function renderTable(sc, pct) {
  const tbody = document.getElementById("ingr-tbody");
  const rows  = Object.keys(INGREDIENTE_LABEL)
    .filter(k => sc[k] && sc[k].mean > 0)
    .map(k => {
      const d    = sc[k];
      const cv   = d.std / d.mean;
      const unit = INGREDIENTE_UNIT[k];
      return `<tr>
        <td>${INGREDIENTE_LABEL[k]}</td>
        <td>${fmt(d[pct])} <span class="ingr-unit">${unit}</span></td>
        <td class="ingr-faixa">${fmt(d.p50)} – ${fmt(d.p95)}</td>
        <td>${badge(cv)}</td>
      </tr>`;
    });
  tbody.innerHTML = rows.length ? rows.join("") : `<tr><td colspan="4" class="small">Sem dados.</td></tr>`;
}

// ── RENDER: HISTOGRAMA SVG ────────────────────────────────────────────────────
function renderHistogram(sc) {
  const hist = sc["_histogram_lc"];
  const svg  = document.getElementById("histogram-svg");
  if (!hist || !svg) return;

  const W = 400, H = 120;
  const pad = { top: 6, right: 4, bottom: 22, left: 4 };
  const innerW = W - pad.left - pad.right;
  const innerH = H - pad.top - pad.bottom;

  const maxCount = Math.max(...hist.counts, 1);
  const nBins    = hist.counts.length;
  const barW     = innerW / nBins;

  const bars = hist.counts.map((c, i) => {
    const h = (c / maxCount) * innerH;
    const x = pad.left + i * barW;
    const y = pad.top + innerH - h;
    return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${(barW - 1).toFixed(1)}" height="${h.toFixed(1)}" class="hist-bar"/>`;
  }).join("");

  const bins = hist.bins;
  const labels = [
    `<text x="${pad.left}" y="${H - 4}" class="hist-label" text-anchor="start">${Math.round(bins[0])}</text>`,
    `<text x="${W / 2}" y="${H - 4}" class="hist-label" text-anchor="middle">${Math.round(bins[Math.floor(nBins / 2)])}</text>`,
    `<text x="${W - pad.right}" y="${H - 4}" class="hist-label" text-anchor="end">${Math.round(bins[nBins])}</text>`,
  ].join("");

  svg.innerHTML = bars + labels;
}

// ── RENDER: TENDÊNCIA HISTÓRICA ───────────────────────────────────────────────
function renderHistorico() {
  const hist  = predData?.model?.historico;
  const tbody = document.getElementById("hist-tbody");
  if (!hist) return;

  const years = ["2024", "2025", "2026"];

  const rows = Object.entries(hist).map(([recheio, byYear]) => {
    const vals = years.map(y => byYear[y] ?? 0);
    const max  = Math.max(...vals, 0.1);

    const cells = years.map(y => {
      const v   = byYear[y] ?? 0;
      const pct = ((v / max) * 100).toFixed(0);
      return `<td>
        <div class="trend-bar">
          <div class="trend-fill" style="width:${pct}%"></div>
          <span>${v.toFixed(1)}%</span>
        </div>
      </td>`;
    });

    return `<tr><td>${recheio}</td>${cells.join("")}</tr>`;
  });

  tbody.innerHTML = rows.length ? rows.join("") : `<tr><td colspan="4" class="small">Sem dados.</td></tr>`;
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
  renderHistogram(sc);
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
