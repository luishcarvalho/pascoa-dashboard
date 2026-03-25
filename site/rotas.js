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

// ── ESTADO ────────────────────────────────────────────────────────────────────
let routesData    = null;
let lastUpdatedTs = null;
let map           = null;
let tileLayer     = null;
let layerGroup    = null;

// Paleta de cores distintas para os pins
const PIN_COLORS = [
  "#e05c5c", "#e07d1e", "#c9a800", "#4caf50", "#2196f3",
  "#9c27b0", "#00bcd4", "#e91e8c", "#795548", "#607d8b",
  "#ff5722", "#009688", "#3f51b5", "#f06292", "#8bc34a",
];

function pinColor(index) {
  return PIN_COLORS[index % PIN_COLORS.length];
}

// ── MAPA ──────────────────────────────────────────────────────────────────────
function tileUrl(dark) {
  return dark
    ? "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
    : "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png";
}

function updateMapTheme(dark) {
  if (!map) return;
  if (tileLayer) map.removeLayer(tileLayer);
  tileLayer = L.tileLayer(tileUrl(dark), {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
    maxZoom: 19,
  }).addTo(map);
}

function initMap() {
  map = L.map("map");
  const isDark = document.documentElement.getAttribute("data-theme") === "dark";
  updateMapTheme(isDark);
  layerGroup = L.layerGroup().addTo(map);

  new MutationObserver(() => {
    updateMapTheme(document.documentElement.getAttribute("data-theme") === "dark");
  }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
}

function makeIcon(label, color) {
  const isOrigin = label === "⌂";
  const isMulti  = !isOrigin && label !== "";
  const fontSize = isMulti && label.length > 2 ? "8" : "10";
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="30" height="38" viewBox="0 0 30 38">
      <path d="M15 1C8.37 1 3 6.37 3 13c0 8.5 12 24 12 24S27 21.5 27 13C27 6.37 21.63 1 15 1z"
            fill="${color}" stroke="white" stroke-width="1.5"/>
      ${label ? `<text x="15" y="17" text-anchor="middle" dominant-baseline="middle" font-family="DM Mono, monospace" font-size="${fontSize}" font-weight="600" fill="white">${label}</text>` : ""}
    </svg>`;
  return L.divIcon({
    html: svg,
    className: "",
    iconSize:   [30, 38],
    iconAnchor: [15, 38],
    popupAnchor:[0, -38],
  });
}

// ── RENDER ────────────────────────────────────────────────────────────────────
function renderDay(dia) {
  if (!routesData || !map) return;

  const day = routesData[dia];
  if (!day) return;

  layerGroup.clearLayers();

  const origin  = day.origin;
  const pedidos = day.pedidos;
  const latlngs = [[origin.lat, origin.lon]];

  // Marcador de origem
  const oriIcon = makeIcon("⌂", "#6b6660");
  L.marker([origin.lat, origin.lon], { icon: oriIcon })
    .bindPopup(`<b>Ponto de partida</b><br><small>${origin.endereco}</small>`)
    .addTo(layerGroup);

  // Marcadores das paradas — uma cor por parada
  pedidos.forEach((p, i) => {
    if (!p.geocoded) return;

    latlngs.push([p.lat, p.lon]);
    const color  = pinColor(i);
    const pinLabel = p.ordens.length > 1 ? `${p.ordens.length}x` : "";
    const icon   = makeIcon(pinLabel, color);
    const ordensHtml = p.ordens.map(o =>
      `<div style="margin-top:5px;padding-top:5px;border-top:1px solid rgba(128,128,128,0.3)">
        ${o.pedido ? `<small style="color:#999">#${o.pedido}</small> ` : ""}<b>${o.nome}</b><br>
        ${o.recheio ? `<span style="color:#e0622d">${o.recheio}${o.tipo ? " · " + o.tipo : ""}</span><br>` : ""}
        ${o.faltante_num > 0 ? `<small style="color:#4caf50;font-weight:600">💰 ${o.faltante}</small><br>` : ""}
        ${o.obs && o.obs !== "nan" ? `<small style="color:#999">${o.obs}</small>` : ""}
      </div>`
    ).join("");

    const marker = L.marker([p.lat, p.lon], { icon })
      .bindPopup(`
        <div style="min-width:180px">
          <small style="color:#999">${p.endereco}</small>
          ${ordensHtml}
        </div>
      `);
    layerGroup.addLayer(marker);

    // Clique no item da lista abre o popup
    const listItem = document.getElementById(`stop-${i}`);
    if (listItem) {
      listItem.addEventListener("click", () => {
        map.setView([p.lat, p.lon], 16);
        marker.openPopup();
      });
    }
  });

  // Ajusta zoom
  if (latlngs.length > 1) {
    map.fitBounds(L.latLngBounds(latlngs), { padding: [32, 32] });
  } else {
    map.setView([origin.lat, origin.lon], 14);
  }

  // Stats
  document.getElementById("stat-stops").textContent    = `${day.total_paradas} paradas · ${day.total_ordens} ovos`;
  document.getElementById("stat-missing").textContent  = day.geocoded_falhou || "0";
  document.getElementById("stat-faltante").textContent = fmtBRL(day.faltante_total || 0);

  // Lista lateral
  renderSidebar(origin, pedidos);
}

function renderSidebar(origin, pedidos) {
  const ul   = document.getElementById("stop-list");
  const rows = [];

  // Origem
  rows.push(`
    <li class="stop-item stop-origin">
      <div class="stop-num">⌂</div>
      <div class="stop-info">
        <div class="stop-name">Ponto de partida</div>
        <div class="stop-addr">${origin.endereco}</div>
      </div>
    </li>`);

  pedidos.forEach((p, i) => {
    const noCoord = !p.geocoded;
    const multi   = p.ordens.length > 1;
    const color   = pinColor(i);
    const faltantePar = p.faltante_parada || 0;

    const ordensHtml = p.ordens.map(o => {
      const val = o.faltante_num ?? 0;
      return `<div class="stop-ordem">
        ${o.pedido ? `<span style="color:var(--text3);font-size:0.72rem;font-family:'DM Mono',monospace">#${o.pedido}</span> ` : ""}<span class="stop-name">${o.nome}</span>
        <div class="stop-recheio-row">
          ${o.recheio ? `<span class="stop-recheio">${o.recheio}${o.tipo ? " · " + o.tipo : ""}</span>` : "<span></span>"}
          <span class="stop-faltante">${val > 0 ? o.faltante : "Pago"}</span>
        </div>
      </div>`;
    }).join("");

    const faltanteTotal = `<div class="stop-faltante-total"><span>Total a Receber</span><span>${fmtBRL(faltantePar)}</span></div>`;
    const numStyle = noCoord ? "" : `style="background:${color}"`;

    rows.push(`
      <li class="stop-item${noCoord ? " stop-no-coord" : ""}" id="stop-${i}">
        <div class="stop-num" ${numStyle}>${noCoord ? "?" : ""}${multi ? `<div style="font-size:0.6rem;margin-top:1px">${p.ordens.length}x</div>` : ""}</div>
        <div class="stop-info">
          <div class="stop-addr">${p.endereco}</div>
          ${ordensHtml}
          ${faltanteTotal}
        </div>
      </li>`);
  });

  ul.innerHTML = rows.join("");

  // Re-bind cliques após renderizar
  pedidos.forEach((p, i) => {
    if (!p.geocoded) return;
    const item = document.getElementById(`stop-${i}`);
    if (item) item.style.cursor = "pointer";
  });
}

function fmtBRL(val) {
  return Number(val).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

// ── INIT ──────────────────────────────────────────────────────────────────────
async function init() {
  const statusEl = document.getElementById("status-rotas");
  statusEl.textContent = "Carregando…";

  try {
    const base = document.querySelector('base')?.href ?? window.location.href.replace(/[^/]*$/, '');
    const res  = await fetch(`${base}data/routes.json?t=${Date.now()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const payload  = await res.json();
    lastUpdatedTs  = payload.last_updated_utc ?? null;
    routesData     = payload.routes ?? payload; // compatibilidade com formato antigo
  } catch (e) {
    statusEl.textContent = `Erro ao carregar rotas: ${e.message}`;
    return;
  }

  statusEl.textContent = "";

  const sel  = document.getElementById("daySelectRoutes");
  const dias = Object.keys(routesData);
  dias.forEach(chave => {
    const opt = document.createElement("option");
    opt.value = chave;
    const parts = chave.split(" · ");
    opt.textContent = parts.length > 1 ? `${parts[0]}  ·  ${parts[1]}` : chave;
    sel.appendChild(opt);
  });

  initMap();

  sel.addEventListener("change", () => renderDay(sel.value));

  if (dias.length > 0) {
    sel.value = dias[0];
    renderDay(dias[0]);
  }
}

document.getElementById("btnRefresh")?.addEventListener("click", async () => {
  const btn      = document.getElementById("btnRefresh");
  const statusEl = document.getElementById("status-rotas");
  const previousTs = lastUpdatedTs;

  const setLoading = (label) => { btn.disabled = true; btn.classList.add("is-loading"); btn.textContent = label; };

  try {
    setLoading("Disparando…");
    statusEl.textContent = "Disparando atualização no servidor…";
    const r = await fetch(`${DISPATCH_URL}?t=${Date.now()}`, { method: "POST", mode: "cors", cache: "no-store" });
    if (!r.ok) throw new Error(`Dispatch HTTP ${r.status}`);

    setLoading("Aguardando…");
    statusEl.textContent = "Workflow iniciado. Aguardando processamento…";
    await new Promise(res => setTimeout(res, 15000));

    const base  = document.querySelector("base")?.href ?? window.location.href.replace(/[^/]*$/, "");
    const start = Date.now();
    while (Date.now() - start < 3 * 60 * 1000) {
      setLoading("Atualizando…");
      statusEl.textContent = "Buscando dados publicados…";
      try {
        const res = await fetch(`${base}data/routes.json?t=${Date.now()}`, { cache: "no-store" });
        if (res.ok) {
          const data = await res.json();
          if (data.last_updated_utc && data.last_updated_utc !== previousTs) { window.location.reload(); return; }
        }
      } catch (_) {}
      await new Promise(res => setTimeout(res, 8000));
    }
    throw new Error("Atualização demorou mais que o esperado. Tente novamente em instantes.");
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
