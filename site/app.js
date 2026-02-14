const statusEl = document.getElementById("status");

function setStatus(msg) {
  statusEl.textContent = msg;
}

function toTable(rows, cols) {
  if (!rows || rows.length === 0) return "<p class='small'>Sem dados.</p>";
  const head = `<tr>${cols.map(c => `<th>${c}</th>`).join("")}</tr>`;
  const body = rows.map(r => `<tr>${cols.map(c => `<td>${(r[c] ?? "")}</td>`).join("")}</tr>`).join("");
  return `<table>${head}${body}</table>`;
}

function toKeyValueTable(obj) {
  const rows = Object.entries(obj || {}).map(([k, v]) => ({ chave: k, valor: v }));
  return toTable(rows, ["chave", "valor"]);
}

async function loadMetrics(bustCache=false) {
  try {
    setStatus("Carregando...");

    // garante que funciona em GitHub Pages /<repo>/
    const base = window.location.pathname.replace(/\/[^\/]*$/, "/"); 
    
    const url = `data/metrics.json${bustCache ? `?t=${Date.now()}` : ""}`;
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    // Resumo
    document.getElementById("summary").innerHTML = `
      <div class="kpi"><div class="label">Total de linhas</div><div class="value">${data.n_rows ?? "-"}</div></div>
      <div class="kpi"><div class="label">Última atualização (UTC)</div><div class="value" style="font-size:14px">${data.last_updated_utc ?? "-"}</div></div>
    `;

    // Contagens
    const counts = data.counts || {};
    document.getElementById("counts").innerHTML = Object.keys(counts).map(k => `
      <h3>${k}</h3>
      ${toKeyValueTable(counts[k])}
    `).join("");

    document.getElementById("cascas").innerHTML =
      toTable(data.cascas_por_combinacao, ["Casca", "Chocolate", "Quantidade de cascas"]);

    document.getElementById("tipoRecheio").innerHTML =
      toTable(data.tipo_recheio, ["Tipo", "Recheio", "quantidade"]);

    document.getElementById("tipoChocolate").innerHTML =
      toTable(data.tipo_chocolate, ["Tipo", "Chocolate", "quantidade"]);

    document.getElementById("gasto").innerHTML =
      toKeyValueTable(data.gasto_por_chocolate_gramas);

    document.getElementById("docinhos").innerHTML =
      toKeyValueTable(data.docinhos_totais);

    document.getElementById("ingredientes").innerHTML =
      toKeyValueTable(data.ingredientes_docinhos_total);

    setStatus("OK ✔");
  } catch (e) {
  console.error(e);
  setStatus(`Erro: ${e.message}`);
  }
}

document.getElementById("btnRefresh").addEventListener("click", () => loadMetrics(true));

// carrega ao abrir
loadMetrics(true);

// auto-refresh a cada 1h (no navegador)
setInterval(() => loadMetrics(true), 60 * 60 * 1000);
