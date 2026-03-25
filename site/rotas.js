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
const AUTH_HASH    = "HASH_PLACEHOLDER"; // injetado pelo CI (GitHub Secret AUTH_HASH)
const ALL_DAYS     = "__all__";

// ── HELPERS ───────────────────────────────────────────────────────────────────
function getBaseUrl() {
  return document.querySelector("base")?.href ?? window.location.href.replace(/[^/]*$/, "");
}

function fmtBRL(val) {
  return Number(val).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function updateStats(stops, missing, faltante) {
  document.getElementById("stat-stops").textContent    = stops;
  document.getElementById("stat-missing").textContent  = String(missing);
  document.getElementById("stat-faltante").textContent = fmtBRL(faltante);
}

function popupOrdemHtml(o) {
  return `<div style="margin-top:5px;padding-top:5px;border-top:1px solid rgba(128,128,128,0.3)">
    ${o.pedido ? `<small style="color:#999">#${o.pedido}</small> ` : ""}<b>${o.nome ?? "•••"}</b><br>
    ${o.recheio ? `<span style="color:#e0622d">${o.recheio}${o.tipo ? " · " + o.tipo : ""}</span><br>` : ""}
    ${o.faltante_num > 0
      ? `<small style="color:#4caf50;font-weight:600">💰 ${o.faltante}</small><br>`
      : `<small style="color:#4caf50;font-weight:600">Pago</small><br>`}
    ${o.obs && o.obs !== "nan" ? `<small style="color:#999">${o.obs}</small>` : ""}
  </div>`;
}

// ── AUTENTICAÇÃO ──────────────────────────────────────────────────────────────
let isAuthenticated = false;

async function sha256(str) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(str));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, "0")).join("");
}

function setAuthUI(authenticated) {
  const bar   = document.getElementById("auth-bar");
  const icon  = document.getElementById("auth-icon");
  const label = document.getElementById("auth-label");
  const input = document.getElementById("auth-input");
  const btn   = document.getElementById("auth-btn");
  const msg   = document.getElementById("auth-msg");

  if (authenticated) {
    bar.classList.add("unlocked");
    icon.textContent  = "🔓";
    label.textContent = "Dados completos visíveis";
    const btnWidth = btn.offsetWidth;
    input.style.display = "none";
    btn.style.display   = "none";
    msg.textContent     = "";
    let logoutBtn = document.getElementById("auth-logout");
    if (!logoutBtn) {
      logoutBtn = document.createElement("button");
      logoutBtn.id          = "auth-logout";
      logoutBtn.textContent = "Ocultar";
      logoutBtn.style.width = `${btnWidth}px`;
      logoutBtn.addEventListener("click", async () => {
        sessionStorage.removeItem("rotas_auth");
        isAuthenticated = false;
        setAuthUI(false);
        try {
          const res = await fetch(`${getBaseUrl()}data/routes.json`, { cache: "no-store" });
          if (res.ok) {
            const payload = await res.json();
            routesData = payload.routes ?? payload;
            const sel = document.getElementById("daySelectRoutes");
            if (sel.value === ALL_DAYS) renderAll();
            else renderDay(sel.value);
          }
        } catch (e) { console.error(e); }
      });
      bar.appendChild(logoutBtn);
    }
    logoutBtn.style.display = "";
  } else {
    bar.classList.remove("unlocked");
    icon.textContent  = "🔒";
    label.textContent = "Dados sensíveis ocultos";
    input.style.display = "";
    btn.style.display   = "";
    const logoutBtn = document.getElementById("auth-logout");
    if (logoutBtn) logoutBtn.style.display = "none";
  }
}

document.getElementById("auth-btn").addEventListener("click", async () => {
  const input = document.getElementById("auth-input");
  const msg   = document.getElementById("auth-msg");
  const hash  = await sha256(input.value);

  if (hash !== AUTH_HASH) {
    msg.textContent = "Senha incorreta";
    input.value = "";
    return;
  }

  sessionStorage.setItem("rotas_auth", hash);
  isAuthenticated = true;
  setAuthUI(true);
  msg.textContent = "";

  try {
    const res = await fetch(`${getBaseUrl()}data/routes_full.json`, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const payload = await res.json();
    routesData = payload.routes ?? payload;
    const sel = document.getElementById("daySelectRoutes");
    if (sel.value === ALL_DAYS) renderAll();
    else renderDay(sel.value);
  } catch (e) {
    console.error("Erro ao carregar dados completos:", e);
  }
});

document.getElementById("auth-input").addEventListener("keydown", e => {
  if (e.key === "Enter") document.getElementById("auth-btn").click();
});

// ── ESTADO ────────────────────────────────────────────────────────────────────
let routesData    = null;
let lastUpdatedTs = null;
let map           = null;
let tileLayer     = null;
let layerGroup    = null;

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
function stopCardHtml(p, i, color, idPrefix = "stop") {
  const noCoord  = !p.geocoded;
  const multi    = p.ordens.length > 1;
  const numStyle = noCoord ? "" : `style="background:${color}"`;
  const priv     = '<span style="color:var(--text3);font-style:italic">•••</span>';

  const ordensHtml = p.ordens.map(o => {
    const val = o.faltante_num ?? 0;
    return `<div class="stop-ordem">
      ${o.pedido ? `<span style="color:var(--text3);font-size:0.72rem;font-family:'DM Mono',monospace">#${o.pedido}</span> ` : ""}
      <span class="stop-name">${o.nome ?? priv}</span>
      <div class="stop-recheio-row">
        ${o.recheio ? `<span class="stop-recheio">${o.recheio}${o.tipo ? " · " + o.tipo : ""}</span>` : "<span></span>"}
        <span class="stop-faltante">${val > 0 ? o.faltante : "Pago"}</span>
      </div>
    </div>`;
  }).join("");

  return `
    <li class="stop-item${noCoord ? " stop-no-coord" : ""}" id="${idPrefix}-${i}">
      <div class="stop-num" ${numStyle}>${noCoord ? "?" : ""}${multi ? `<div style="font-size:0.6rem;margin-top:1px">${p.ordens.length}x</div>` : ""}</div>
      <div class="stop-info">
        <div class="stop-addr">${p.endereco ?? priv}</div>
        ${ordensHtml}
        <div class="stop-faltante-total"><span>Total a Receber</span><span>${fmtBRL(p.faltante_parada ?? 0)}</span></div>
      </div>
    </li>`;
}

function renderGrid(pedidos) {
  document.getElementById("stop-list").innerHTML =
    pedidos.map((p, i) => stopCardHtml(p, i, pinColor(i))).join("");
}

function renderDay(dia) {
  if (!routesData || !map) return;
  const day = routesData[dia];
  if (!day) return;

  layerGroup.clearLayers();
  renderGrid(day.pedidos);

  const origin  = day.origin;
  const latlngs = [[origin.lat, origin.lon]];

  L.marker([origin.lat, origin.lon], { icon: makeIcon("⌂", "#6b6660") })
    .bindPopup(`<b>Ponto de partida</b><br><small>${origin.endereco}</small>`)
    .addTo(layerGroup);

  day.pedidos.forEach((p, i) => {
    if (!p.geocoded) return;
    latlngs.push([p.lat, p.lon]);
    const color  = pinColor(i);
    const marker = L.marker([p.lat, p.lon], { icon: makeIcon(p.ordens.length > 1 ? `${p.ordens.length}x` : "", color) })
      .bindPopup(`<div style="min-width:180px"><small style="color:#999">${p.endereco}</small>${p.ordens.map(popupOrdemHtml).join("")}</div>`);
    layerGroup.addLayer(marker);

    const listItem = document.getElementById(`stop-${i}`);
    if (listItem) listItem.addEventListener("click", () => { map.setView([p.lat, p.lon], 16); marker.openPopup(); });
  });

  if (latlngs.length > 1) map.fitBounds(L.latLngBounds(latlngs), { padding: [32, 32] });
  else map.setView([origin.lat, origin.lon], 14);

  updateStats(
    `${day.total_paradas} paradas · ${day.total_ordens} ovos`,
    day.geocoded_falhou ?? 0,
    day.faltante_total  ?? 0,
  );
}

function renderAll() {
  if (!routesData || !map) return;
  layerGroup.clearLayers();

  const latlngs      = [];
  const clickTargets = [];
  let totalParadas = 0, totalOrdens = 0, totalMissing = 0, totalFaltante = 0;
  let colorIdx = 0;
  const rows = [];

  Object.entries(routesData).forEach(([chave, day]) => {
    totalParadas  += day.total_paradas;
    totalOrdens   += day.total_ordens;
    totalMissing  += day.geocoded_falhou ?? 0;
    totalFaltante += day.faltante_total  ?? 0;

    const parts = chave.split(" · ");
    rows.push(`<li class="stop-item stop-day-label">${parts.length > 1 ? `${parts[0]} · ${parts[1]}` : chave}</li>`);

    day.pedidos.forEach(p => {
      if (!p.geocoded) return;
      latlngs.push([p.lat, p.lon]);
      const color = pinColor(colorIdx);
      L.marker([p.lat, p.lon], { icon: makeIcon(p.ordens.length > 1 ? `${p.ordens.length}x` : "", color) })
        .bindPopup(`<div style="min-width:180px"><small style="color:#999">${p.endereco}</small>${p.ordens.map(popupOrdemHtml).join("")}</div>`)
        .addTo(layerGroup);

      rows.push(stopCardHtml(p, colorIdx, color, "stop-all"));
      clickTargets.push({ id: `stop-all-${colorIdx}`, lat: p.lat, lon: p.lon });
      colorIdx++;
    });
  });

  document.getElementById("stop-list").innerHTML = rows.join("");

  clickTargets.forEach(({ id, lat, lon }) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("click", () => map.setView([lat, lon], 16));
  });

  if (latlngs.length > 0) map.fitBounds(L.latLngBounds(latlngs), { padding: [32, 32] });

  updateStats(
    `${totalParadas} paradas · ${totalOrdens} ovos`,
    totalMissing,
    totalFaltante,
  );
}

// ── INIT ──────────────────────────────────────────────────────────────────────
async function init() {
  const statusEl = document.getElementById("status-rotas");
  statusEl.textContent = "Carregando…";

  try {
    const res     = await fetch(`${getBaseUrl()}data/routes.json`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const payload  = await res.json();
    lastUpdatedTs  = payload.last_updated_utc ?? null;
    routesData     = payload.routes ?? payload;
  } catch (e) {
    statusEl.textContent = `Erro ao carregar rotas: ${e.message}`;
    return;
  }

  statusEl.textContent = "";
  setAuthUI(false);

  const sel  = document.getElementById("daySelectRoutes");
  const dias = Object.keys(routesData);
  dias.forEach(chave => {
    const opt   = document.createElement("option");
    opt.value   = chave;
    const parts = chave.split(" · ");
    opt.textContent = parts.length > 1 ? `${parts[0]}  ·  ${parts[1]}` : chave;
    sel.appendChild(opt);
  });

  const optAll = document.createElement("option");
  optAll.value = ALL_DAYS;
  optAll.textContent = "Geral (todos os dias)";
  sel.appendChild(optAll);

  initMap();

  sel.addEventListener("change", () => {
    if (sel.value === ALL_DAYS) renderAll();
    else renderDay(sel.value);
  });

  if (dias.length > 0) {
    sel.value = dias[0];
    renderDay(dias[0]);
  }
}

document.getElementById("btnRefresh")?.addEventListener("click", async () => {
  const btn        = document.getElementById("btnRefresh");
  const statusEl   = document.getElementById("status-rotas");
  const previousTs = lastUpdatedTs;

  const setLoading = (label) => { btn.disabled = true; btn.classList.add("is-loading"); btn.textContent = label; };

  try {
    setLoading("Disparando…");
    statusEl.textContent = "Disparando atualização no servidor…";
    const r = await fetch(DISPATCH_URL, { method: "POST", mode: "cors", cache: "no-store" });
    if (!r.ok) throw new Error(`Dispatch HTTP ${r.status}`);

    setLoading("Aguardando…");
    statusEl.textContent = "Workflow iniciado. Aguardando processamento…";
    await new Promise(res => setTimeout(res, 15000));

    const base  = getBaseUrl();
    const start = Date.now();
    while (Date.now() - start < 3 * 60 * 1000) {
      setLoading("Atualizando…");
      statusEl.textContent = "Buscando dados publicados…";
      try {
        const res = await fetch(`${base}data/routes.json`, { cache: "no-store" });
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
