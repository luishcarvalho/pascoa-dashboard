const DISPATCH_URL = "https://pascoa-dispatch.luis-h-carvalho.workers.dev/";
let lastUpdatedIso = null;
let timeAgoIntervalId = null;

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
  // aplica offset fixo -03:00
  return new Date(d.getTime() - 3 * 60 * 60 * 1000);
}

function formatDateBR_UTCminus3(isoString) {
  const br = toBRDateUTCminus3(isoString);
  if (!br) return "-";

  // usar getters UTC porque já “deslocamos” o timestamp
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
  }, 10 * 1000); // atualiza a cada 10s
}

async function loadMetrics(bustCache = false) {
  try {
    setStatus("Carregando...");

    // garante que funciona em GitHub Pages /<repo>/
    const base = window.location.pathname.replace(/\/[^\/]*$/, "/");
    const url = `${base}data/metrics.json${bustCache ? `?t=${Date.now()}` : ""}`;

    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const data = await res.json();
    lastUpdatedIso = data.last_updated_utc || null;

    const last = data.last_updated_utc;

    // Resumo
    document.getElementById("summary").innerHTML = `
      <div class="kpi">
        <div class="label">Total de linhas</div>
        <div class="value">${data.n_rows ?? "-"}</div>
      </div>

      <div class="kpi">
        <div class="label">Última atualização (Brasil - UTC-3)</div>
        <div class="value" style="font-size:14px">${formatDateBR_UTCminus3(last)}</div>
        <div id="timeAgo" class="label" style="margin-top:6px">${timeAgo(last)}</div>
      </div>
    `;

    // inicia/renova o timer do "Atualizado há..."
    startOrRefreshTimeAgoTimer();

    // Contagens
    const counts = data.counts || {};
    document.getElementById("counts").innerHTML = Object.keys(counts)
      .map(
        k => `
      <h3>${k}</h3>
      ${toKeyValueTable(counts[k])}
    `
      )
      .join("");

    document.getElementById("cascas").innerHTML = toTable(
      data.cascas_por_combinacao,
      ["Casca", "Chocolate", "Quantidade de cascas"]
    );

    document.getElementById("tipoRecheio").innerHTML = toTable(data.tipo_recheio, [
      "Tipo",
      "Recheio",
      "quantidade",
    ]);

    document.getElementById("tipoChocolate").innerHTML = toTable(data.tipo_chocolate, [
      "Tipo",
      "Chocolate",
      "quantidade",
    ]);

    document.getElementById("gasto").innerHTML = toKeyValueTable(data.gasto_por_chocolate_gramas);

    document.getElementById("docinhos").innerHTML = toKeyValueTable(data.docinhos_totais);

    document.getElementById("ingredientes").innerHTML = toKeyValueTable(
      data.ingredientes_docinhos_total
    );

    setStatus("OK ✔");
  } catch (e) {
    console.error(e);
    setStatus(`Erro: ${e.message}`);
  }
}

// ✅ Botão agora DISPARA o workflow e espera publicar um metrics.json novo
document.getElementById("btnRefresh").addEventListener("click", async () => {
  const btn = document.getElementById("btnRefresh");
  const previous = lastUpdatedIso;

  try {
    btn.disabled = true;
    setStatus("Disparando atualização…");

    // 1) Dispara workflow via Cloudflare Worker
    const r = await fetch(DISPATCH_URL, { method: "POST" });
    if (!r.ok) throw new Error(await r.text());

    setStatus("Workflow iniciado. Aguardando publicar…");

    // 2) Poll no metrics.json até mudar last_updated_utc (timeout 2 min)
    const start = Date.now();
    while (Date.now() - start < 2 * 60 * 1000) {
      await loadMetrics(true); // força buscar JSON novo
      if (lastUpdatedIso && lastUpdatedIso !== previous) {
        setStatus("Atualizado ✔");
        return;
      }
      await new Promise(res => setTimeout(res, 5000)); // espera 5s
    }

    setStatus("Workflow disparado, mas ainda não publicou. Tente em instantes.");
  } catch (e) {
    console.error(e);
    setStatus(`Erro: ${e.message}`);
  } finally {
    btn.disabled = false;
  }
});

// carrega ao abrir
loadMetrics(true);

// auto-refresh a cada 10 minutos (no navegador)
setInterval(() => loadMetrics(true), 10 * 60 * 1000);
