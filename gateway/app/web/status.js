// Barra de status do cabeçalho: consulta GET /saude do gateway a cada 5 s e acende
// o indicador de cada serviço. Usa só textContent/classList (nada de innerHTML).
"use strict";
(function () {
  const NOMES = { usuarios: "Usuários", inventario: "Inventário", chamados: "Chamados" };
  const INTERVALO_MS = 5000;
  const LIMITE_MS = 4000;
  const raiz = document.getElementById("status-servicos");
  if (!raiz) return;

  function aplicar(estados) {
    raiz.querySelectorAll(".chip").forEach((chip) => {
      const chave = chip.dataset.servico;
      const online = estados[chave] === "online";
      const led = chip.querySelector(".led");
      led.className = "led " + (online ? "on" : "off");
      chip.querySelector(".st").textContent = online ? "online" : "offline";
      chip.title = (NOMES[chave] || chave) + ": " + (online ? "online" : "offline");
    });
  }

  async function atualizar() {
    const controle = new AbortController();
    const prazo = setTimeout(() => controle.abort(), LIMITE_MS);
    try {
      const r = await fetch("/saude", { cache: "no-store", signal: controle.signal });
      const dados = await r.json();
      aplicar((dados && dados.servicos) || {});
    } catch (e) {
      aplicar({});  // sem resposta do gateway: tudo aparece como offline
    } finally {
      clearTimeout(prazo);
    }
  }

  setInterval(() => { if (!document.hidden) atualizar(); }, INTERVALO_MS);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) atualizar(); });
  atualizar();
})();
