/* MenteAcessível SP — tela inicial */
"use strict";

// Data dos dados no rodapé
fetch("/api/status").then((r) => r.json()).then((s) => {
  const m = s.metadados || {};
  const rodape = document.getElementById("rodape-inicio");
  if (!s.pronto) {
    rodape.insertAdjacentHTML("afterbegin",
      '<span class="aviso" style="display:block;margin-bottom:8px">O banco de dados ainda está vazio. ' +
      "No computador, rode <code>python -m etl.coletar</code> e reinicie o servidor.</span>");
  } else if (m.total_unidades) {
    rodape.append(` ${Number(m.total_unidades).toLocaleString("pt-BR")} unidades em ` +
      `${m.total_municipios} municípios, dados de ${m.competencia_cnes}.`);
  }
}).catch(() => {});

// Instalar no celular (Android/Chrome)
let pedidoInstalacao = null;
const botaoInstalar = document.getElementById("instalar");
window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  pedidoInstalacao = e;
  botaoInstalar.hidden = false;
});
botaoInstalar.addEventListener("click", async () => {
  if (!pedidoInstalacao) return;
  pedidoInstalacao.prompt();
  await pedidoInstalacao.userChoice.catch(() => {});
  pedidoInstalacao = null;
  botaoInstalar.hidden = true;
});

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
