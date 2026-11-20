import { Camera, CircleCheck, CircleHelp, CircleX, Lightbulb, RotateCcw, Send, Signpost, Trash2, Wrench } from "lucide-react";

import { ESTADOS_REPORTE, descreverEvento, formatarDataHora } from "./rotulos.js";

// Shared pieces of the citizen-report pages: icons per category and state, status badge, timeline.

const ICONES_CATEGORIA= { sinal: Signpost, iluminacao: Lightbulb, residuos: Trash2 };

export function IconeCategoria({ categoria, ...props }) {
  const Icone= ICONES_CATEGORIA[categoria] ?? CircleHelp;
  return <Icone aria-hidden="true" {...props} />;
}

const ICONES_ESTADO= {
  rascunho: Camera,
  aberto: Send,
  em_resolucao: Wrench,
  resolvido: CircleCheck,
  rejeitado: CircleX,
};

export function IconeEstado({ estado, reaberto= false, ...props }) {
  const Icone= reaberto ? RotateCcw : (ICONES_ESTADO[estado] ?? Send);
  return <Icone aria-hidden="true" {...props} />;
}

export function Etiqueta({ estado, grande= false }) {
  return (
    <span className={`etiqueta etiqueta--${estado}${grande ? " etiqueta--grande" : ""}`}>
      <IconeEstado estado={estado} size={grande ? 16 : 14} strokeWidth={2.25} />
      {ESTADOS_REPORTE[estado] ?? estado}
    </span>
  );
}

export function formatarRelativo(texto) {
  const instante= Date.parse(texto);
  if (Number.isNaN(instante)) return "";
  const segundos= Math.max(0, (Date.now() - instante) / 1000);
  if (segundos < 60) return "agora mesmo";
  if (segundos < 3600) return `há ${Math.floor(segundos / 60)} min`;
  if (segundos < 86400) return `há ${Math.floor(segundos / 3600)} h`;
  if (segundos < 2 * 86400) return "ontem";
  if (segundos < 7 * 86400) return `há ${Math.floor(segundos / 86400)} dias`;
  return new Date(instante).toLocaleDateString("pt-PT", { day: "numeric", month: "short" });
}

export function Quando({ em }) {
  return (
    <time dateTime={em} title={formatarDataHora(em)}>
      {formatarRelativo(em)}
    </time>
  );
}

export function LinhaDoTempo({ eventos }) {
  return (
    <ol className="linha-tempo">
      {eventos.map((evento, indice) => {
        const reaberto= evento.estado === "aberto" && evento.autor !== "cidadão";
        return (
          <li key={indice} className={`linha-tempo__passo linha-tempo__passo--${reaberto ? "reaberto" : evento.estado}`}>
            <span className="linha-tempo__icone">
              <IconeEstado estado={evento.estado} reaberto={reaberto} size={16} strokeWidth={2.25} />
            </span>
            <div className="linha-tempo__texto">
              <span>{descreverEvento(evento)}</span>
              <Quando em={evento.em} />
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export function Vazio({ icone: Icone, titulo, children }) {
  return (
    <div className="vazio">
      <span className="vazio__icone">
        <Icone aria-hidden="true" size={28} />
      </span>
      <p className="vazio__titulo">{titulo}</p>
      {children && <div className="vazio__texto">{children}</div>}
    </div>
  );
}
