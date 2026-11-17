import { useEffect, useRef } from "react";

import { ESTADOS } from "./rotulos.js";

export const FILTROS_VAZIOS= { categoria: "", classe: "", estado: "", minObservacoes: "", minConfianca: "" };

export function contarFiltros(filtros) {
  return Object.values(filtros).filter(Boolean).length;
}

export default function Filtros({ config, filtros, mostrados, total, aoMudar, aoLimpar, aoFechar }) {
  const primeiro= useRef(null);
  const categorias= Object.keys(config.categorias);

  useEffect(() => {
    primeiro.current?.focus();
  }, []);

  function mudarCategoria(valor) {
    aoMudar({ categoria: valor, classe: "" });
  }

  return (
    <section id="painel-filtros" className="filtros" aria-label="Filtros">
      <div className="filtros__grelha">
        <div className="campo">
          <label htmlFor="filtro-categoria">Categoria</label>
          <select
            id="filtro-categoria"
            ref={primeiro}
            value={filtros.categoria}
            onChange={(evento) => mudarCategoria(evento.target.value)}
          >
            <option value="">Todas</option>
            {categorias.map((nome) => (
              <option key={nome} value={nome}>
                {config.categorias[nome].rotulo}
              </option>
            ))}
          </select>
        </div>
        <div className="campo">
          <label htmlFor="filtro-classe">Tipo</label>
          <select id="filtro-classe" value={filtros.classe} onChange={(evento) => aoMudar({ classe: evento.target.value })}>
            <option value="">Todos</option>
            {categorias
              .filter((nome) => !filtros.categoria || nome === filtros.categoria)
              .map((nome) => (
                <optgroup key={nome} label={config.categorias[nome].rotulo}>
                  {config.categorias[nome].classes.map((classe) => (
                    <option key={classe.id} value={classe.id}>
                      {classe.rotulo}
                    </option>
                  ))}
                </optgroup>
              ))}
          </select>
        </div>
        <div className="campo">
          <label htmlFor="filtro-estado">Estado</label>
          <select id="filtro-estado" value={filtros.estado} onChange={(evento) => aoMudar({ estado: evento.target.value })}>
            <option value="">Todos</option>
            {config.estados.map((estado) => (
              <option key={estado} value={estado}>
                {ESTADOS[estado] ?? estado}
              </option>
            ))}
          </select>
        </div>
        <div className="campo">
          <label htmlFor="filtro-observacoes">Fotografias em que aparece</label>
          <select
            id="filtro-observacoes"
            value={filtros.minObservacoes}
            onChange={(evento) => aoMudar({ minObservacoes: evento.target.value })}
          >
            <option value="">Qualquer número</option>
            <option value="2">2 ou mais</option>
            <option value="3">3 ou mais</option>
            <option value="5">5 ou mais</option>
          </select>
        </div>
        <div className="campo">
          <label htmlFor="filtro-confianca">Confiança</label>
          <select
            id="filtro-confianca"
            value={filtros.minConfianca}
            onChange={(evento) => aoMudar({ minConfianca: evento.target.value })}
          >
            <option value="">Qualquer</option>
            <option value="0.3">30% ou mais</option>
            <option value="0.4">40% ou mais</option>
            <option value="0.5">50% ou mais</option>
            <option value="0.6">60% ou mais</option>
          </select>
        </div>
      </div>
      <div className="filtros__rodape">
        <p className="filtros__resumo" role="status">
          A mostrar {mostrados} de {total} elementos.
        </p>
        <div className="acoes">
          <button type="button" className="botao botao--secundario" onClick={aoLimpar}>
            Limpar filtros
          </button>
          <button type="button" className="botao" onClick={aoFechar}>
            Fechar
          </button>
        </div>
      </div>
    </section>
  );
}
