import { useEffect, useState } from "react";

import { notificacoesDoCidadao } from "./api.js";
import { idCidadao } from "./armazenamento.js";
import { Ligacao, useCaminho } from "./rota.js";

const INTERVALO_MS= 30000;

// Unread notifications of this browser's citizen, refreshed every 30 s and when the page changes.
export function useNaoLidas() {
  const caminho= useCaminho();
  const [naoLidas, setNaoLidas]= useState(0);
  useEffect(() => {
    const controlo= new AbortController();
    const cidadao= idCidadao();
    function atualizar() {
      notificacoesDoCidadao(cidadao, controlo.signal)
        .then((dados) => setNaoLidas(dados.nao_lidas))
        .catch(() => {});
    }
    atualizar();
    const temporizador= setInterval(atualizar, INTERVALO_MS);
    window.addEventListener("simu:notificacoes", atualizar);
    return () => {
      controlo.abort();
      clearInterval(temporizador);
      window.removeEventListener("simu:notificacoes", atualizar);
    };
  }, [caminho]);
  return naoLidas;
}

export default function Navegacao() {
  const caminho= useCaminho();
  const naoLidas= useNaoLidas();
  const atual= (prefixo) => (caminho.startsWith(prefixo) ? "page" : undefined);
  return (
    <nav className="navegacao" aria-label="Secções">
      <Ligacao para="/reportar" className="navegacao__ligacao" aria-current={atual("/reportar")}>
        Reportar problema
      </Ligacao>
      <Ligacao para="/notificacoes" className="navegacao__ligacao" aria-current={atual("/notificacoes")}>
        Notificações
        {naoLidas > 0 && (
          <span className="selo" aria-label={`${naoLidas} por ler`}>
            {naoLidas}
          </span>
        )}
      </Ligacao>
      <Ligacao para="/tecnico/reportes" className="navegacao__ligacao" aria-current={atual("/tecnico")}>
        Painel do técnico
      </Ligacao>
    </nav>
  );
}
