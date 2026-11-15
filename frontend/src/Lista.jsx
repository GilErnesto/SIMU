import { indiceCategoria, percentagem, rotuloCategoria, rotuloClasse, rotuloEstado } from "./rotulos.js";

const LIMITE= 300;

function Legenda({ config }) {
  const categorias= Object.keys(config.categorias);
  return (
    <details className="legenda">
      <summary>Legenda do mapa</summary>
      <ul className="legenda__lista">
        {categorias.map((nome) => (
          <li key={nome}>
            <span className={`pino pino--legenda pino--c${indiceCategoria(config, nome)} pino--auto`} aria-hidden="true" />
            {rotuloCategoria(config, nome)}
          </li>
        ))}
        <li>
          <span className="pino pino--legenda pino--c0 pino--rejeitado" aria-hidden="true" />
          Contorno tracejado: rejeitado
        </li>
        <li>
          <span className="pino pino--legenda pino--c0 pino--validado" aria-hidden="true" />
          Centro branco: validado
        </li>
        <li>
          <span className="pino pino--legenda pino--c0 pino--corrigido" aria-hidden="true" />
          Barra branca: corrigido
        </li>
      </ul>
    </details>
  );
}

function Estado({ lista, aoRepetir, aoLimpar, temFiltros }) {
  if (lista.estado === "a-carregar") {
    return <p className="mensagem">A carregar elementos.</p>;
  }
  if (lista.estado === "erro") {
    return (
      <div className="mensagem mensagem--erro" role="alert">
        <p>{lista.erro}</p>
        <button type="button" className="botao" onClick={aoRepetir}>
          Tentar de novo
        </button>
      </div>
    );
  }
  if (lista.features.length === 0 && temFiltros) {
    return (
      <div className="mensagem">
        <p>Nenhum elemento corresponde a estes filtros.</p>
        <button type="button" className="botao" onClick={aoLimpar}>
          Limpar filtros
        </button>
      </div>
    );
  }
  if (lista.features.length === 0) {
    return (
      <div className="mensagem">
        <p>O catálogo está vazio.</p>
        <p>
          Corra <code>python -m pipeline.run --municipio config/municipio.yaml</code> para o preencher.
        </p>
      </div>
    );
  }
  return null;
}

export default function Lista({ config, lista, selecionadoId, temFiltros, aoSelecionar, aoRepetir, aoLimpar }) {
  const visiveis= lista.features.slice(0, LIMITE);
  return (
    <section className="lista" aria-labelledby="titulo-lista" id="lista">
      <h2 id="titulo-lista" className="painel__titulo">
        Elementos
        {lista.estado === "ok" && <span className="painel__contagem"> ({lista.features.length})</span>}
      </h2>
      <Estado lista={lista} aoRepetir={aoRepetir} aoLimpar={aoLimpar} temFiltros={temFiltros} />
      {lista.estado === "ok" && visiveis.length > 0 && (
        <ul className="lista__itens">
          {visiveis.map((feature) => {
            const p= feature.properties;
            const ativo= p.id === selecionadoId;
            return (
              <li key={p.id}>
                <button
                  type="button"
                  className="item"
                  aria-current={ativo ? "true" : undefined}
                  onClick={() => aoSelecionar(p.id, "lista")}
                >
                  <span className={`pino pino--legenda pino--c${indiceCategoria(config, p.categoria)} pino--${p.estado}`} aria-hidden="true" />
                  <span className="item__texto">
                    <span className="item__nome">{rotuloClasse(config, p.categoria, p.classe)}</span>
                    <span className="item__meta">
                      {rotuloEstado(p.estado)}, confiança {percentagem(p.confianca)}
                      {p.obstruido ? ", tapado" : ""}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {lista.estado === "ok" && lista.features.length > LIMITE && (
        <p className="mensagem">
          A mostrar os primeiros {LIMITE} de {lista.features.length}. Use os filtros para ver os restantes.
        </p>
      )}
      <Legenda config={config} />
    </section>
  );
}
