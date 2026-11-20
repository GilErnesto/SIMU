import { Bell, Camera, FolderOpen, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";

import { listarReportes, notificacoesDoCidadao } from "./api.js";
import { idCidadao } from "./armazenamento.js";
import Marca from "./Marca.jsx";
import { Ligacao, useCaminho } from "./rota.js";

// Two separate areas: the citizen's (/reportar, /notificacoes) and the technician's (/, /a/..., /tecnico/...).

function usePeriodico(carregar, evento, intervaloMs) {
  const caminho= useCaminho();
  const [valor, setValor]= useState(0);
  useEffect(() => {
    const controlo= new AbortController();
    const atualizar= () =>
      carregar(controlo.signal)
        .then(setValor)
        .catch(() => {});
    atualizar();
    const temporizador= setInterval(atualizar, intervaloMs);
    window.addEventListener(evento, atualizar);
    return () => {
      controlo.abort();
      clearInterval(temporizador);
      window.removeEventListener(evento, atualizar);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caminho]);
  return valor;
}

export function useNaoLidas() {
  return usePeriodico(
    (sinal) => notificacoesDoCidadao(idCidadao(), sinal).then((dados) => dados.nao_lidas),
    "simu:notificacoes",
    30000,
  );
}

export function useProblemasAbertos() {
  return usePeriodico(
    (sinal) => listarReportes("abertos", null, sinal).then((dados) => dados.features.length),
    "simu:reportes",
    60000,
  );
}

function Contador({ valor, rotulo }) {
  if (!valor) return null;
  return (
    <span className="contador" aria-label={rotulo}>
      {valor > 99 ? "99+" : valor}
    </span>
  );
}

// Citizen header: brand, "Reportar" and the notifications bell in the top-right corner.
export function CabecalhoCidadao() {
  const caminho= useCaminho();
  const naoLidas= useNaoLidas();
  const emNotificacoes= caminho.startsWith("/notificacoes");
  return (
    <header className="cabecalho-cidadao">
      <div className="cabecalho-cidadao__dentro">
        <Marca para="/reportar" />
        <span className="cabecalho-cidadao__area">Reportar problemas na rua</span>
        <nav className="cabecalho-cidadao__acoes" aria-label="Cidadão">
          {caminho !== "/reportar" ? (
            <Ligacao para="/reportar" className="botao-g botao-g--secundario botao-g--compacto cabecalho-cidadao__novo">
              <Camera aria-hidden="true" size={18} />
              <span>Novo reporte</span>
            </Ligacao>
          ) : null}
          <Ligacao
            para="/notificacoes"
            className="sino"
            aria-current={emNotificacoes ? "page" : undefined}
            aria-label={naoLidas ? `Notificações, ${naoLidas} por ler` : "Notificações"}
          >
            <Bell aria-hidden="true" size={22} strokeWidth={emNotificacoes ? 2.4 : 2} />
            <Contador valor={naoLidas} rotulo={`${naoLidas} por ler`} />
          </Ligacao>
        </nav>
      </div>
    </header>
  );
}

const SECCOES_TECNICO= [
  { para: "/", rotulo: "Análises", Icone: FolderOpen, ativo: (c) => c === "/" || c.startsWith("/a/") },
  { para: "/tecnico/reportes", rotulo: "Problemas", Icone: TriangleAlert, ativo: (c) => c.startsWith("/tecnico"), contador: true },
];

// Technician navigation: analyses (map work) and the problems inbox.
export function NavegacaoTecnico() {
  const caminho= useCaminho();
  const abertos= useProblemasAbertos();
  return (
    <nav className="nav-tecnico" aria-label="Área do técnico">
      {SECCOES_TECNICO.map(({ para, rotulo, Icone, ativo, contador }) => (
        <Ligacao key={para} para={para} className="nav-tecnico__ligacao" aria-current={ativo(caminho) ? "page" : undefined}>
          <Icone aria-hidden="true" size={18} />
          <span>{rotulo}</span>
          {contador && <Contador valor={abertos} rotulo={`${abertos} por tratar`} />}
        </Ligacao>
      ))}
    </nav>
  );
}
