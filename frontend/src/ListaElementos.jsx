import { percentagem, rotuloCategoria, rotuloClasse, rotuloEstado } from "./rotulos.js";
import Simbolo from "./Simbolo.jsx";

const LIMITE= 300;

function Legenda({ config }) {
  const sinais= config.categorias.sinal?.classes ?? [];
  return (
    <details className="legenda">
      <summary>Legenda do mapa</summary>
      <ul className="legenda__lista">
        {config.categorias.iluminacao && (
          <li>
            <Simbolo categoria="iluminacao" classe="luz" />
            {rotuloCategoria(config, "iluminacao")}: lâmpada
          </li>
        )}
        {config.categorias.residuos && (
          <li>
            <Simbolo categoria="residuos" classe="contentor" />
            {rotuloCategoria(config, "residuos")}: caixote do lixo
          </li>
        )}
        {sinais.map((classe) => (
          <li key={classe.id}>
            <Simbolo categoria="sinal" classe={classe.id} />
            {classe.rotulo}
          </li>
        ))}
        <li>
          <Simbolo categoria="iluminacao" classe="luz" estado="validado" />
          Selo verde: validado
        </li>
        <li>
          <Simbolo categoria="iluminacao" classe="luz" estado="corrigido" />
          Selo laranja com barra: corrigido
        </li>
        <li>
          <Simbolo categoria="iluminacao" classe="luz" estado="rejeitado" />
          Esbatido e tracejado: rejeitado
        </li>
        <li>Sem posição: só aparece na lista, não no mapa</li>
      </ul>
    </details>
  );
}

function Estado({ lista, aoRepetir, aoLimpar, temFiltros, vazia }) {
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
    return <p className="mensagem">{vazia}</p>;
  }
  return null;
}

export default function ListaElementos({
  config,
  lista,
  selecionadoId,
  temFiltros,
  vazia,
  aoSelecionar,
  aoRepetir,
  aoLimpar,
  semTitulo= false,
}) {
  const visiveis= lista.features.slice(0, LIMITE);
  return (
    <section className="lista" aria-labelledby="titulo-lista">
      {!semTitulo && (
        <h2 id="titulo-lista" className="painel__titulo">
          Elementos
          {lista.estado === "ok" && <span className="painel__contagem"> ({lista.features.length})</span>}
        </h2>
      )}
      <Estado lista={lista} aoRepetir={aoRepetir} aoLimpar={aoLimpar} temFiltros={temFiltros} vazia={vazia} />
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
                  <Simbolo categoria={p.categoria} classe={p.classe} estado={p.estado} />
                  <span className="item__texto">
                    <span className="item__nome">{rotuloClasse(config, p.categoria, p.classe)}</span>
                    <span className="item__meta">
                      n.º {p.id}, {rotuloEstado(p.estado)}, confiança {percentagem(p.confianca)}
                      {p.obstruido ? ", tapado" : ""}
                      {feature.geometry ? "" : ", sem posição"}
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
