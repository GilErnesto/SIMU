import { useEffect, useState } from "react";

import DetalheProblema, { ABERTOS, tituloProblema } from "./DetalheProblema.jsx";
import { Etiqueta } from "./ReportesUi.jsx";

// "Problema" tab of the analysis map: the citizens' problems on the selected element, open ones first.
export default function PainelProblemas({ config, reportes, tecnico, aoMudar }) {
  const ordenados= [...reportes].sort((a, b) => Number(ABERTOS.has(b.estado)) - Number(ABERTOS.has(a.estado)));
  const [escolhido, setEscolhido]= useState(ordenados[0]?.token ?? null);

  useEffect(() => {
    if (!ordenados.some((r) => r.token === escolhido)) setEscolhido(ordenados[0]?.token ?? null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reportes]);

  if (!escolhido) return null;
  return (
    <section className="painel-problemas" aria-label="Problemas reportados neste elemento">
      {ordenados.length > 1 && (
        <div className="painel-problemas__lista" role="group" aria-label="Escolher o problema">
          {ordenados.map((r) => (
            <button
              key={r.token}
              type="button"
              className="painel-problemas__item"
              aria-pressed={r.token === escolhido}
              onClick={() => setEscolhido(r.token)}
            >
              <span>{tituloProblema(config, r)}</span>
              <Etiqueta estado={r.estado} />
            </button>
          ))}
        </div>
      )}
      <DetalheProblema key={escolhido} config={config} token={escolhido} tecnico={tecnico} aoMudar={aoMudar} comMapa={false} compacto />
    </section>
  );
}
