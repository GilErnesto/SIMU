import { useEffect, useState } from "react";

import { marcarNotificacoesLidas, notificacoesDoCidadao, obterConfig, reportesDoCidadao } from "./api.js";
import { idCidadao } from "./armazenamento.js";
import Marca from "./Marca.jsx";
import Navegacao from "./Navegacao.jsx";
import { ESTADOS_REPORTE, formatarDataHora, rotuloClasse, rotuloProblema } from "./rotulos.js";
import { Ligacao } from "./rota.js";

// /notificacoes: what changed in this browser's reports (newest first, unread in bold), then the reports.
export default function Notificacoes() {
  const [dados, setDados]= useState(null);
  const [meus, setMeus]= useState([]);
  const [config, setConfig]= useState(null);
  const [erro, setErro]= useState(null);

  useEffect(() => {
    const controlo= new AbortController();
    const cidadao= idCidadao();
    Promise.all([
      notificacoesDoCidadao(cidadao, controlo.signal),
      reportesDoCidadao(cidadao, controlo.signal),
      obterConfig(controlo.signal),
    ])
      .then(([notificacoes, reportes, configuracao]) => {
        setDados(notificacoes);
        setMeus(reportes);
        setConfig(configuracao);
        if (notificacoes.nao_lidas > 0) {
          // Seen now: the bold stays on screen until the next visit, the counter clears at once.
          marcarNotificacoesLidas(cidadao)
            .then(() => window.dispatchEvent(new Event("simu:notificacoes")))
            .catch(() => {});
        }
      })
      .catch((e) => e.name !== "AbortError" && setErro(e.message));
    return () => controlo.abort();
  }, []);

  return (
    <div className="pagina">
      <header className="cabecalho cabecalho--simples cabecalho--inicio">
        <Marca />
        <Navegacao />
      </header>
      <main className="reporte">
        <h1 className="reporte__titulo">Notificações</h1>
        {erro && (
          <p className="mensagem mensagem--erro" role="alert">
            {erro}
          </p>
        )}
        {!dados && !erro && <p className="mensagem">A carregar…</p>}
        {dados && dados.notificacoes.length === 0 && (
          <p className="mensagem">
            Ainda não tem notificações. Quando um técnico tratar um reporte seu, aparece aqui.
          </p>
        )}
        {dados && dados.notificacoes.length > 0 && (
          <ul className="notificacoes">
            {dados.notificacoes.map((n) => (
              <li key={n.id} className={n.lida ? "notificacao" : "notificacao notificacao--nova"}>
                <Ligacao para={`/reportar/${n.reporte}`} className="notificacao__ligacao">
                  {!n.lida && <span className="visualmente-escondido">Nova: </span>}
                  <span className="notificacao__texto">{n.texto}</span>
                  <span className="notificacao__quando">{formatarDataHora(n.criada_em)}</span>
                </Ligacao>
              </li>
            ))}
          </ul>
        )}

        <h2>Os meus reportes</h2>
        {meus.length === 0 ? (
          <p className="nota">
            Ainda não enviou nenhum reporte. <Ligacao para="/reportar">Reportar um problema</Ligacao>.
          </p>
        ) : (
          <ul className="notificacoes">
            {meus.map((r) => (
              <li key={r.token} className="notificacao">
                <Ligacao para={`/reportar/${r.token}`} className="notificacao__ligacao">
                  <span className="notificacao__texto">
                    {rotuloProblema(config, r.categoria, r.problema)}
                    {r.classe ? ` (${rotuloClasse(config, r.categoria, r.classe)})` : ""}
                  </span>
                  <span className={`etiqueta etiqueta--${r.estado}`}>{ESTADOS_REPORTE[r.estado] ?? r.estado}</span>
                  <span className="notificacao__quando">{formatarDataHora(r.criado_em)}</span>
                </Ligacao>
              </li>
            ))}
          </ul>
        )}
        <p className="nota">
          As notificações ficam guardadas neste browser, sem conta. Noutro dispositivo não aparecem.
        </p>
      </main>
    </div>
  );
}
