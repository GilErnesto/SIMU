import { useEffect, useRef, useState } from "react";

import {
  FONTES,
  METODOS,
  formatarData,
  lerNumero,
  percentagem,
  rotuloCategoria,
  rotuloClasse,
  rotuloEstado,
} from "./rotulos.js";

function Foto({ observacao }) {
  const [tamanho, setTamanho]= useState(null);
  const [falhou, setFalhou]= useState(false);
  const { imagem, bbox }= observacao;
  const fonte= FONTES[imagem.fonte] ?? imagem.fonte;
  const caixa= bbox && bbox.length === 4 ? bbox : null;

  return (
    <figure className="foto">
      {imagem.url && !falhou ? (
        <div className="foto__caixa">
          <img
            src={`/api${imagem.url}`}
            alt="Imagem de rua anonimizada, com o elemento assinalado por um retângulo"
            loading="lazy"
            onLoad={(evento) =>
              setTamanho({ w: evento.currentTarget.naturalWidth, h: evento.currentTarget.naturalHeight })
            }
            onError={() => setFalhou(true)}
          />
          {tamanho && caixa && (
            <svg viewBox={`0 0 ${tamanho.w} ${tamanho.h}`} preserveAspectRatio="none" aria-hidden="true">
              <rect className="foto__moldura-fora" x={caixa[0]} y={caixa[1]} width={caixa[2] - caixa[0]} height={caixa[3] - caixa[1]} />
              <rect className="foto__moldura" x={caixa[0]} y={caixa[1]} width={caixa[2] - caixa[0]} height={caixa[3] - caixa[1]} />
            </svg>
          )}
        </div>
      ) : (
        <p className="foto__falta">Imagem não disponível.</p>
      )}
      <figcaption>
        Foto de {imagem.autor} no {fonte}, {formatarData(imagem.capturada_em)}. Licença {imagem.licenca}.{" "}
        <a href={imagem.url_origem} target="_blank" rel="noopener noreferrer">
          Ver original
        </a>
      </figcaption>
    </figure>
  );
}

function aoFocar(evento) {
  evento.currentTarget.scrollIntoView({ block: "center" });
}

export default function Detalhe({
  config,
  selecionadoId,
  detalhe,
  tecnico,
  modoMover,
  candidata,
  aoFechar,
  aoRepetir,
  aoGuardar,
  aoAlternarMover,
  aoMudarCandidata,
}) {
  const titulo= useRef(null);
  const [escolhida, setEscolhida]= useState(null);
  const [aGuardar, setAGuardar]= useState(false);
  const [mensagem, setMensagem]= useState(null);
  const dados= detalhe.estado === "ok" ? detalhe.dados : null;
  const p= dados?.properties;
  const classe= escolhida ?? p?.classe ?? "";

  useEffect(() => {
    if (selecionadoId !== null) titulo.current?.focus();
    setMensagem(null);
    setEscolhida(null);
  }, [selecionadoId]);

  async function executar(corpo) {
    if (!tecnico.trim()) {
      setMensagem({ tipo: "erro", texto: "Indique o seu nome no campo Técnico antes de guardar." });
      return;
    }
    setAGuardar(true);
    setMensagem(null);
    try {
      await aoGuardar({ ...corpo, autor: tecnico.trim() });
      setEscolhida(null);
      setMensagem({ tipo: "ok", texto: "Alteração guardada." });
    } catch (erro) {
      setMensagem({ tipo: "erro", texto: erro.message });
    } finally {
      setAGuardar(false);
    }
  }

  function guardarPosicao() {
    const lat= lerNumero(candidata?.lat ?? "");
    const lon= lerNumero(candidata?.lon ?? "");
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
      setMensagem({ tipo: "erro", texto: "Indique uma latitude e uma longitude válidas." });
      return;
    }
    executar({ lat, lon });
  }

  if (selecionadoId === null) {
    return (
      <aside className="detalhe detalhe--vazio" aria-labelledby="titulo-detalhe">
        <h2 id="titulo-detalhe" className="painel__titulo">
          Revisão
        </h2>
        <p className="mensagem">Escolha um elemento no mapa ou na lista para ver as imagens, a origem e rever.</p>
      </aside>
    );
  }

  const [lon, lat]= dados ? dados.geometry.coordinates : [null, null];
  const classes= dados ? (config.categorias[p.categoria]?.classes ?? []) : [];
  const campoLat= candidata ? candidata.lat : lat !== null ? String(lat) : "";
  const campoLon= candidata ? candidata.lon : lon !== null ? String(lon) : "";

  return (
    <aside className="detalhe" aria-labelledby="titulo-detalhe">
      <div className="detalhe__cabeca">
        <h2 id="titulo-detalhe" className="painel__titulo" ref={titulo} tabIndex={-1}>
          {p ? rotuloClasse(config, p.categoria, p.classe) : "Elemento"}
        </h2>
        <button type="button" className="botao botao--secundario" onClick={aoFechar}>
          Fechar
        </button>
      </div>

      {detalhe.estado === "a-carregar" && <p className="mensagem">A carregar elemento.</p>}
      {detalhe.estado === "erro" && (
        <div className="mensagem mensagem--erro" role="alert">
          <p>{detalhe.erro}</p>
          <button type="button" className="botao" onClick={aoRepetir}>
            Tentar de novo
          </button>
        </div>
      )}

      {p && (
        <>
          <dl className="factos">
            <div>
              <dt>Categoria</dt>
              <dd>{rotuloCategoria(config, p.categoria)}</dd>
            </div>
            <div>
              <dt>Estado</dt>
              <dd>{rotuloEstado(p.estado)}</dd>
            </div>
            <div>
              <dt>Confiança</dt>
              <dd>{percentagem(p.confianca)}</dd>
            </div>
            <div>
              <dt>Observações</dt>
              <dd>{p.n_observacoes}</dd>
            </div>
            <div>
              <dt>Posição obtida por</dt>
              <dd>{METODOS[p.metodo_geo] ?? p.metodo_geo}</dd>
            </div>
          </dl>
          {p.obstruido && (
            <p className="aviso">Sinal tapado ou vandalizado. Confirme a classe antes de validar.</p>
          )}

          <section className="bloco" aria-labelledby="titulo-estado">
            <h3 id="titulo-estado" className="bloco__titulo">
              Decisão
            </h3>
            <div className="acoes">
              <button type="button" className="botao botao--principal" disabled={aGuardar || p.estado === "validado"} onClick={() => executar({ estado: "validado" })}>
                Validar
              </button>
              <button type="button" className="botao" disabled={aGuardar || p.estado === "rejeitado"} onClick={() => executar({ estado: "rejeitado" })}>
                Rejeitar
              </button>
              <button type="button" className="botao botao--secundario" disabled={aGuardar || p.estado === "auto"} onClick={() => executar({ estado: "auto" })}>
                Voltar a por rever
              </button>
            </div>
            <p className="nota">Rejeitar não apaga o elemento: fica registado no histórico de correções.</p>
          </section>

          <section className="bloco" aria-labelledby="titulo-classe">
            <h3 id="titulo-classe" className="bloco__titulo">
              Corrigir a classe
            </h3>
            <div className="campo">
              <label htmlFor="classe">Classe</label>
              <select id="classe" value={classe} onChange={(evento) => setEscolhida(evento.target.value)} onFocus={aoFocar}>
                {classes.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.rotulo}
                  </option>
                ))}
              </select>
            </div>
            <button type="button" className="botao" disabled={aGuardar || classe === p.classe} onClick={() => executar({ classe })}>
              Guardar classe
            </button>
          </section>

          <section className="bloco" aria-labelledby="titulo-posicao">
            <h3 id="titulo-posicao" className="bloco__titulo">
              Corrigir a posição
            </h3>
            <div className="campos-par">
              <div className="campo">
                <label htmlFor="lat">Latitude</label>
                <input id="lat" inputMode="decimal" value={campoLat} onFocus={aoFocar} onChange={(evento) => aoMudarCandidata({ lat: evento.target.value, lon: campoLon })} />
              </div>
              <div className="campo">
                <label htmlFor="lon">Longitude</label>
                <input id="lon" inputMode="decimal" value={campoLon} onFocus={aoFocar} onChange={(evento) => aoMudarCandidata({ lat: campoLat, lon: evento.target.value })} />
              </div>
            </div>
            <div className="acoes">
              <button type="button" className="botao" aria-pressed={modoMover} onClick={aoAlternarMover}>
                {modoMover ? "A escolher no mapa: clique para parar" : "Escolher no mapa"}
              </button>
              <button type="button" className="botao" disabled={aGuardar || !candidata} onClick={guardarPosicao}>
                Guardar posição
              </button>
            </div>
          </section>

          <div className="estado-guardar" role={mensagem?.tipo === "erro" ? "alert" : "status"}>
            {mensagem && <p className={mensagem.tipo === "erro" ? "mensagem--erro" : "mensagem--ok"}>{mensagem.texto}</p>}
          </div>

          <section className="bloco" aria-labelledby="titulo-obs">
            <h3 id="titulo-obs" className="bloco__titulo">
              Imagens de origem
            </h3>
            {p.observacoes.length === 0 && <p className="nota">Este elemento não tem observações registadas.</p>}
            {p.observacoes.map((observacao) => (
              <Foto key={observacao.id} observacao={observacao} />
            ))}
          </section>
        </>
      )}
    </aside>
  );
}
