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
let routesData = null;
let map        = null;
let tileLayer  = null;
let layerGroup = null;

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

  // Sincroniza tiles com mudanças de tema
  new MutationObserver(() => {
    updateMapTheme(document.documentElement.getAttribute("data-theme") === "dark");
  }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
}

function makeIcon(label, color) {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="30" height="38" viewBox="0 0 30 38">
      <path d="M15 1C8.37 1 3 6.37 3 13c0 8.5 12 24 12 24S27 21.5 27 13C27 6.37 21.63 1 15 1z"
            fill="${color}" stroke="white" stroke-width="1.5"/>
      <text x="15" y="17" text-anchor="middle" dominant-baseline="middle"
            font-family="DM Mono, monospace" font-size="10" font-weight="600" fill="white">${label}</text>
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
async function renderDay(dia) {
  if (!routesData || !map) return;

  const day = routesData[dia];
  if (!day) return;

  layerGroup.clearLayers();

  const origin  = day.origin;
  const pedidos = day.pedidos;
  const latlngs = [];

  // Marcador de origem
  const oriIcon = makeIcon("⌂", "#6b6660");
  const oriMarker = L.marker([origin.lat, origin.lon], { icon: oriIcon })
    .bindPopup(`<b>Ponto de partida</b><br><small>${origin.endereco}</small>`);
  layerGroup.addLayer(oriMarker);
  latlngs.push([origin.lat, origin.lon]);

  // Marcadores das paradas
  pedidos.forEach((p, i) => {
    if (!p.geocoded) return;

    const icon   = makeIcon(i + 1, getAccentColor());
    const ordensHtml = p.ordens.map(o =>
      `<div style="margin-top:5px;padding-top:5px;border-top:1px solid rgba(128,128,128,0.3)">
        ${o.pedido ? `<small style="color:#999">#${o.pedido}</small> ` : ""}<b>${o.nome}</b><br>
        ${o.recheio ? `<span style="color:#e0622d">${o.recheio}${o.tipo ? " · " + o.tipo : ""}</span><br>` : ""}
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
    latlngs.push([p.lat, p.lon]);

    // Clique no item da lista abre o popup
    const listItem = document.getElementById(`stop-${i}`);
    if (listItem) {
      listItem.addEventListener("click", () => {
        map.setView([p.lat, p.lon], 16);
        marker.openPopup();
      });
    }
  });

  const routeType = day.route_type || "loop";

  // Waypoints para OSRM:
  //   loop → origin;s1;s2;...;origin
  //   star → origin;s1;origin;s2;origin;...
  const geocodedPedidos = pedidos.filter(p => p.geocoded);
  let osrmWaypoints;
  if (routeType === "star") {
    osrmWaypoints = [];
    geocodedPedidos.forEach(p => {
      osrmWaypoints.push([origin.lat, origin.lon]);
      osrmWaypoints.push([p.lat, p.lon]);
    });
    osrmWaypoints.push([origin.lat, origin.lon]);
  } else {
    osrmWaypoints = [...latlngs];
    if (latlngs.length > 1) osrmWaypoints.push([origin.lat, origin.lon]);
  }

  // Ajusta zoom para mostrar todos os pontos (usa apenas coords únicas dos stops)
  if (latlngs.length > 0) {
    map.fitBounds(L.latLngBounds(latlngs), { padding: [32, 32] });
  }

  // Stats (distância provisória enquanto OSRM carrega)
  document.getElementById("stat-stops").textContent   = `${day.total_paradas} paradas · ${day.total_ordens} ovos`;
  document.getElementById("stat-dist").textContent    = `~${day.dist_km_est} km (c/ retorno)`;
  document.getElementById("stat-missing").textContent = day.geocoded_falhou || "0";

  // Rota pelas ruas via OSRM
  if (osrmWaypoints.length > 1) {
    const color = getAccentColor();
    const lineStyle = { color, weight: 3, opacity: 0.85, dashArray: "6, 4" };
    const osrmCoords = osrmWaypoints.map(([lat, lon]) => `${lon},${lat}`).join(";");
    const statusEl = document.getElementById("status-rotas");
    statusEl.textContent = "Calculando rota pelas ruas…";
    try {
      const res = await fetch(
        `https://routing.openstreetmap.de/routed-foot/route/v1/driving/${osrmCoords}?overview=full&geometries=geojson`,
        { cache: "no-store" }
      );
      if (!res.ok) throw new Error(`OSRM HTTP ${res.status}`);
      const data = await res.json();
      if (data.code !== "Ok") throw new Error(`OSRM: ${data.code}`);
      const route = data.routes?.[0];
      if (!route?.geometry) throw new Error("sem geometria");
      L.geoJSON(route.geometry, { style: lineStyle }).addTo(layerGroup);
      const km = (route.distance / 1000).toFixed(1);
      document.getElementById("stat-dist").textContent = `${km} km (c/ retorno)`;
      statusEl.textContent = "";
    } catch (e) {
      statusEl.textContent = `Rota estimada (linha reta) — ${e.message}`;
      L.polyline(latlngs, lineStyle).addTo(layerGroup);
    }
  }

  // Lista lateral
  renderSidebar(origin, pedidos, routeType);
}

const RETURN_ROW = (addr) => `
    <li class="stop-item stop-origin" style="opacity:0.7">
      <div class="stop-num">⌂</div>
      <div class="stop-info">
        <div class="stop-name">Retorno ao ponto de partida</div>
        <div class="stop-addr">${addr}</div>
      </div>
    </li>`;

function renderSidebar(origin, pedidos, routeType = "loop") {
  const ul = document.getElementById("stop-list");
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
    const noCoord  = !p.geocoded;
    const multi    = p.ordens.length > 1;
    const ordensHtml = p.ordens.map(o =>
      `<div class="stop-ordem">
        ${o.pedido ? `<span style="color:var(--text3);font-size:0.72rem;font-family:'DM Mono',monospace">#${o.pedido}</span> ` : ""}<span class="stop-name">${o.nome}</span>
        ${o.recheio ? `<span class="stop-recheio">${o.recheio}${o.tipo ? " · " + o.tipo : ""}</span>` : ""}
      </div>`
    ).join("");

    rows.push(`
      <li class="stop-item${noCoord ? " stop-no-coord" : ""}" id="stop-${i}">
        <div class="stop-num">${noCoord ? "?" : i + 1}${multi ? `<div style="font-size:0.6rem;margin-top:1px">${p.ordens.length}x</div>` : ""}</div>
        <div class="stop-info">
          <div class="stop-addr">${p.endereco}</div>
          ${ordensHtml}
        </div>
      </li>`);

    // No modo star, mostra retorno após cada parada geocodificada
    if (routeType === "star" && !noCoord) {
      rows.push(RETURN_ROW(origin.endereco));
    }
  });

  // No modo loop, mostra retorno apenas no final
  if (routeType !== "star") {
    rows.push(RETURN_ROW(origin.endereco));
  }

  ul.innerHTML = rows.join("");

  // Re-bind cliques após renderizar
  pedidos.forEach((p, i) => {
    if (!p.geocoded) return;
    const item = document.getElementById(`stop-${i}`);
    if (item) item.style.cursor = "pointer";
  });
}

function getAccentColor() {
  return getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "#c84b1e";
}

// ── INIT ──────────────────────────────────────────────────────────────────────
async function init() {
  const statusEl = document.getElementById("status-rotas");
  statusEl.textContent = "Carregando…";

  try {
    const base = document.querySelector('base')?.href ?? window.location.href.replace(/[^/]*$/, '');
    const res  = await fetch(`${base}data/routes.json?t=${Date.now()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    routesData = await res.json();
  } catch (e) {
    statusEl.textContent = `Erro ao carregar rotas: ${e.message}`;
    return;
  }

  statusEl.textContent = "";

  // Popula seletor de dias/turnos
  const sel  = document.getElementById("daySelectRoutes");
  const dias = Object.keys(routesData);
  dias.forEach(chave => {
    const opt = document.createElement("option");
    opt.value = chave;
    // Exibe "Sex - 03/04  ·  Manhã" formatado
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
  const btn = document.getElementById("btnRefresh");
  btn.disabled = true;
  btn.classList.add("is-loading");
  btn.textContent = "Atualizando…";
  routesData = null;
  document.getElementById("daySelectRoutes").innerHTML = "";
  await init();
  btn.disabled = false;
  btn.classList.remove("is-loading");
  btn.textContent = "Atualizar agora";
});

init();
