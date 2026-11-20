import * as Tabs from "@radix-ui/react-tabs";
import { BellOff, Camera, ChevronRight, Inbox } from "lucide-react";
import { useEffect, useState } from "react";

import { marcarNotificacoesLidas, notificacoesDoCidadao, obterConfig, reportesDoCidadao, urlFotoReporte } from "./api.js";
import { idCidadao } from "./armazenamento.js";
import { PaginaCidadao } from "./Reportar.jsx";
import { Etiqueta, IconeCategoria, IconeEstado, Quando, Vazio } from "./ReportesUi.jsx";
import { rotuloCategoria, rotuloClasse, rotuloProblema } from "./rotulos.js";
import { Ligacao } from "./rota.js";

function Notificacao({ n }) {
  return (
    <li>
      <Ligacao para={`/reportar/${n.reporte}`} className={n.lida ? "notificacao" : "notificacao notificacao--nova"}>
        <span className={`notificacao__avatar notificacao__avatar--${n.estado ?? "aberto"}`} aria-hidden="true">
          <IconeEstado estado={n.estado ?? "aberto"} reaberto={n.estado === "aberto"} size={20} />
        </span>
        <span className="notificacao__corpo">
          {!n.lida && <span className="visualmente-escondido">Nova: </span>}
          <span className="notificacao__texto">{n.texto}</span>
          <Quando em={n.criada_em} />
        </span>
        {!n.lida && <span className="notificacao__ponto" aria-hidden="true" />}
      </Ligacao>
    </li>
  );
}

function MeuReporte({ config, r }) {
  const foto= urlFotoReporte(r);
  return (
    <li>
      <Ligacao para={`/reportar/${r.token}`} className="meu-reporte">
        {foto ? (
          <img className="meu-reporte__foto" src={foto} alt="" />
        ) : (
          <span className="meu-reporte__foto meu-reporte__foto--vazia">
            <IconeCategoria categoria={r.categoria} size={22} />
          </span>
        )}
        <span className="meu-reporte__corpo">
          <span className="meu-reporte__titulo">{rotuloProblema(config, r.categoria, r.problema)}</span>
          <span className="meu-reporte__sub">
            {r.classe ? rotuloClasse(config, r.categoria, r.classe) : rotuloCategoria(config, r.categoria)} · <Quando em={r.criado_em} />
          </span>
          <Etiqueta estado={r.estado} />
        </span>
        <ChevronRight className="meu-reporte__seta" aria-hidden="true" size={20} />
      </Ligacao>
    </li>
  );
}

// /notificacoes: what changed in this browser's reports (newest first, unread highlighted), and the reports.
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
          // Seen now: they stay highlighted until the next visit, the counter clears at once.
          marcarNotificacoesLidas(cidadao)
            .then(() => window.dispatchEvent(new Event("simu:notificacoes")))
            .catch(() => {});
        }
      })
      .catch((e) => e.name !== "AbortError" && setErro(e.message));
    return () => controlo.abort();
  }, []);

  return (
    <PaginaCidadao>
      <header className="fluxo__cabeca">
        <h1>Notificações</h1>
        <p>As novidades dos problemas que reportou.</p>
      </header>
      {erro && (
        <p className="alerta alerta--erro" role="alert">
          {erro}
        </p>
      )}
      {!dados && !erro && (
        <div className="cartao esqueleto" aria-label="A carregar">
          <span />
          <span />
          <span />
        </div>
      )}
      {dados && config && (
        <Tabs.Root className="notif-abas" defaultValue="notificacoes">
          <Tabs.List className="notif-abas__lista" aria-label="Notificações e reportes">
            <Tabs.Trigger className="notif-abas__botao" value="notificacoes">
              Notificações
              {dados.nao_lidas > 0 && <span className="notif-abas__contador">{dados.nao_lidas}</span>}
            </Tabs.Trigger>
            <Tabs.Trigger className="notif-abas__botao" value="reportes">
              Os meus reportes
              <span className="notif-abas__contador notif-abas__contador--neutro">{meus.length}</span>
            </Tabs.Trigger>
          </Tabs.List>
          <Tabs.Content value="notificacoes" className="notif-abas__conteudo">
            {dados.notificacoes.length === 0 ? (
              <Vazio icone={BellOff} titulo="Ainda não há notificações">
                Quando a Câmara tratar um reporte seu, avisamos aqui.
              </Vazio>
            ) : (
              <ul className="cartao lista-notificacoes">
                {dados.notificacoes.map((n) => (
                  <Notificacao key={n.id} n={n} />
                ))}
              </ul>
            )}
          </Tabs.Content>
          <Tabs.Content value="reportes" className="notif-abas__conteudo">
            {meus.length === 0 ? (
              <Vazio icone={Inbox} titulo="Ainda não reportou nenhum problema">
                <Ligacao para="/reportar" className="botao-g botao-g--principal">
                  <Camera aria-hidden="true" size={18} />
                  Reportar um problema
                </Ligacao>
              </Vazio>
            ) : (
              <ul className="lista-meus">
                {meus.map((r) => (
                  <MeuReporte key={r.token} config={config} r={r} />
                ))}
              </ul>
            )}
          </Tabs.Content>
        </Tabs.Root>
      )}
      <p className="nota-privacidade">
        <Inbox aria-hidden="true" size={18} />
        Sem conta: as notificações ficam guardadas neste dispositivo.
      </p>
    </PaginaCidadao>
  );
}
