import { useEffect, useRef, useState } from "react";

import {
  FONTES,
  METODOS,
  formatarData,
  percentagem,
  rotuloCategoria,
  rotuloClasse,
  rotuloEstado,
} from "./rotulos.js";

export function legendaDe(imagem) {
  const fonte= FONTES[imagem.fonte] ?? imagem.fonte;
  const origem= imagem.fonte === "upload" || imagem.fonte === "video" ? `${fonte}` : `Foto de ${imagem.autor} no ${fonte}`;
  return `${origem}${imagem.capturada_em ? `, ${formatarData(imagem.capturada_em)}` : ""}. ${imagem.licenca}.`;
}

export function ImagemComCaixa({ observacao, descricao }) {
  const [tamanho, setTamanho]= useState(null);
  const [falhou, setFalhou]= useState(false);
  const { imagem, bbox }= observacao;
  const caixa= bbox && bbox.length === 4 ? bbox : null;
  if (!imagem.url || falhou) return <p className="foto__falta">Imagem não disponível.</p>;
  return (
    <div className="foto__caixa">
      <img
        src={`/api${imagem.url}`}
        alt={descricao ?? ""}
        loading="lazy"
        onLoad={(evento) => setTamanho({ w: evento.currentTarget.naturalWidth, h: evento.currentTarget.naturalHeight })}
        onError={() => setFalhou(true)}
      />
      {tamanho && caixa && (
        <svg viewBox={`0 0 ${tamanho.w} ${tamanho.h}`} preserveAspectRatio="none" aria-hidden="true">
          <rect className="foto__moldura-fora" x={caixa[0]} y={caixa[1]} width={caixa[2] - caixa[0]} height={caixa[3] - caixa[1]} />
          <rect className="foto__moldura" x={caixa[0]} y={caixa[1]} width={caixa[2] - caixa[0]} height={caixa[3] - caixa[1]} />
        </svg>
      )}
    </div>
  );
}

export function Foto({ observacao, marcada, aoMarcar }) {
  const { imagem }= observacao;
  return (
    <figure className="foto">
      <ImagemComCaixa observacao={observacao} descricao="Imagem de rua anonimizada, com o elemento assinalado por um retângulo" />
      <figcaption>
        {legendaDe(imagem)}
        {imagem.url_origem && (
          <>
            {" "}
            <a href={imagem.url_origem} target="_blank" rel="noopener noreferrer">
              Ver original
            </a>
          </>
        )}
      </figcaption>
      {aoMarcar && (
        <label className="fotos__marcar">
          <input type="checkbox" checked={!!marcada} onChange={() => aoMarcar(observacao.id)} />
          Separar esta fotografia
        </label>
      )}
    </figure>
  );
}

export function Miniatura({ observacao, indice, total, marcada, aoMarcar, aoAbrir }) {
  return (
    <div className="miniatura" data-marcada={!!marcada}>
      <button
        type="button"
        className="miniatura__abrir"
        aria-label={`Ampliar a fotografia ${indice + 1} de ${total}`}
        onClick={() => aoAbrir(indice)}
      >
        <ImagemComCaixa observacao={observacao} />
      </button>
      {aoMarcar && (
        <label className="miniatura__marcar">
          <input type="checkbox" checked={!!marcada} onChange={() => aoMarcar(observacao.id)} />
          Separar
        </label>
      )}
    </div>
  );
}

function Creditos({ observacoes }) {
  const origens= [...new Set(observacoes.map((o) => `${FONTES[o.imagem.fonte] ?? o.imagem.fonte}, ${o.imagem.licenca}`))];
  return (
    <details className="creditos">
      <summary>Fotografias: {origens.join("; ")}</summary>
      <ul>
        {observacoes.map((observacao, indice) => (
          <li key={observacao.id}>
            {indice + 1}. {legendaDe(observacao.imagem)}
            {observacao.imagem.url_origem && (
              <>
                {" "}
                <a href={observacao.imagem.url_origem} target="_blank" rel="noopener noreferrer">
                  Ver original
                </a>
              </>
            )}
          </li>
        ))}
      </ul>
    </details>
  );
}

export default function Fotos({ config, selecionadoId, detalhe, aoRepetir, tecnico, aoMudarTecnico, aoSeparar, aoAmpliar }) {
  const titulo= useRef(null);
  const [marcadas, setMarcadas]= useState(() => new Set());
  const [aConfirmar, setAConfirmar]= useState(false);
  const [mensagem, setMensagem]= useState(null);
  const p= detalhe.estado === "ok" ? detalhe.dados.properties : null;
  const total= p ? p.observacoes.length : 0;

  useEffect(() => {
    if (selecionadoId !== null) titulo.current?.focus({ preventScroll: true });
    setMarcadas(new Set());
    setAConfirmar(false);
    setMensagem(null);
  }, [selecionadoId]);

  function alternar(id) {
    setAConfirmar(false);
    setMarcadas((atual) => {
      const novo= new Set(atual);
      if (novo.has(id)) novo.delete(id);
      else novo.add(id);
      return novo;
    });
  }

  async function confirmar() {
    if (!tecnico.trim()) {
      setMensagem({ tipo: "erro", texto: "Indique o seu nome antes de separar." });
      setAConfirmar(false);
      return;
    }
    try {
      await aoSeparar([...marcadas], tecnico.trim());
      setMarcadas(new Set());
      setAConfirmar(false);
      setMensagem({ tipo: "ok", texto: "Fotografias separadas num novo elemento sem posição." });
    } catch (erro) {
      setAConfirmar(false);
      setMensagem({ tipo: "erro", texto: erro.message });
    }
  }

  if (selecionadoId === null) {
    return (
      <section className="fotos fotos--vazio" aria-labelledby="titulo-fotos">
        <h2 id="titulo-fotos" className="painel__titulo">
          Fotografias
        </h2>
        <p className="mensagem">Escolha um elemento na lista ou no mapa para ver as fotografias onde aparece.</p>
      </section>
    );
  }

  return (
    <section className="fotos" aria-labelledby="titulo-fotos">
      <header className="fotos__cabeca">
        <h2 id="titulo-fotos" className="painel__titulo" ref={titulo} tabIndex={-1}>
          {p ? rotuloClasse(config, p.categoria, p.classe) : "Elemento"}
        </h2>
        {p && (
          <p className="fotos__sub">
            {rotuloCategoria(config, p.categoria)}, {rotuloEstado(p.estado)}, confiança {percentagem(p.confianca)}, {total}{" "}
            {total === 1 ? "fotografia" : "fotografias"}
          </p>
        )}
        {p && p.metodo_geo === "sem_posicao" && <p className="fotos__sub">Posição indisponível: a fotografia não tem GPS.</p>}
        {p && p.metodo_geo !== "sem_posicao" && <p className="fotos__sub">Posição obtida por: {METODOS[p.metodo_geo] ?? p.metodo_geo}</p>}
      </header>

      {detalhe.estado === "a-carregar" && <p className="mensagem">A carregar o elemento.</p>}
      {detalhe.estado === "erro" && (
        <div className="mensagem mensagem--erro" role="alert">
          <p>{detalhe.erro}</p>
          <button type="button" className="botao" onClick={aoRepetir}>
            Tentar de novo
          </button>
        </div>
      )}
      {p?.obstruido && <p className="aviso">Sinal tapado ou vandalizado. Confirme o tipo antes de validar.</p>}
      {p && total === 0 && <p className="nota">Este elemento não tem fotografias registadas.</p>}
      {p && total > 0 && (
        <>
          <ul className="miniaturas" aria-label="Fotografias do elemento">
            {p.observacoes.map((observacao, indice) => (
              <li key={observacao.id}>
                <Miniatura
                  observacao={observacao}
                  indice={indice}
                  total={total}
                  marcada={marcadas.has(observacao.id)}
                  aoMarcar={total > 1 ? alternar : undefined}
                  aoAbrir={aoAmpliar}
                />
              </li>
            ))}
          </ul>
          <Creditos observacoes={p.observacoes} />
        </>
      )}

      {(marcadas.size > 0 || mensagem) && (
        <div className="fotos__separar">
          {marcadas.size > 0 && (
            <>
              <p className="nota">
                Separar {marcadas.size} {marcadas.size === 1 ? "fotografia" : "fotografias"} para um novo elemento sem posição (depois
                indique a posição em Avaliar). Tem de ficar pelo menos uma fotografia neste elemento.
              </p>
              <div className="campo">
                <label htmlFor="tecnico-separar">O seu nome</label>
                <input id="tecnico-separar" autoComplete="name" value={tecnico} onChange={(e) => aoMudarTecnico(e.target.value)} />
              </div>
              <div className="acoes">
                {!aConfirmar && (
                  <button type="button" className="botao" disabled={marcadas.size >= total} onClick={() => setAConfirmar(true)}>
                    Separar
                  </button>
                )}
                {aConfirmar && (
                  <>
                    <button type="button" className="botao botao--perigo" onClick={confirmar}>
                      Confirmar: separar
                    </button>
                    <button type="button" className="botao botao--secundario" onClick={() => setAConfirmar(false)}>
                      Cancelar
                    </button>
                  </>
                )}
              </div>
            </>
          )}
          <div className="estado-guardar" role={mensagem?.tipo === "erro" ? "alert" : "status"}>
            {mensagem && <p className={mensagem.tipo === "erro" ? "mensagem--erro" : "mensagem--ok"}>{mensagem.texto}</p>}
          </div>
        </div>
      )}
    </section>
  );
}
