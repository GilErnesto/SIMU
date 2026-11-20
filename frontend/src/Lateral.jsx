import { useEffect, useState } from "react";

import Filtros, { contarFiltros } from "./Filtros.jsx";
import { IconeDuplicados, IconeFiltro, IconeSetaDireita, IconeSetaEsquerda } from "./icones.jsx";
import ListaElementos from "./ListaElementos.jsx";

function useLargo() {
  const [largo, setLargo]= useState(() => window.matchMedia("(min-width: 700px)").matches);
  useEffect(() => {
    const consulta= window.matchMedia("(min-width: 700px)");
    const atualizar= () => setLargo(consulta.matches);
    consulta.addEventListener("change", atualizar);
    return () => consulta.removeEventListener("change", atualizar);
  }, []);
  return largo;
}

function Selo({ valor }) {
  if (!valor) return null;
  return (
    <span className="selo" aria-hidden="true">
      {valor}
    </span>
  );
}

export default function Lateral({
  config,
  lista,
  selecionadoId,
  filtros,
  filtrosAbertos,
  totalAnalise,
  pares,
  fechada,
  vazia,
  aoAlternar,
  aoAlternarFiltros,
  aoMudarFiltros,
  aoLimparFiltros,
  aoAbrirDuplicados,
  aoSelecionar,
  aoRepetir,
}) {
  const largo= useLargo();
  const ativos= contarFiltros(filtros);
  const rotuloFiltros= ativos > 0 ? `Filtros, ${ativos} ${ativos === 1 ? "ativo" : "ativos"}` : "Filtros";
  const rotuloDuplicados= `Possíveis duplicados, ${pares}`;

  if (fechada && largo) {
    return (
      <aside className="lateral lateral--fechada" id="lateral" aria-label="Elementos">
        <button type="button" className="botao botao--icone" aria-label="Mostrar a lista de elementos" aria-expanded="false" title="Mostrar a lista" onClick={aoAlternar}>
          <IconeSetaDireita />
        </button>
        <button type="button" className="botao botao--icone botao--selo" aria-label={rotuloFiltros} title="Filtros" onClick={() => aoAlternarFiltros(true)}>
          <IconeFiltro />
          <Selo valor={ativos} />
        </button>
        <button type="button" className="botao botao--icone botao--selo" aria-label={rotuloDuplicados} title="Possíveis duplicados" onClick={aoAbrirDuplicados}>
          <IconeDuplicados />
          <Selo valor={pares} />
        </button>
        <p className="lateral__contagem" aria-label={`${lista.features.length} elementos`} title={`${lista.features.length} elementos`}>
          {lista.features.length}
        </p>
      </aside>
    );
  }

  return (
    <aside className="lateral" id="lateral" aria-label="Elementos">
      <div className="lateral__cabeca">
        <h2 id="titulo-lista" className="painel__titulo">
          Elementos
          {lista.estado === "ok" && <span className="painel__contagem"> ({lista.features.length})</span>}
        </h2>
        <button
          type="button"
          className="botao botao--icone botao--selo"
          aria-label={rotuloFiltros}
          aria-expanded={filtrosAbertos}
          aria-controls="painel-filtros"
          title="Filtros"
          onClick={() => aoAlternarFiltros()}
        >
          <IconeFiltro />
          <Selo valor={ativos} />
        </button>
        <button type="button" className="botao botao--icone lateral__recolher" aria-label="Recolher a lista" title="Recolher a lista" onClick={aoAlternar}>
          <IconeSetaEsquerda />
        </button>
      </div>
      {filtrosAbertos && (
        <Filtros
          compacto
          config={config}
          filtros={filtros}
          mostrados={lista.features.length}
          total={totalAnalise}
          aoMudar={aoMudarFiltros}
          aoLimpar={aoLimparFiltros}
        />
      )}
      <button type="button" className="lateral__duplicados" onClick={aoAbrirDuplicados}>
        <IconeDuplicados tamanho={18} />
        <span>Possíveis duplicados</span>
        <span className="selo selo--linha">{pares}</span>
      </button>
      <ListaElementos
        semTitulo
        config={config}
        lista={lista}
        selecionadoId={selecionadoId}
        temFiltros={ativos > 0}
        vazia={vazia}
        aoSelecionar={aoSelecionar}
        aoRepetir={aoRepetir}
        aoLimpar={aoLimparFiltros}
      />
    </aside>
  );
}
