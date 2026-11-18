/* MenteAcessível SP — tela de busca */
"use strict";

const CORES = { CAPS: "#2a78d6", URGENCIA: "#eb6834", ATENCAO_BASICA: "#1baf7a" };
const NOMES_CATEGORIA = { CAPS: "CAPS", URGENCIA: "Pronto atendimento", ATENCAO_BASICA: "UBS" };
const estado = { municipios: [], modalidades: {}, ultimaOrigem: null, marcadores: {} };

const $ = (sel) => document.querySelector(sel);
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
function formatarTelefone(t) {
  const d = String(t || "").replace(/\D/g, "").replace(/^0+/, "");
  if (d.length === 10) return `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`;
  if (d.length === 11) return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`;
  if (d.length === 8) return `${d.slice(0, 4)}-${d.slice(4)}`;
  return t || "";
}
const semAcento = (t) => String(t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();

async function api(caminho, opcoes) {
  const r = await fetch(caminho, opcoes);
  const dados = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(dados.erro || `Erro ${r.status}`);
  return dados;
}

function avisar(html, tipo = "") {
  $("#status").innerHTML = html ? `<div class="${tipo || "dica"}">${html}</div>` : "";
}

/* ------------------------------------------------------------------ mapa */
const mapa = L.map("mapa", { zoomControl: true }).setView([-22.4, -48.5], 7);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
}).addTo(mapa);
const camadaCaps = L.layerGroup().addTo(mapa);
const camadaResultados = L.layerGroup().addTo(mapa);
const camadaRota = L.layerGroup().addTo(mapa);

const legenda = L.control({ position: "bottomleft" });
legenda.onAdd = () => {
  const div = L.DomUtil.create("div", "cartao");
  div.style.padding = "8px 10px";
  div.style.margin = "0";
  div.innerHTML = Object.entries(CORES).map(([cat, cor]) =>
    `<div><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${cor};margin-right:6px"></span>${NOMES_CATEGORIA[cat]}</div>`
  ).join("");
  return div;
};
legenda.addTo(mapa);

function marcador(u, destaque) {
  return L.circleMarker([u.lat, u.lon], {
    radius: destaque ? 9 : 5,
    color: "#ffffff",
    weight: 2,
    fillColor: CORES[u.categoria] || CORES.CAPS,
    fillOpacity: destaque ? 1 : 0.75,
  });
}

/* ------------------------------------------------------------- inicial */
async function iniciar() {
  try {
    const status = await api("/api/status");
    if (!status.pronto) {
      avisar("O banco de dados ainda está vazio. No terminal, rode <code>python -m etl.coletar</code> e reinicie o servidor.", "aviso");
      return;
    }
    const [perfis, municipios, caps] = await Promise.all([
      api("/api/perfis"), api("/api/municipios"), api("/api/unidades/caps"),
    ]);
    estado.modalidades = perfis.modalidades;
    estado.municipios = municipios;
    $("#lista-municipios").innerHTML = municipios.map((m) => `<option value="${esc(m.nome)}">`).join("");
    caps.forEach((u) => {
      marcador({ ...u, categoria: "CAPS" }, false)
        .bindTooltip(esc(u.nome))
        .on("click", () => abrirFicha(u.cnes))
        .addTo(camadaCaps);
    });
    avisar(`${caps.length} CAPS no mapa. Use sua localização ou digite um endereço para ver os mais indicados.`);
  } catch (erro) {
    const salvo = lerCache();
    if (salvo) {
      avisar("Sem conexão: mostrando a última busca salva.", "aviso");
      mostrarResultados(salvo, true);
    } else {
      avisar(`Não foi possível carregar os dados (${esc(erro.message)}).`, "aviso");
    }
  }
}

function perfilAtual() {
  return document.querySelector('input[name="perfil"]:checked').value;
}

/* --------------------------------------------------------------- busca */
async function buscar(lat, lon, rotulo) {
  estado.ultimaOrigem = { lat, lon, rotulo };
  avisar("Buscando serviços próximos...");
  try {
    const dados = await api(`/api/unidades/proximas?lat=${lat}&lon=${lon}&perfil=${perfilAtual()}&limite=10`);
    dados.origem = { lat, lon, rotulo };
    salvarCache(dados);
    mostrarResultados(dados);
  } catch (erro) {
    avisar(`Não foi possível buscar agora (${esc(erro.message)}).`, "aviso");
  }
}

function mostrarResultados(dados, doCache = false) {
  const lista = $("#resultados");
  camadaResultados.clearLayers();
  camadaRota.clearLayers();
  estado.marcadores = {};
  const { origem } = dados;
  if (!dados.resultados.length) {
    lista.innerHTML = "";
    avisar("Nenhum serviço compatível encontrado num raio de 250 km. Tente o perfil “Qualquer serviço” ou ligue 136 (Disque Saúde).", "aviso");
    return;
  }
  const local = dados.municipio_usuario_nome ? ` em ${esc(dados.municipio_usuario_nome)}` : "";
  if (!doCache) {
    avisar(`${dados.resultados.length} serviços indicados${local}, do mais adequado ao menos adequado.` +
      (dados.raio_km > 30 ? ` Não há opções a menos de 30 km; ampliamos a busca para ${dados.raio_km} km.` : ""));
  }
  lista.innerHTML = dados.resultados.map((u, i) => `
    <li class="resultado" tabindex="0" data-cnes="${esc(u.cnes)}">
      <h3>${i + 1}. ${esc(u.nome)}</h3>
      <div class="meta">${esc(u.modalidade_nome)} · ${u.distancia_km.toLocaleString("pt-BR")} km · ${esc(u.municipio)}</div>
      <div>
        ${u.funciona_24h ? '<span class="selo h24">24 horas</span>' : ""}
        <span class="selo ${u.situacao.startsWith("Aberto") || u.situacao.startsWith("Provavelmente aberto") ? "aberto" : "fechado"}">${esc(u.situacao)}</span>
        ${u.compatibilidade >= 1 ? '<span class="selo">Indicado para o perfil</span>' : ""}
      </div>
    </li>`).join("");

  // No celular o mapa fica abaixo da busca: rola até ele para mostrar os resultados
  if (!doCache && window.matchMedia("(max-width: 860px)").matches) {
    $("#status").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  const pontos = [];
  if (origem) {
    L.circleMarker([origem.lat, origem.lon], { radius: 7, color: "#0b0b0b", weight: 2, fillColor: "#ffffff", fillOpacity: 1 })
      .bindTooltip("Você está aqui").addTo(camadaResultados);
    pontos.push([origem.lat, origem.lon]);
  }
  dados.resultados.forEach((u) => {
    const m = marcador(u, true).bindTooltip(esc(u.nome)).on("click", () => abrirFicha(u.cnes)).addTo(camadaResultados);
    estado.marcadores[u.cnes] = m;
    pontos.push([u.lat, u.lon]);
  });
  mapa.fitBounds(pontos, { padding: [40, 40], maxZoom: 15 });
}

$("#resultados").addEventListener("click", (e) => {
  const item = e.target.closest(".resultado");
  if (item) abrirFicha(item.dataset.cnes);
});
$("#resultados").addEventListener("keydown", (e) => {
  const item = e.target.closest(".resultado");
  if (item && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); abrirFicha(item.dataset.cnes); }
});
$("#resultados").addEventListener("mouseover", (e) => {
  const item = e.target.closest(".resultado");
  const m = item && estado.marcadores[item.dataset.cnes];
  if (m) m.openTooltip();
});

document.querySelectorAll('input[name="perfil"]').forEach((r) => r.addEventListener("change", () => {
  if (estado.ultimaOrigem) buscar(estado.ultimaOrigem.lat, estado.ultimaOrigem.lon, estado.ultimaOrigem.rotulo);
}));

/* ---------------------------------------------------------- localização */
function usarLocalizacao(perfilForcado) {
  if (perfilForcado) document.querySelector(`input[value="${perfilForcado}"]`).checked = true;
  if (!window.isSecureContext) {
    // Celulares só liberam o GPS em sites HTTPS (ou no próprio computador, em localhost)
    avisar("O GPS só funciona quando o app é aberto por um link <strong>https://</strong>. " +
      "Por enquanto, digite seu CEP, endereço ou cidade no campo abaixo.", "aviso");
    $("#endereco").focus();
    return;
  }
  if (!navigator.geolocation) {
    avisar("Seu navegador não informa a localização. Digite um endereço ou cidade.", "aviso");
    return;
  }
  avisar("Pedindo permissão para usar sua localização...");
  navigator.geolocation.getCurrentPosition(
    (pos) => buscar(pos.coords.latitude.toFixed(5), pos.coords.longitude.toFixed(5), "Sua localização"),
    () => avisar("Não foi possível obter sua localização. Digite um CEP, endereço ou cidade.", "aviso"),
    { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 },
  );
}
$("#usar-localizacao").addEventListener("click", () => usarLocalizacao());

/* -------------------------------------------- geocodificação do endereço */
async function geocodificar(texto) {
  const alvo = semAcento(texto);
  const mun = estado.municipios.find((m) => semAcento(m.nome) === alvo);
  if (mun && mun.lat) return { lat: mun.lat, lon: mun.lon, rotulo: mun.nome };

  let consulta = `${texto}, São Paulo, Brasil`;
  const cep = texto.replace(/\D/g, "");
  if (cep.length === 8) {
    try {
      const v = await (await fetch(`https://viacep.com.br/ws/${cep}/json/`)).json();
      if (!v.erro) {
        if (v.uf && v.uf !== "SP") throw new Error("CEP fora de SP");
        consulta = [v.logradouro, v.bairro, v.localidade, "SP", "Brasil"].filter(Boolean).join(", ");
        const m = estado.municipios.find((x) => semAcento(x.nome) === semAcento(v.localidade));
        const r = await nominatim(consulta);
        if (r) return { ...r, rotulo: `CEP ${texto}` };
        if (m) return { lat: m.lat, lon: m.lon, rotulo: `${m.nome} (centro da cidade)` };
      }
    } catch (erro) {
      if (erro.message === "CEP fora de SP") throw erro;
    }
  }
  const r = await nominatim(consulta);
  if (r) return { ...r, rotulo: texto };
  throw new Error("Endereço não encontrado");
}

async function nominatim(consulta) {
  const url = `https://nominatim.openstreetmap.org/search?format=json&limit=1&countrycodes=br&q=${encodeURIComponent(consulta)}`;
  try {
    const dados = await (await fetch(url, { headers: { "Accept-Language": "pt-BR" } })).json();
    return dados[0] ? { lat: Number(dados[0].lat).toFixed(5), lon: Number(dados[0].lon).toFixed(5) } : null;
  } catch {
    return null;
  }
}

$("#form-endereco").addEventListener("submit", async (e) => {
  e.preventDefault();
  const texto = $("#endereco").value.trim();
  if (!texto) return;
  avisar("Localizando endereço...");
  try {
    const g = await geocodificar(texto);
    buscar(g.lat, g.lon, g.rotulo);
  } catch (erro) {
    avisar(erro.message === "CEP fora de SP"
      ? "Este CEP não é do Estado de São Paulo. O app cobre apenas SP."
      : "Não encontramos esse endereço. Tente só o nome da cidade ou do bairro e a cidade.", "aviso");
  }
});

/* --------------------------------------------------------------- ficha */
async function abrirFicha(cnes) {
  const dialogo = $("#dialogo-ficha");
  const corpo = $("#ficha-conteudo");
  corpo.innerHTML = "<p>Carregando...</p>";
  dialogo.showModal();
  try {
    const u = await api(`/api/unidades/${encodeURIComponent(cnes)}`);
    const tel = (u.telefone || "").replace(/\D/g, "");
    const destino = `${u.lat},${u.lon}`;
    const endereco = [u.endereco, u.bairro, u.municipio].filter(Boolean).join(", ");
    const horarios = u.horarios.length
      ? `<ul>${u.horarios.map((h) => `<li>${esc(h.dia_nome)}: ${esc(h.abre)} às ${esc(h.fecha)}${h.observacao ? ` (${esc(h.observacao)})` : ""}</li>`).join("")}</ul>
         <p class="dica">Horário verificado${u.horarios[0].verificado_em ? ` em ${esc(u.horarios[0].verificado_em)}` : ""}.</p>`
      : `<p>${esc(u.turno || "Turno não informado no cadastro")}.</p><p class="dica">Horário do cadastro do CNES, não verificado. Ligue antes de ir.</p>`;
    corpo.innerHTML = `
      <button class="fechar" data-fechar aria-label="Fechar">&times;</button>
      <h2 id="ficha-nome">${esc(u.nome)}</h2>
      <p><span class="selo">${esc(u.modalidade_nome)}</span>${u.funciona_24h ? '<span class="selo h24">24 horas</span>' : ""}</p>
      <p>${esc(u.descricao)}</p>
      <h3>Endereço</h3>
      <p>${esc(endereco)}${u.cep ? ` — CEP ${esc(u.cep)}` : ""}</p>
      ${u.coordenada_aproximada ? '<p class="aviso">A localização no mapa é aproximada (centro da cidade): o cadastro não tem coordenadas confiáveis.</p>' : ""}
      <div class="acoes">
        ${tel ? `<a class="botao primario" href="tel:${tel}">Ligar ${esc(formatarTelefone(u.telefone))}</a>` : ""}
        <button class="botao" id="compartilhar" type="button">Compartilhar</button>
      </div>
      <section class="como-chegar" aria-labelledby="titulo-como-chegar">
        <h3 id="titulo-como-chegar">Como chegar</h3>
        <div class="abas" role="tablist" aria-label="Meio de transporte">
          <button role="tab" type="button" data-modo="transporte" aria-selected="false">Ônibus/metrô</button>
          <button role="tab" type="button" data-modo="carro" aria-selected="false">Carro</button>
          <button role="tab" type="button" data-modo="a_pe" aria-selected="false">A pé</button>
        </div>
        <div id="rota-conteudo" role="tabpanel" aria-live="polite"></div>
      </section>
      <h3>Funcionamento</h3>
      ${horarios}
      <h3>O que levar</h3>
      <ul class="lista-docs">${u.documentos.map((d) => `<li>${esc(d.documento)}${d.obrigatorio ? "" : " <em>(opcional)</em>"}${d.observacao ? `<br><small>${esc(d.observacao)}</small>` : ""}</li>`).join("")}</ul>
      <details>
        <summary>Informação errada? Avise a gente</summary>
        <form id="form-reporte" style="margin-top:10px">
          <label for="tipo-reporte">O que está errado?</label><br>
          <select id="tipo-reporte" required>
            <option value="telefone_errado">Telefone</option>
            <option value="endereco_errado">Endereço</option>
            <option value="horario_errado">Horário</option>
            <option value="unidade_fechada">A unidade fechou</option>
            <option value="outro">Outro</option>
          </select><br>
          <label for="texto-reporte">Detalhes (não escreva dados pessoais)</label><br>
          <textarea id="texto-reporte" maxlength="500" rows="3" style="width:100%"></textarea>
          <button class="botao pequeno" type="submit">Enviar</button>
        </form>
      </details>
      <p class="dica">CNES ${esc(u.cnes)} · dados de ${esc(u.competencia || "data não informada")}</p>`;

    prepararComoChegar(u);

    $("#compartilhar").addEventListener("click", () => {
      const texto = `${u.nome}\n${endereco}${u.telefone ? `\nTel: ${formatarTelefone(u.telefone)}` : ""}\nhttps://www.google.com/maps/search/?api=1&query=${destino}`;
      if (navigator.share) navigator.share({ title: u.nome, text: texto }).catch(() => {});
      else window.open(`https://wa.me/?text=${encodeURIComponent(texto)}`, "_blank", "noopener");
    });
    $("#form-reporte").addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await api("/api/reportes", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ cnes: u.cnes, tipo: $("#tipo-reporte").value, texto: $("#texto-reporte").value }),
        });
        e.target.innerHTML = "<p>Obrigado! Vamos verificar.</p>";
      } catch (erro) {
        e.target.insertAdjacentHTML("beforeend", `<p class="aviso">${esc(erro.message)}</p>`);
      }
    });
  } catch (erro) {
    corpo.innerHTML = `<button class="fechar" data-fechar aria-label="Fechar">&times;</button><p>Não foi possível abrir a ficha (${esc(erro.message)}).</p>`;
  }
}

/* --------------------------------------------------------- como chegar */
const NOME_MODO = { transporte: "de transporte público", carro: "de carro", a_pe: "a pé" };
const COR_ROTA = { carro: "#2a78d6", a_pe: "#1d6b1d" };

function formatarDuracao(seg) {
  const min = Math.max(1, Math.round(seg / 60));
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60), m = min % 60;
  return m ? `${h} h ${m} min` : `${h} h`;
}
function formatarDistancia(m) {
  return m < 1000 ? `${Math.round(m / 10) * 10} m` : `${(m / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} km`;
}

function prepararComoChegar(u) {
  const abas = document.querySelectorAll(".como-chegar [role=tab]");
  abas.forEach((aba) => aba.addEventListener("click", () => mostrarRota(u, aba.dataset.modo)));
  // Aba inicial: a pé se estiver perto (até 1,5 km); senão, transporte público
  const o = estado.ultimaOrigem;
  const perto = o && distanciaKm(o.lat, o.lon, u.lat, u.lon) <= 1.5;
  mostrarRota(u, perto ? "a_pe" : "transporte");
}

function distanciaKm(lat1, lon1, lat2, lon2) {
  const r = Math.PI / 180, a = Math.sin(((lat2 - lat1) * r) / 2) ** 2 +
    Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.sin(((lon2 - lon1) * r) / 2) ** 2;
  return 12742 * Math.asin(Math.sqrt(a));
}

function botoesLinks(links) {
  return `<div class="acoes">${links.map((l) =>
    `<a class="botao" target="_blank" rel="noopener" href="${esc(l.url)}">${esc(l.nome)}</a>`).join("")}</div>`;
}

async function mostrarRota(u, modo) {
  document.querySelectorAll(".como-chegar [role=tab]").forEach((aba) =>
    aba.setAttribute("aria-selected", String(aba.dataset.modo === modo)));
  const painel = $("#rota-conteudo");
  const o = estado.ultimaOrigem;
  painel.innerHTML = modo === "transporte" ? "" : "<p class='dica'>Calculando rota...</p>";
  const params = new URLSearchParams({ cnes: u.cnes, modo });
  if (o) { params.set("lat", o.lat); params.set("lon", o.lon); }

  let r;
  try {
    r = await api(`/api/rota?${params}`);
  } catch (erro) {
    painel.innerHTML = `<p class="aviso">Não foi possível calcular a rota (${esc(erro.message)}).</p>`;
    return;
  }
  const semOrigem = !o
    ? `<p class="aviso">Para traçar a rota a partir de onde você está, use <strong>Usar minha localização</strong> ou busque seu endereço na tela inicial.</p>`
    : "";

  if (modo === "transporte") {
    painel.innerHTML = `
      ${semOrigem}
      <p>${r.distancia_reta_km != null ? `A unidade fica a ${r.distancia_reta_km.toLocaleString("pt-BR")} km em linha reta. ` : ""}
      Veja as linhas de ônibus, metrô e trem, os horários e onde descer:</p>
      ${botoesLinks(r.links)}
      <p class="dica">Abre no Google Maps ou no Moovit, que têm os horários do transporte público de SP.</p>`;
    return;
  }

  if (!r.rota) {
    painel.innerHTML = `${semOrigem}${r.aviso && o ? `<p class="aviso">${esc(r.aviso)}</p>` : ""}${botoesLinks(r.links)}`;
    return;
  }

  const rota = r.rota;
  painel.innerHTML = `
    <p class="resumo-rota"><strong>${formatarDuracao(rota.duracao_s)}</strong> · ${formatarDistancia(rota.distancia_m)}
      ${modo === "carro" ? '<br><small class="dica">Tempo estimado sem considerar o trânsito.</small>' : ""}</p>
    <div class="acoes">
      <button class="botao primario" type="button" id="ver-rota-mapa">Ver no mapa</button>
      ${r.links.map((l) => `<a class="botao" target="_blank" rel="noopener" href="${esc(l.url)}">Navegar com ${esc(l.nome)}</a>`).join("")}
    </div>
    <details class="passos-rota">
      <summary>Passo a passo (${rota.passos.length} etapas)</summary>
      <ol>${rota.passos.map((p) => `<li>${esc(p.instrucao)}${p.distancia_m ? ` <small>${formatarDistancia(p.distancia_m)}</small>` : ""}</li>`).join("")}</ol>
    </details>
    <p class="dica">Rota: OpenStreetMap / OSRM. Confira a sinalização no caminho.</p>`;
  $("#ver-rota-mapa").addEventListener("click", () => desenharRota(u, modo, rota));
}

function desenharRota(u, modo, rota) {
  camadaRota.clearLayers();
  const pontos = rota.geometria.map(([lon, lat]) => [lat, lon]);
  L.polyline(pontos, { color: "#ffffff", weight: 8, opacity: 0.9 }).addTo(camadaRota);
  L.polyline(pontos, { color: COR_ROTA[modo], weight: 5, opacity: 1,
    dashArray: modo === "a_pe" ? "2 8" : null, lineCap: "round" }).addTo(camadaRota);
  mapa.fitBounds(pontos, { padding: [40, 40] });
  $("#dialogo-ficha").close();
  avisar(`Rota ${NOME_MODO[modo]} até <strong>${esc(u.nome)}</strong>: ${formatarDuracao(rota.duracao_s)} · ${formatarDistancia(rota.distancia_m)}.
    <button class="botao pequeno" type="button" id="reabrir-ficha">Voltar à ficha</button>
    <button class="botao pequeno" type="button" id="limpar-rota">Limpar rota</button>`);
  $("#reabrir-ficha").addEventListener("click", () => abrirFicha(u.cnes));
  $("#limpar-rota").addEventListener("click", () => { camadaRota.clearLayers(); avisar(""); });
  if (window.matchMedia("(max-width: 860px)").matches) $("#mapa").scrollIntoView({ behavior: "smooth" });
}

/* ------------------------------------------------------------ diálogos */
document.addEventListener("click", (e) => {
  if (e.target.matches("[data-fechar]")) e.target.closest("dialog").close();
  if (e.target.tagName === "DIALOG") e.target.close(); // clique fora
});

$("#botao-crise").addEventListener("click", () => $("#dialogo-crise").showModal());
$("#crise-proximo").addEventListener("click", () => {
  $("#dialogo-crise").close();
  if (estado.ultimaOrigem) {
    document.querySelector('input[value="crise"]').checked = true;
    buscar(estado.ultimaOrigem.lat, estado.ultimaOrigem.lon, estado.ultimaOrigem.rotulo);
  } else {
    usarLocalizacao("crise");
  }
});

$("#abrir-triagem").addEventListener("click", () => $("#dialogo-triagem").showModal());
$("#form-triagem").addEventListener("submit", (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  $("#dialogo-triagem").close();
  if (f.get("risco") === "sim") {
    $("#dialogo-crise").showModal();
    return;
  }
  const perfil = f.get("substancia") === "sim" ? "alcool_drogas" : f.get("idade") === "menor" ? "infantojuvenil" : "adulto";
  document.querySelector(`input[value="${perfil}"]`).checked = true;
  if (estado.ultimaOrigem) buscar(estado.ultimaOrigem.lat, estado.ultimaOrigem.lon, estado.ultimaOrigem.rotulo);
  else avisar("Perfil escolhido. Agora use sua localização ou digite um endereço.");
});

$("#abrir-tipos").addEventListener("click", async () => {
  const descricoes = {
    "CAPS I": "Municípios menores; atende todas as idades.",
    "CAPS II": "Adultos com sofrimento intenso, durante o dia.",
    "CAPS III": "Adultos, 24 horas, com acolhimento noturno.",
    "CAPS AD / AD III": "Uso de álcool e outras drogas (o AD III funciona 24h).",
    "CAPS Infantojuvenil": "Crianças e adolescentes.",
  };
  $("#lista-tipos").innerHTML = Object.entries(descricoes).map(([k, v]) => `<li><strong>${k}:</strong> ${v}</li>`).join("");
  $("#dialogo-tipos").showModal();
});

/* -------------------------------------------------------------- offline */
function salvarCache(dados) {
  try { localStorage.setItem("menteacessivel:ultima-busca", JSON.stringify(dados)); } catch { /* sem espaço */ }
}
function lerCache() {
  try { return JSON.parse(localStorage.getItem("menteacessivel:ultima-busca")); } catch { return null; }
}

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

/* ------------------------------------------------- instalar no celular */
let pedidoInstalacao = null;
window.addEventListener("beforeinstallprompt", (e) => {
  // Android/Chrome: mostra nosso botão em vez do aviso automático
  e.preventDefault();
  pedidoInstalacao = e;
  $("#instalar").hidden = false;
});
$("#instalar").addEventListener("click", async () => {
  if (!pedidoInstalacao) return;
  pedidoInstalacao.prompt();
  await pedidoInstalacao.userChoice.catch(() => {});
  pedidoInstalacao = null;
  $("#instalar").hidden = true;
});
window.addEventListener("appinstalled", () => { $("#instalar").hidden = true; });

/* ------------------------------------------- atalhos vindos do menu inicial */
// /buscar?perfil=adulto&acao=localizacao | ?q=CEP | ?triagem=1 | ?tipos=1 | ?crise=1
const parametros = new URLSearchParams(location.search);
const perfilPedido = parametros.get("perfil");
if (perfilPedido) {
  const opcao = document.querySelector(`input[name="perfil"][value="${CSS.escape(perfilPedido)}"]`);
  if (opcao) opcao.checked = true;
}

function aplicarAtalhos() {
  if (parametros.get("crise") === "1") $("#dialogo-crise").showModal();
  else if (parametros.get("triagem") === "1") $("#dialogo-triagem").showModal();
  else if (parametros.get("tipos") === "1") $("#abrir-tipos").click();

  if (parametros.get("acao") === "localizacao") {
    usarLocalizacao();
  } else if (parametros.get("q")) {
    $("#endereco").value = parametros.get("q");
    $("#form-endereco").requestSubmit();
  }
  // Limpa a barra de endereço para que recarregar a página não repita a ação
  if (parametros.toString()) history.replaceState(null, "", "/buscar");
}

iniciar().then(aplicarAtalhos);
