// Servidor falso para os testes de JavaScript (roda só no PC, pelo tests/test_js.py).
// Troca o fetch do navegador: cada pedido fica parado até o cenário responder.
var Falso = (function () {
  "use strict";

  var pedidos = [];
  var noAr = 0;         // pedidos enviados e ainda sem resposta
  var maximoNoAr = 0;   // maior número de pedidos no ar ao mesmo tempo

  var falso = {
    pedidos: pedidos,
    // true = finge um navegador sem AbortController: a resposta pode chegar
    // depois do tempo limite (para testar que ela é descartada).
    ignorarCancelamento: false,
    maximoNoAr: function () { return maximoNoAr; }
  };

  window.fetch = function (url, config) {
    return new Promise(function (resolver, rejeitar) {
      var pedido = {
        url: url,
        metodo: config.method,
        corpo: config.body ? JSON.parse(config.body) : null,
        terminado: false,   // saiu da conta de "no ar" (respondido ou cancelado)
        respondido: false,  // a promessa do fetch já terminou
        responder: function (status, dados) {
          if (pedido.respondido) return;
          pedido.respondido = true;
          if (!pedido.terminado) { pedido.terminado = true; noAr--; }
          resolver({ status: status, json: function () { return Promise.resolve(dados); } });
        }
      };
      noAr++;
      maximoNoAr = Math.max(maximoNoAr, noAr);
      if (config.signal) {
        config.signal.addEventListener("abort", function () {
          if (pedido.terminado) return;
          pedido.terminado = true;
          noAr--;
          if (!falso.ignorarCancelamento) {
            pedido.respondido = true;
            rejeitar(new Error("cancelado"));
          }
        });
      }
      pedidos.push(pedido);
    });
  };

  return falso;
})();
