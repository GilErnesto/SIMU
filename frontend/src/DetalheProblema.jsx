import { CircleCheck, CircleX, Clock, Link2, LoaderCircle, MapPin, MapPinned, RotateCcw, Users, Wrench, X } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { mudarEstadoReporte, obterReporte } from "./api.js";
import FotoReporte from "./FotoReporte.jsx";
import { Etiqueta, IconeCategoria, LinhaDoTempo, Quando } from "./ReportesUi.jsx";
import { formatarDataHora, rotuloCategoria, rotuloClasse, rotuloProblema } from "./rotulos.js";
import { Ligacao } from "./rota.js";

const ORIGENS= { browser: "localização do telemóvel", exif: "GPS da fotografia", mapa: "indicada no mapa pelo cidadão" };
export const ABERTOS= new Set(["aberto", "em_resolucao"]);
const MENSAGENS= {
  em_resolucao: "Marcado como em resolução",
  resolvido: "Marcado como resolvido",
  rejeitado: "Arquivado sem intervenção",
  aberto: "Problema reaberto",
};

export function tituloProblema(config, p) {
  return rotuloProblema(config, p.categoria, p.problema);
}

export function tipoProblema(config, p) {
  return p.classe ? rotuloClasse(config, p.categoria, p.classe) : rotuloCategoria(config, p.categoria);
}

export function ligacaoNoMapa(p) {
  return p.analise && p.elemento_id ? `/a/${p.analise}?e=${p.elemento_id}` : null;
}

function BotaoEstado({ estado, Icone, classe, aGuardar, aoMudar, children }) {
  return (
    <button type="button" className={`botao-g ${classe}`} disabled={aGuardar !== null} onClick={() => aoMudar(estado)}>
      {aGuardar === estado ? <LoaderCircle className="a-rodar" aria-hidden="true" size={18} /> : <Icone aria-hidden="true" size={18} />}
      {children}
    </button>
  );
}

// One citizen problem for the technician: photo, data, the actions and the history. Used in the inbox
// (/tecnico/reportes) and in the "Problema" tab of the analysis map.
export default function DetalheProblema({ config, token, tecnico, aoMudar, aoFechar, comMapa= true, compacto= false }) {
  const [reporte, setReporte]= useState(null);
  const [nota, setNota]= useState("");
  const [erro, setErro]= useState(null);
  const [aGuardar, setAGuardar]= useState(null);

  useEffect(() => {
    const controlo= new AbortController();
    setReporte(null);
    setNota("");
    setErro(null);
    obterReporte(token, controlo.signal)
      .then(setReporte)
      .catch((e) => e.name !== "AbortError" && setErro(e.message));
    return () => controlo.abort();
  }, [token]);

  async function mudar(estado) {
    if (!tecnico.trim()) {
      toast.error("Indique o seu nome no campo Técnico antes de tratar o problema.");
      return;
    }
    setAGuardar(estado);
    try {
      const dados= await mudarEstadoReporte(token, { autor: tecnico.trim(), estado, nota: nota.trim() || null });
      setReporte(dados);
      setNota("");
      toast.success(MENSAGENS[estado], {
        description: dados.confirmacoes ? `${dados.confirmacoes + 1} cidadãos foram notificados.` : "O cidadão foi notificado.",
      });
      window.dispatchEvent(new Event("simu:reportes"));
      aoMudar?.(dados);
    } catch (falha) {
      toast.error(falha.message);
    } finally {
      setAGuardar(null);
    }
  }

  if (erro && !reporte) {
    return (
      <p className="alerta alerta--erro" role="alert">
        {erro}
      </p>
    );
  }
  if (!reporte) {
    return (
      <div className="cartao esqueleto" aria-label="A carregar o problema">
        <span />
        <span />
        <span />
      </div>
    );
  }
  const aberto= ABERTOS.has(reporte.estado);
  const noMapa= ligacaoNoMapa(reporte);
  return (
    <article className={compacto ? "detalhe-reporte detalhe-reporte--compacto" : "cartao detalhe-reporte"} aria-labelledby={`titulo-${token}`}>
      <header className="detalhe-reporte__cabeca">
        <span className="seguimento__icone" aria-hidden="true">
          <IconeCategoria categoria={reporte.categoria} size={22} />
        </span>
        <div className="detalhe-reporte__titulos">
          <h2 id={`titulo-${token}`}>{tituloProblema(config, reporte)}</h2>
          <p className="seguimento__sub">{tipoProblema(config, reporte)}</p>
        </div>
        <Etiqueta estado={reporte.estado} grande />
        {aoFechar && (
          <button type="button" className="botao-icone" aria-label="Fechar" onClick={aoFechar}>
            <X aria-hidden="true" size={18} />
          </button>
        )}
      </header>

      {reporte.confirmacoes > 0 && (
        <p className="confirmacoes">
          <Users aria-hidden="true" size={18} />
          Reportado por {reporte.confirmacoes + 1} cidadãos
        </p>
      )}
      {reporte.descricao && <blockquote className="seguimento__descricao">{reporte.descricao}</blockquote>}
      {!compacto && <FotoReporte reporte={reporte} />}

      <dl className="metadados">
        <div>
          <dt>
            <Clock aria-hidden="true" size={16} /> Recebido
          </dt>
          <dd title={formatarDataHora(reporte.criado_em)}>
            <Quando em={reporte.criado_em} />
          </dd>
        </div>
        <div>
          <dt>
            <MapPin aria-hidden="true" size={16} /> Posição
          </dt>
          <dd>
            {reporte.lat === null ? (
              "Desconhecida"
            ) : (
              <>
                {reporte.lat.toFixed(5)}, {reporte.lon.toFixed(5)}
                <span className="metadados__nota">{ORIGENS[reporte.origem_posicao] ?? reporte.origem_posicao}</span>
              </>
            )}
          </dd>
        </div>
        <div>
          <dt>
            <Link2 aria-hidden="true" size={16} /> Catálogo
          </dt>
          <dd>{reporte.elemento_id ? `Elemento n.º ${reporte.elemento_id}` : "Sem elemento a menos de 15 m"}</dd>
        </div>
      </dl>
      {comMapa && noMapa && (
        <Ligacao para={noMapa} className="botao-g botao-g--secundario">
          <MapPinned aria-hidden="true" size={18} />
          Ver no mapa da análise
        </Ligacao>
      )}

      <section className="acoes-reporte" aria-label="Tratar o problema">
        <label className="campo-g">
          <span className="campo-g__rotulo">
            Nota para o cidadão <span className="campo-g__opcional">(opcional)</span>
          </span>
          <textarea
            rows={2}
            maxLength={1000}
            placeholder={aberto ? "Por exemplo: sinal substituído esta manhã" : "Porque está a reabrir?"}
            value={nota}
            onChange={(e) => setNota(e.target.value)}
          />
        </label>
        <div className="acoes-reporte__botoes">
          {aberto ? (
            <>
              <BotaoEstado estado="resolvido" Icone={CircleCheck} classe="botao-g--sucesso" aGuardar={aGuardar} aoMudar={mudar}>
                Marcar como resolvido
              </BotaoEstado>
              {reporte.estado === "aberto" && (
                <BotaoEstado estado="em_resolucao" Icone={Wrench} classe="botao-g--secundario" aGuardar={aGuardar} aoMudar={mudar}>
                  Em resolução
                </BotaoEstado>
              )}
              <BotaoEstado estado="rejeitado" Icone={CircleX} classe="botao-g--fantasma" aGuardar={aGuardar} aoMudar={mudar}>
                Não precisa de intervenção
              </BotaoEstado>
            </>
          ) : (
            <BotaoEstado estado="aberto" Icone={RotateCcw} classe="botao-g--secundario" aGuardar={aGuardar} aoMudar={mudar}>
              Reabrir
            </BotaoEstado>
          )}
        </div>
        <p className="campo-g__ajuda">Quem reportou recebe uma notificação a cada mudança de estado.</p>
      </section>

      <h3 className="seguimento__titulo">Histórico</h3>
      <LinhaDoTempo eventos={reporte.eventos} />
    </article>
  );
}
