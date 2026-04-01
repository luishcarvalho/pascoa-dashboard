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
const DAY_ORDER    = ["qua", "qui", "sex", "sab", "dom", "seg"];
const TURNO_ORDER  = ["Manhã", "Tarde", "Noite"];
const CIDADE_ORDER = ["Dores", "Divinópolis"];

// ── ESTADO ────────────────────────────────────────────────────────────────────
let pedidosPayload    = null;
let lastUpdatedIso    = null;
let timeAgoIntervalId = null;
let isLocked          = true;

const statusEl  = document.getElementById("status-pedidos");
const contentEl = document.getElementById("pedidos-content");
const daySelect = document.getElementById("daySelectPedidos");

// ── HELPERS ───────────────────────────────────────────────────────────────────
function getBaseUrl() {
  return document.querySelector("base")?.href ?? window.location.href.replace(/[^/]*$/, "");
}

function setStatus(msg) {
  statusEl.textContent = msg;
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

function timeAgo(iso) {
  if (!iso) return "—";
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60)    return `Atualizado há ${diff}s`;
  if (diff < 3600)  return `Atualizado há ${Math.floor(diff / 60)}min`;
  if (diff < 86400) return `Atualizado há ${Math.floor(diff / 3600)}h`;
  return `Atualizado há ${Math.floor(diff / 86400)}d`;
}

function startTimeAgo() {
  if (timeAgoIntervalId) clearInterval(timeAgoIntervalId);
  const el = document.getElementById("lastUpdated");
  if (!el) return;
  function tick() { el.textContent = timeAgo(lastUpdatedIso); }
  tick();
  timeAgoIntervalId = setInterval(tick, 30_000);
}

function sortIdx(arr, val) {
  const i = arr.indexOf(val);
  return i >= 0 ? i : 99;
}

// ── RENDERIZAÇÃO ──────────────────────────────────────────────────────────────

const PRIV = "•••";

function masked(val) {
  return isLocked ? `<span class="priv">${PRIV}</span>` : (val || `<span style="color:var(--text3)">—</span>`);
}

function plain(val) {
  return val || `<span style="color:var(--text3)">—</span>`;
}

function faltanteCell(val) {
  if (isLocked) return `<span class="priv">${PRIV}</span>`;
  if (!val || val === "R$ 0,00" || val === "R$ 0.00") {
    return `<span class="faltante-zero">R$ 0,00</span>`;
  }
  return `<span class="faltante-pos">${val}</span>`;
}

function entregaBadge(tipo) {
  if (tipo === "Retirada") return `<span class="badge-retirada">Retirada</span>`;
  return `<span class="badge-entrega">Entrega</span>`;
}

function infantilBadge(val) {
  if (!val || val.toLowerCase() === "não" || val.toLowerCase() === "nao") return "";
  return `<span class="badge-infantil">Infantil</span>`;
}

// Observação colapsável: textos com mais de 10 chars são colapsados
const OBS_LIMIT = 10;
function obsCell(val) {
  if (isLocked) return `<span class="priv">${PRIV}</span>`;
  if (!val) return `<span style="color:var(--text3)">—</span>`;
  if (val.length <= OBS_LIMIT) return `<span class="obs-text">${val}</span>`;
  const preview = val.slice(0, OBS_LIMIT).trimEnd();
  return `<details class="obs-details">
    <summary class="obs-summary">${preview}…</summary>
    <span class="obs-full">${val}</span>
  </details>`;
}

function buildTable(pedidos) {
  if (!pedidos || pedidos.length === 0) return "";

  // Alternância de grupo por nome para colorir linhas do mesmo cliente
  const groups = [];
  let lastNome = null;
  let groupIdx = 0;
  for (const p of pedidos) {
    const nome = p.nome || "__anon__";
    if (nome !== lastNome) { groupIdx++; lastNome = nome; }
    groups.push(groupIdx % 2 === 0);
  }

  const head = `<tr>
    <th>#</th>
    <th>Nome</th>
    <th>Tipo</th>
    <th>Recheio</th>
    <th>Chocolate</th>
    <th>Docinho</th>
    <th>Infantil</th>
    <th>Endereço</th>
    <th>Valor</th>
    <th>Observação</th>
    <th>Recebido</th>
    <th>Faltante</th>
  </tr>`;

  const rows = pedidos.map((p, i) => {
    const alt = groups[i] ? " group-alt" : "";
    const inf = infantilBadge(p.infantil);
    return `<tr class="${alt}">
      <td><span class="pedido-num">${p.pedido || "—"}</span></td>
      <td>${masked(p.nome)}</td>
      <td>${plain(p.tipo)}</td>
      <td>${plain(p.recheio)}</td>
      <td>${plain(p.chocolate)}</td>
      <td>${plain(p.docinho)}</td>
      <td>${inf || `<span style="color:var(--text3)">—</span>`}</td>
      <td>${masked(p.endereco)}</td>
      <td>${masked(p.valor)}</td>
      <td class="obs-cell">${obsCell(p.obs)}</td>
      <td>${masked(p.recebido)}</td>
      <td>${faltanteCell(p.faltante)}</td>
    </tr>`;
  }).join("");

  return `<div class="pedidos-wrap custom-scroll">
    <table class="pedidos-table">
      <thead>${head}</thead>
      <tbody>${rows}</tbody>
    </table>
  </div>`;
}

function renderDay(dia) {
  if (!pedidosPayload?.days) {
    contentEl.innerHTML = '<p class="empty-day">Sem dados.</p>';
    return;
  }

  const dayData = pedidosPayload.days[dia];
  if (!dayData) {
    contentEl.innerHTML = '<p class="empty-day">Nenhum pedido para este dia.</p>';
    return;
  }

  const { cidades, total } = dayData;

  // Totais por tipo
  let totalEntregas = 0, totalRetiradas = 0, totalFaltante = 0;
  for (const turnos of Object.values(cidades)) {
    for (const tipoMap of Object.values(turnos)) {
      for (const [tipo, pedidos] of Object.entries(tipoMap)) {
        for (const p of pedidos) {
          if (tipo === "Retirada") totalRetiradas++;
          else totalEntregas++;
          const v = parseFloat(
            String(p.faltante || "0").replace("R$", "").replace(/\./g, "").replace(",", ".").trim()
          );
          if (!isNaN(v)) totalFaltante += v;
        }
      }
    }
  }

  const faltanteStr = totalFaltante.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

  // Stats ficam no status-bar (inline com o select)
  const statsEl = document.getElementById("pedidos-day-stats");
  if (statsEl) {
    statsEl.innerHTML =
      `<div class="day-stat">Total <strong>${total}</strong></div>` +
      `<div class="day-stat">Entregas <strong>${totalEntregas}</strong></div>` +
      `<div class="day-stat">Retiradas <strong>${totalRetiradas}</strong></div>` +
      (!isLocked ? `<div class="day-stat">A receber <strong>${faltanteStr}</strong></div>` : "");
  }

  let html = ``;

  // Ordena cidades
  const cidades_sorted = Object.keys(cidades).sort(
    (a, b) => sortIdx(CIDADE_ORDER, a) - sortIdx(CIDADE_ORDER, b)
  );

  for (const cidade of cidades_sorted) {
    const turnos = cidades[cidade];

    // Ordena turnos
    const turnos_sorted = Object.keys(turnos).sort(
      (a, b) => sortIdx(TURNO_ORDER, a) - sortIdx(TURNO_ORDER, b)
    );

    let turnosHtml = "";
    for (const turno of turnos_sorted) {
      const tipoMap = turnos[turno];

      let tiposHtml = "";
      // Entrega primeiro, depois Retirada
      for (const tipo of ["Entrega", "Retirada"]) {
        const pedidos = tipoMap[tipo];
        if (!pedidos || pedidos.length === 0) continue;
        const badgeTxt = pedidos.length === 1 ? "1 pedido" : `${pedidos.length} pedidos`;
        tiposHtml += `<div class="tipo-section">
          <div class="tipo-label">
            ${tipo === "Retirada"
              ? `<span class="badge-retirada">${tipo}</span>`
              : `<span class="badge-entrega">${tipo}</span>`}
            <span class="tipo-badge">${badgeTxt}</span>
          </div>
          ${buildTable(pedidos)}
        </div>`;
      }

      turnosHtml += `<div class="turno-section">
        <div class="turno-label">${turno}</div>
        ${tiposHtml}
      </div>`;
    }

    html += `<div class="cidade-section">
      <div class="cidade-label">
        ${cidade}
        <span class="cidade-badge">${Object.values(turnos).reduce((s, t) =>
          s + Object.values(t).reduce((a, b) => a + b.length, 0), 0)} pedidos</span>
      </div>
      ${turnosHtml}
    </div>`;
  }

  contentEl.innerHTML = html;
}

// ── CARREGAMENTO ──────────────────────────────────────────────────────────────

async function loadPedidos(silent = false) {
  if (!silent) setStatus("Carregando…");
  try {
    const url = `${getBaseUrl()}data/pedidos.json`;
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const payload = await res.json();

    pedidosPayload = payload;
    lastUpdatedIso = payload.last_updated_utc ?? null;
    startTimeAgo();

    const days = payload.available_days ?? [];
    daySelect.innerHTML = days.map(d => `<option value="${d}">${d}</option>`).join("");

    if (days.length > 0) renderDay(days[0]);
    else contentEl.innerHTML = '<p class="empty-day">Nenhum pedido encontrado.</p>';

    if (!silent) setStatus("");
  } catch (err) {
    setStatus(`Erro ao carregar dados: ${err.message}`);
  }
}

// ── EVENTOS ───────────────────────────────────────────────────────────────────

daySelect.addEventListener("change", () => renderDay(daySelect.value));

window.addEventListener("authchange", ({ detail }) => {
  isLocked = !detail.authenticated;
  if (pedidosPayload && daySelect.value) renderDay(daySelect.value);
});

document.getElementById("btnRefresh").addEventListener("click", async () => {
  setStatus("Disparando atualização…");
  try {
    const dispatchedAt = Date.now();
    const res = await fetch(DISPATCH_URL, { method: "POST" });
    if (!res.ok) throw new Error(`Dispatch falhou: ${res.status}`);
    setStatus("Workflow iniciado, aguardando…");
    const ok = await waitForDeploy(dispatchedAt, setStatus);
    if (ok) {
      setStatus("Concluído! Recarregando…");
      await sleep(1500);
      location.reload();
    } else {
      setStatus("Timeout — recarregue manualmente.");
    }
  } catch (err) {
    setStatus(`Erro: ${err.message}`);
  }
});

// ── INIT ──────────────────────────────────────────────────────────────────────
isLocked = !window.isAuth?.();
loadPedidos();
setInterval(() => loadPedidos(true), 10 * 60 * 1000);
