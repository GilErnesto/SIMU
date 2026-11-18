import { useEffect, useRef, useState } from "react";

import { obterElemento } from "./api.js";
import { Foto } from "./Fotos.jsx";
import { percentagem, rotuloClasse } from "./rotulos.js";

const FOTOS_POR_LADO= 2;

function chaveDe(par) {
  return `${par.a}-${par.b}`;
}

function textoParecer(par) {
  return par.fotos_em_comum > 0
    ? "Aparecem na mesma fotografia: provavelmente são dois elementos."
    : "Nenhuma fotografia em comum: provavelmente é o mesmo elemento.";
}

function formatarMetros(valor) {
  return `${valor.toFixed(1).replace(".", ",")} m`;
}

function Lado({ config, id, rotulo, aoCarregar }) {
  const [estado, setEstado]= useState({ fase: "a-carregar" });

  useEffect(() => {
    const controlo= new AbortController();
    setEstado({ fase: "a-carregar" });
    obterElemento(id, controlo.signal)
      .then((dados) => {
        setEstado({ fase: "ok", dados });
        aoCarregar(id, dados.properties);
      })
      .catch((erro) => {
        if (erro.name !== "AbortError") setEstado({ fase: "erro", texto: erro.message });
      });
    return () => controlo.abort();
  }, [id]);

  if (estado.fase === "a-carregar") return <div className="duplicados__lado"><p className="mensagem">A carregar o elemento {rotulo}.</p></div>;
  if (estado.fase === "erro") {
    return (
      <div className="duplicados__lado">
        <p className="mensagem mensagem--erro" role="alert">{estado.texto}</p>
      </div>
    );
  }
  const p= estado.dados.properties;
  return (
    <div className="duplicados__lado">
      <h3 className="bloco__titulo">
        Elemento {rotulo}: {rotuloClasse(config, p.categoria, p.classe)}
      </h3>
      <p className="nota">
        Confiança {percentagem(p.confianca)}, {p.n_observacoes} {p.n_observacoes === 1 ? "fotografia" : "fotografias"}.
      </p>
      {p.observacoes.slice(0, FOTOS_POR_LADO).map((observacao) => (
        <Foto key={observacao.id} observacao={observacao} />
      ))}
      {p.observacoes.length > FOTOS_POR_LADO && (
        <p className="nota">Mais {p.observacoes.length - FOTOS_POR_LADO} fotografias no painel de fotografias.</p>
      )}
    </div>
  );
}

export default function Duplicados({ config, estado, pares, dispensados, tecnico, aoMudarTecnico, aoJuntar, aoDispensar, aoVerNoMapa, aoRepetir, aoFechar }) {
  const titulo= useRef(null);
  const [escolhido, setEscolhido]= useState(null);
  const [detalhes, setDetalhes]= useState({});
  const [aConfirmar, setAConfirmar]= useState(false);
  const [aGuardar, setAGuardar]= useState(false);
  const [mensagem, setMensagem]= useState(null);
  const visiveis= pares.filter((par) => !dispensados.has(chaveDe(par)));
  const par= visiveis.find((candidato) => chaveDe(candidato) === escolhido) ?? null;

  useEffect(() => {
    titulo.current?.focus();
  }, []);

  useEffect(() => {
    setAConfirmar(false);
  }, [escolhido]);

  useEffect(() => {
    if (escolhido === null && visiveis.length > 0) setEscolhido(chaveDe(visiveis[0]));
    if (escolhido !== null && !par) setEscolhido(visiveis.length > 0 ? chaveDe(visiveis[0]) : null);
  }, [pares, dispensados]);

  function registar(id, propriedades) {
    setDetalhes((anteriores) => ({ ...anteriores, [id]: propriedades }));
  }

  function destinoOrigem() {
    const a= detalhes[par.a];
    const b= detalhes[par.b];
    if (a && b && b.n_observacoes > a.n_observacoes) return [par.b, par.a];
    return [par.a, par.b];
  }

  async function confirmar() {
    if (!tecnico.trim()) {
      setMensagem({ tipo: "erro", texto: "Indique o seu nome antes de juntar." });
      setAConfirmar(false);
      return;
    }
    const [destino, origem]= destinoOrigem();
    setAGuardar(true);
    setMensagem(null);
    try {
      await aoJuntar(destino, origem, tecnico.trim());
      setMensagem({ tipo: "ok", texto: `Elementos juntados no elemento ${destino}.` });
    } catch (erro) {
      setMensagem({ tipo: "erro", texto: erro.message });
    } finally {
      setAGuardar(false);
      setAConfirmar(false);
    }
  }

  return (
    <aside className="duplicados" role="dialog" aria-modal="true" aria-labelledby="titulo-duplicados">
      <div className="duplicados__cabeca">
        <h2 id="titulo-duplicados" className="painel__titulo" ref={titulo} tabIndex={-1}>
          Possíveis duplicados ({visiveis.length})
        </h2>
        <button type="button" className="botao botao--secundario" onClick={aoFechar}>
          Fechar
        </button>
      </div>
      <p className="nota">
        Pares de elementos da mesma categoria a poucos metros um do outro. Compare as fotografias e decida: juntar não
        apaga nada, o elemento juntado fica rejeitado e a decisão fica no histórico.
      </p>
      <div className="campo duplicados__nome">
        <label htmlFor="tecnico-duplicados">O seu nome</label>
        <input id="tecnico-duplicados" autoComplete="name" value={tecnico} onChange={(e) => aoMudarTecnico(e.target.value)} />
      </div>

      {estado === "a-carregar" && <p className="mensagem">A procurar duplicados.</p>}
      {estado === "erro" && (
        <div className="mensagem mensagem--erro" role="alert">
          <p>Não foi possível obter os duplicados.</p>
          <button type="button" className="botao" onClick={aoRepetir}>
            Tentar de novo
          </button>
        </div>
      )}
      {estado === "ok" && visiveis.length === 0 && (
        <p className="mensagem">
          {pares.length === 0 ? "Não há elementos suspeitos de estarem duplicados." : "Já decidiu todos os pares."}
        </p>
      )}

      {estado === "ok" && visiveis.length > 0 && (
        <div className="duplicados__corpo">
          <ol className="duplicados__lista" aria-label="Pares suspeitos">
            {visiveis.map((candidato) => (
              <li key={chaveDe(candidato)}>
                <button
                  type="button"
                  className="duplicados__par"
                  aria-current={chaveDe(candidato) === escolhido}
                  onClick={() => setEscolhido(chaveDe(candidato))}
                >
                  <span>
                    {rotuloClasse(config, candidato.categoria, candidato.classe_a)} {candidato.a} e {candidato.b}
                  </span>
                  <span className="nota">
                    a {formatarMetros(candidato.distancia_m)}, {candidato.fotos_em_comum > 0 ? "na mesma fotografia" : "sem fotografia comum"}
                  </span>
                </button>
              </li>
            ))}
          </ol>

          {par && (
            <section className="duplicados__comparar" aria-labelledby="titulo-comparar">
              <h3 id="titulo-comparar" className="bloco__titulo">
                A {formatarMetros(par.distancia_m)} de distância
              </h3>
              <p className={par.fotos_em_comum > 0 ? "aviso" : "nota"}>{textoParecer(par)}</p>
              <div className="acoes">
                {!aConfirmar && (
                  <button type="button" className="botao botao--principal" disabled={aGuardar} onClick={() => setAConfirmar(true)}>
                    São o mesmo: juntar
                  </button>
                )}
                {aConfirmar && (
                  <>
                    <button type="button" className="botao botao--perigo" disabled={aGuardar} onClick={confirmar}>
                      Confirmar: juntar no elemento com mais fotografias
                    </button>
                    <button type="button" className="botao botao--secundario" disabled={aGuardar} onClick={() => setAConfirmar(false)}>
                      Cancelar
                    </button>
                  </>
                )}
                <button type="button" className="botao" disabled={aGuardar} onClick={() => aoDispensar(par)}>
                  São diferentes
                </button>
                <button type="button" className="botao botao--secundario" onClick={() => aoVerNoMapa(par)}>
                  Ver no mapa
                </button>
              </div>
              <div className="estado-guardar" role={mensagem?.tipo === "erro" ? "alert" : "status"}>
                {mensagem && <p className={mensagem.tipo === "erro" ? "mensagem--erro" : "mensagem--ok"}>{mensagem.texto}</p>}
              </div>
              <div className="duplicados__lados">
                <Lado key={`a-${par.a}`} config={config} id={par.a} rotulo={String(par.a)} aoCarregar={registar} />
                <Lado key={`b-${par.b}`} config={config} id={par.b} rotulo={String(par.b)} aoCarregar={registar} />
              </div>
            </section>
          )}
        </div>
      )}
    </aside>
  );
}
