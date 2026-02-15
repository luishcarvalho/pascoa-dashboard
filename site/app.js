const DISPATCH_URL = "https://pascoa-dispatch.luis-h-carvalho.workers.dev/";
let lastUpdatedIso = null;
let timeAgoIntervalId = null;

// ✅ novo: guarda o JSON inteiro (overall + per_day)
let metricsPayload = null;

const statusEl = document.getElementById("status");

function setStatus(msg) {
  statusEl.textContent = msg;
}

function toTable(rows, cols) {
  if (!rows || rows.length === 0) return "<p class='small'>Sem dados.</p>";
  const head = `<tr>${cols.map(c => `<th>${c}</th>`).join("")}</tr>`;
  const body = rows
    .map(r => `<tr>${cols.map(c => `<td>${(r[c] ?? "")}</td>`).join("")}</tr>`)
    .join("");
  return `<table>${head}${body}</table>`;
}

function toKeyValueTable(obj) {
  const rows = Object.entries(obj || {}).map(([k, v]) => ({ chave: k, valor: v }));
  return toTable(rows, ["chave", "valor"]);
}

/**
 * Helpers: data/hora Brasil (UTC-3 fixo) + "Atualizado há X ..."
 * (não depende do fuso do computador do usuário)
 */
function pad2(n) {
  return String(n).padStart(2, "0");
}

function toBRDateUTCminus3(isoString) {
  if (!isoString) return null;
  const d = new Date(isoString);
  return new Date(d.getTime() - 3 * 60 * 60 * 1000);
}

function formatDateBR_UTCminus3(isoString) {
  const br = toBRDateUTCminus3(isoString);
  if (!br) return "-";

  const dia = pad2(br.getUTCDate());
  const mes = pad2(br.getUTCMonth() + 1);
  const ano = br.getUTCFullYear();

  const hora = pad2(br.getUTCHours());
  const minuto = pad2(br.getUTCMinutes());
  const segundo = pad2(br.getUTCSeconds());

  return `${dia}/${mes}/${ano} - ${hora}:${minuto}:${segundo}`;
}

function timeAgo(isoString) {
  if (!isoString) return "-";
  const d = new Date(isoString);

  const diffMs = Date.now() - d.getTime();
  if (diffMs < 0) return "Atualizado agora";

  const sec = Math.floor(diffMs / 1000);
  if (sec < 60) return `Atualizado há ${sec} segundo${sec === 1 ? "" : "s"}`;

  const min = Math.floor(sec / 60);
  if (min < 60) return `Atualizado há ${min} minuto${min === 1 ? "" : "s"}`;

  const hr = Math.floor(min / 60);
  if (hr < 24) return `Atualizado há ${hr} hora${hr === 1 ? "" : "s"}`;

  const dia = Math.floor(hr / 24);
  return `Atualizado há ${dia} dia${dia === 1 ? "" : "s"}`;
}

function startOrRefreshTimeAgoTimer() {
  if (timeAgoIntervalId) clearInterval(timeAgoIntervalId);
  timeAgoIntervalId = setInterval(() => {
    const el = document.getElementById("timeAgo");
    if (el && lastUpdatedIso) el.textContent = timeAgo(lastUpdatedIso);
  }, 10 * 1000);
}

/* ------------------------------------------------------------------ */
/* Dropdown: Geral vs Dia                                              */
/* ------------------------------------------------------------------ */
function populateDaySelect() {
  const el = document.getElementById("daySelect");
  if (!el || !metricsPayload) return;

  const days =
    metricsPayload.available_days ||
    Object.keys(metricsPayload.per_day || {}).sort((a, b) => String(a).localeCompare(String(b), "pt-BR"));

  const current = el.value || "overall";
  el.innerHTML = `
    <option value="overall">Geral (todos os dias)</option>
    ${days.map(d => `<option value="${d}">Dia ${d}</option>`).join("")}
  `;

  el.value = days.includes(current) ? current : "overall";
}

function getSelectedMetrics() {
  if (!metricsPayload) return null;
  const el = document.getElementById("daySelect");
  const sel = (el && el.value) ? el.value : "overall";

  if (sel === "overall") return metricsPayload.overall || null;

  const byDay = metricsPayload.per_day || {};
  return byDay[sel] || metricsPayload.overall || null;
}

function renderView(m) {
  if (!m) return;

  const last = lastUpdatedIso;

  // Resumo
  document.getElementById("summary").innerHTML = `
    <div class="kpi">
      <div class="label">Total de linhas</div>
      <div class="value">${m.n_rows ?? "-"}</div>
    </div>

    <div class="kpi">
      <div class="label">Última atualização (Brasil - UTC-3)</div>
      <div class="value" style="font-size:14px">${formatDateBR_UTCminus3(last)}</div>
      <div id="timeAgo" class="label" style="margin-top:6px">${timeAgo(last)}</div>
    </div>
  `;

  startOrRefreshTimeAgoTimer();

  // Contagens
  const counts = m.counts || {};
  document.getElementById("counts").innerHTML = Object.keys(counts)
    .map(
      k => `
      <h3>${k}</h3>
      ${toKeyValueTable(counts[k])}
    `
    )
    .join("");

  document.getElementById("cascas").innerHTML = toTable(
    m.cascas_por_combinacao,
    ["Casca", "Chocolate", "Quantidade de cascas"]
  );

  document.getElementById("tipoRecheio").innerHTML = toTable(m.tipo_recheio, [
    "Tipo",
    "Recheio",
    "quantidade",
  ]);

  document.getElementById("tipoChocolate").innerHTML = toTable(m.tipo_chocolate, [
    "Tipo",
    "Chocolate",
    "quantidade",
  ]);

  document.getElementById("gasto").innerHTML = toKeyValueTable(m.gasto_por_chocolate_gramas);

  document.getElementById("docinhos").innerHTML = toKeyValueTable(m.docinhos_totais);

  document.getElementById("ingredientes").innerHTML = toKeyValueTable(m.ingredientes_docinhos_total);
}
/* ------------------------------------------------------------------ */

/* ------------------------------------------------------------------ */
/* Botão elegante: loading + bloqueio + mensagens                      */
/* ------------------------------------------------------------------ */
function setButtonLoading(isLoading, label) {
  const btn = document.getElementById("btnRefresh");
  if (!btn) return;

  if (!btn.dataset.originalText) btn.dataset.originalText = btn.textContent;

  btn.disabled = isLoading;
  btn.classList.toggle("is-loading", isLoading);
  btn.textContent = label || (isLoading ? "Atualizando…" : btn.dataset.originalText);
  btn.setAttribute("aria-busy", isLoading ? "true" : "false");
}

function sleep(ms) {
  return new Promise(res => setTimeout(res, ms));
}

async function runUpdateFlow() {
  const previous = lastUpdatedIso;

  setStatus("Disparando atualização no servidor…");
  setButtonLoading(true, "Disparando…");

  const r = await fetch(`${DISPATCH_URL}?t=${Date.now()}`, {
    method: "POST",
    mode: "cors",
    cache: "no-store",
  });

  const txt = await r.text();
  if (!r.ok) throw new Error(txt || `HTTP ${r.status}`);

  setStatus("Workflow iniciado. Aguardando processamento…");
  setButtonLoading(true, "Aguardando…");
  await sleep(15000);

  const start = Date.now();
  const timeoutMs = 3 * 60 * 1000; // 3 min
  const intervalMs = 8000; // 8s

  while (Date.now() - start < timeoutMs) {
    setStatus("Buscando novas métricas publicadas…");
    setButtonLoading(true, "Atualizando…");

    await loadMetrics(true);

    if (lastUpdatedIso && lastUpdatedIso !== previous) {
      setStatus("Atualizado ✔");
      return;
    }

    await sleep(intervalMs);
  }

  throw new Error("Atualização demorou mais que o esperado. Tente novamente em instantes.");
}
/* ------------------------------------------------------------------ */

async function loadMetrics(bustCache = false) {
  try {
    setStatus("Carregando...");

    const base = window.location.pathname.replace(/\/[^\/]*$/, "/");
    const url = `${base}data/metrics.json${bustCache ? `?t=${Date.now()}` : ""}`;

    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const data = await res.json();

    // ✅ novo formato esperado:
    // { last_updated_utc, overall, per_day, available_days }
    metricsPayload = data;
    lastUpdatedIso = data.last_updated_utc || null;

    // atualiza dropdown e renderiza conforme seleção
    populateDaySelect();
    const selected = getSelectedMetrics();
    renderView(selected);

    setStatus("OK ✔");
  } catch (e) {
    console.error(e);
    setStatus(`Erro: ${e.message}`);
  }
}

// ✅ dropdown troca a visão sem recarregar dados
document.getElementById("daySelect")?.addEventListener("change", () => {
  const selected = getSelectedMetrics();
  renderView(selected);
});

// ✅ Botão elegante: dispara workflow + bloqueia + mostra status
document.getElementById("btnRefresh").addEventListener("click", async () => {
  try {
    await runUpdateFlow();
  } catch (e) {
    console.error(e);
    setStatus(`Erro: ${e.message}`);
  } finally {
    setButtonLoading(false);
  }
});

// carrega ao abrir
loadMetrics(true);

// auto-refresh a cada 10 minutos (no navegador)
setInterval(() => loadMetrics(true), 10 * 60 * 1000);
