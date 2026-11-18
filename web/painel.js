/* MenteAcessível SP — painel analítico */
"use strict";

// Escala ordinal de um só tom (azul): mais escuro = mais cobertura
const CLASSES = [
  { nome: "Insuficiente/crítica", cor: "#86b6ef", faixa: "abaixo de 0,20" },
  { nome: "Baixa", cor: "#5598e7", faixa: "0,20 a 0,34" },
  { nome: "Regular/baixa", cor: "#2a78d6", faixa: "0,35 a 0,49" },
  { nome: "Boa", cor: "#1c5cab", faixa: "0,50 a 0,70" },
  { nome: "Muito boa", cor: "#104281", faixa: "acima de 0,70" },
];
const SEM_DADOS = "#f0efec";
const SERIE = "#2a78d6";
const TINTA = { primaria: "#1d1d1b", secundaria: "#52514e", grade: "#e8e6e0" };

const $ = (s) => document.querySelector(s);
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n, casas = 0) => (n == null ? "–" : Number(n).toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas }));
const corDaClasse = (nome) => (CLASSES.find((c) => c.nome === nome) || {}).cor || SEM_DADOS;

Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
Chart.defaults.color = TINTA.secundaria;
Chart.defaults.plugins.legend.display = false;

let dadosMunicipios = [];
let ordem = { col: "indice", asc: true };

async function api(caminho) {
  const r = await fetch(caminho);
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.erro || `Erro ${r.status}`);
  return d;
}

async function iniciar() {
  try {
    const [cob, malha, demanda] = await Promise.all([api("/api/cobertura"), api("/api/malha"), api("/api/demanda")]);
    preencherKpis(cob);
    desenharMapa(cob.municipios, malha);
    desenharRegioes(cob.regioes);
    desenharDispersao(cob.municipios);
    prepararTabela(cob.municipios);
    desenharDemanda(demanda);
    const m = cob.metadados || {};
    $("#fontes").innerHTML = `Fontes: ${esc(m.fonte_cnes)} (dados de ${esc(m.competencia_cnes)}, coletados em ${esc(m.data_coleta)}); ` +
      `${esc(m.fonte_populacao)}; ${esc(m.fonte_malha)}. Modalidade dos CAPS identificada pelo nome cadastrado.`;
  } catch (erro) {
    $("#subtitulo").innerHTML = `<span class="aviso">Não foi possível carregar o painel: ${esc(erro.message)}</span>`;
  }
}

function preencherKpis(cob) {
  const e = cob.estado;
  const total = cob.municipios.length;
  $("#subtitulo").textContent = `${fmt(total)} municípios · ${fmt(e.populacao)} habitantes · ${fmt(e.caps_total)} CAPS`;
  $("#kpi-indice").textContent = fmt(e.indice, 2);
  $("#kpi-classe").textContent = `por 100 mil hab. · cobertura ${e.classificacao.toLowerCase()}`;
  $("#kpi-caps").textContent = fmt(e.caps_total);
  const m = e.caps_por_modalidade || {};
  const h24 = (m.CAPS_III || 0) + (m.CAPS_AD_III || 0) + (m.CAPS_AD_IV || 0);
  $("#kpi-caps-nota").textContent = `${fmt(h24)} ${h24 === 1 ? "funciona" : "funcionam"} 24h`;
  $("#kpi-sem").textContent = fmt(e.municipios_sem_caps);
  $("#kpi-sem-nota").textContent = `${fmt(100 * e.municipios_sem_caps / total, 0)}% dos municípios`;
  $("#kpi-deficit").textContent = fmt(e.municipios_com_deficit);
}

function desenharMapa(municipios, malha) {
  const porCodigo = Object.fromEntries(municipios.map((m) => [m.codigo_ibge, m]));
  const mapa = L.map("mapa-cobertura", { scrollWheelZoom: false });
  const camada = L.geoJSON(malha, {
    style: (f) => ({
      fillColor: corDaClasse((porCodigo[f.properties.codigo_ibge] || {}).classificacao),
      fillOpacity: 1, color: "#ffffff", weight: 0.6,
    }),
    onEachFeature: (f, layer) => {
      const m = porCodigo[f.properties.codigo_ibge] || {};
      layer.bindTooltip(
        `<strong>${esc(f.properties.nome)}</strong><br>` +
        `Índice: ${fmt(m.indice, 2)} (${esc(m.classificacao || "sem dados")})<br>` +
        `${fmt(m.caps_total)} CAPS · ${fmt(m.populacao)} hab.` +
        (m.faltam && m.faltam.length ? `<br>Faltam: ${esc(m.faltam.join(", "))}` : ""), { sticky: true });
      layer.on({
        mouseover: (e) => e.target.setStyle({ weight: 2, color: TINTA.primaria }),
        mouseout: (e) => camada.resetStyle(e.target),
      });
    },
  }).addTo(mapa);
  mapa.fitBounds(camada.getBounds());
  $("#legenda-mapa").innerHTML = CLASSES.map((c) => `<span><i style="background:${c.cor}"></i>${c.nome} (${c.faixa})</span>`).join("") +
    `<span><i style="background:${SEM_DADOS};border:1px solid #ccc"></i>Sem dados de população</span>`;
}

const linhaReferencia = {
  id: "linhaReferencia",
  afterDatasetsDraw(chart, _args, opcoes) {
    const x = chart.scales.x.getPixelForValue(opcoes.valor);
    const { top, bottom } = chart.chartArea;
    const ctx = chart.ctx;
    ctx.save();
    ctx.strokeStyle = TINTA.secundaria;
    ctx.setLineDash([4, 4]);
    ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, bottom); ctx.stroke();
    ctx.restore();
  },
};

function desenharRegioes(regioes) {
  const piores = regioes.filter((r) => r.indice != null).slice(0, 20);
  new Chart($("#grafico-regioes"), {
    type: "bar",
    data: {
      labels: piores.map((r) => r.regiao),
      datasets: [{ data: piores.map((r) => r.indice), backgroundColor: SERIE, borderRadius: 4, barPercentage: 0.7 }],
    },
    options: {
      indexAxis: "y", maintainAspectRatio: false,
      scales: {
        x: { beginAtZero: true, suggestedMax: 0.8, grid: { color: TINTA.grade }, title: { display: true, text: "CAPS por 100 mil hab." } },
        y: { grid: { display: false }, ticks: { autoSkip: false, font: { size: 11 } } },
      },
      plugins: {
        linhaReferencia: { valor: 0.7 },
        tooltip: { callbacks: { label: (c) => {
          const r = piores[c.dataIndex];
          return `${fmt(r.indice, 2)} · ${r.caps_total} CAPS · ${fmt(r.populacao)} hab.`;
        } } },
      },
    },
    plugins: [linhaReferencia],
  });
}

function desenharDispersao(municipios) {
  const pontos = municipios.filter((m) => m.populacao && m.indice != null)
    .map((m) => ({ x: m.populacao, y: m.indice, nome: m.nome, caps: m.caps_total }));
  new Chart($("#grafico-dispersao"), {
    type: "scatter",
    data: { datasets: [{ data: pontos, backgroundColor: SERIE + "b3", borderColor: "#ffffff", borderWidth: 1, pointRadius: 4, pointHoverRadius: 7 }] },
    options: {
      maintainAspectRatio: false,
      scales: {
        x: { type: "logarithmic", title: { display: true, text: "População (escala log)" }, grid: { color: TINTA.grade },
             ticks: { callback: (v) => ([1e3, 1e4, 1e5, 1e6, 1e7].includes(v) ? fmt(v) : "") } },
        y: { beginAtZero: true, title: { display: true, text: "CAPS por 100 mil hab." }, grid: { color: TINTA.grade } },
      },
      plugins: { tooltip: { callbacks: { label: (c) => {
        const p = c.raw;
        return `${p.nome}: ${fmt(p.y, 2)} · ${p.caps} CAPS · ${fmt(p.x)} hab.`;
      } } } },
    },
  });
}

function prepararTabela(municipios) {
  dadosMunicipios = municipios;
  $("#filtro-classe").innerHTML += CLASSES.map((c) => `<option>${c.nome}</option>`).join("") + "<option>Sem dados</option>";
  ["#filtro-nome", "#filtro-classe", "#filtro-deficit"].forEach((s) => $(s).addEventListener("input", desenharTabela));
  document.querySelectorAll("th[data-col]").forEach((th) => th.addEventListener("click", () => {
    const col = th.dataset.col;
    ordem = { col, asc: ordem.col === col ? !ordem.asc : true };
    desenharTabela();
  }));
  desenharTabela();
}

function desenharTabela() {
  const nome = $("#filtro-nome").value.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const classe = $("#filtro-classe").value;
  const soDeficit = $("#filtro-deficit").checked;
  const linhas = dadosMunicipios.filter((m) =>
    (!nome || m.nome.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().includes(nome)) &&
    (!classe || m.classificacao === classe) && (!soDeficit || m.faltam.length));
  const { col, asc } = ordem;
  linhas.sort((a, b) => {
    let va = a[col], vb = b[col];
    if (col === "faltam") { va = a.faltam.length; vb = b.faltam.length; }
    if (va == null) return 1;
    if (vb == null) return -1;
    const r = typeof va === "string" ? va.localeCompare(vb, "pt-BR") : va - vb;
    return asc ? r : -r;
  });
  $("#tabela-municipios").innerHTML = linhas.map((m) => `<tr>
      <td>${esc(m.nome)}</td><td>${esc(m.regiao || "")}</td>
      <td class="num">${fmt(m.populacao)}</td><td class="num">${fmt(m.caps_total)}</td>
      <td class="num">${fmt(m.indice, 2)}</td>
      <td><i style="display:inline-block;width:10px;height:10px;border-radius:2px;background:${corDaClasse(m.classificacao)};margin-right:6px"></i>${esc(m.classificacao)}</td>
      <td>${esc(m.faltam.join(", ") || "—")}</td><td class="num">${fmt(m.buscas_app)}</td></tr>`).join("");
}

function desenharDemanda(d) {
  if (!d.total) {
    $("#grafico-demanda").parentElement.innerHTML = '<p class="dica">Ainda não há buscas registradas. Elas aparecem aqui conforme o app é usado.</p>';
  } else {
    new Chart($("#grafico-demanda"), {
      type: "line",
      data: { labels: d.por_dia.map(([dia]) => dia.split("-").reverse().join("/")),
              datasets: [{ data: d.por_dia.map(([, n]) => n), borderColor: SERIE, borderWidth: 2, pointRadius: 3, tension: 0 }] },
      options: { maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
        scales: { y: { beginAtZero: true, title: { display: true, text: "Buscas por dia" }, grid: { color: TINTA.grade } },
                  x: { grid: { display: false } } } },
    });
  }
  $("#tabela-demanda").innerHTML = d.municipios.map((m) =>
    `<tr><td>${esc(m.nome)}</td><td class="num">${fmt(m.buscas)}</td><td class="num">${fmt(m.sem_servico_perto)}</td></tr>`).join("")
    || '<tr><td colspan="3" class="dica">Sem dados ainda.</td></tr>';
}

iniciar();
