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

export function Foto({ observacao }) {
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
        {imagem.fonte === "upload" || imagem.fonte === "video" ? `${fonte}` : `Foto de ${imagem.autor} no ${fonte}`}
        {imagem.capturada_em ? `, ${formatarData(imagem.capturada_em)}` : ""}. {imagem.licenca}.
        {imagem.url_origem && (
          <>
            {" "}
            <a href={imagem.url_origem} target="_blank" rel="noopener noreferrer">
              Ver original
            </a>
          </>
        )}
      </figcaption>
    </figure>
  );
}

export default function Fotos({ config, selecionadoId, detalhe, aoAvaliar, aoRepetir }) {
  const titulo= useRef(null);
  const p= detalhe.estado === "ok" ? detalhe.dados.properties : null;

  useEffect(() => {
    if (selecionadoId !== null) titulo.current?.focus({ preventScroll: true });
  }, [selecionadoId]);

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
        <div>
          <h2 id="titulo-fotos" className="painel__titulo" ref={titulo} tabIndex={-1}>
            {p ? rotuloClasse(config, p.categoria, p.classe) : "Elemento"}
          </h2>
          {p && (
            <p className="fotos__sub">
              {rotuloCategoria(config, p.categoria)}, {rotuloEstado(p.estado)}, confiança {percentagem(p.confianca)},{" "}
              {p.n_observacoes} {p.n_observacoes === 1 ? "fotografia" : "fotografias"}
            </p>
          )}
          {p && p.metodo_geo === "sem_posicao" && (
            <p className="fotos__sub">Posição indisponível: a fotografia não tem GPS.</p>
          )}
          {p && p.metodo_geo !== "sem_posicao" && (
            <p className="fotos__sub">Posição obtida por: {METODOS[p.metodo_geo] ?? p.metodo_geo}</p>
          )}
        </div>
        <button type="button" className="botao botao--principal" disabled={!p} onClick={aoAvaliar}>
          Avaliar
        </button>
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
      {p && p.observacoes.length === 0 && <p className="nota">Este elemento não tem fotografias registadas.</p>}
      {p && (
        <div className="fotos__lista">
          {p.observacoes.map((observacao) => (
            <Foto key={observacao.id} observacao={observacao} />
          ))}
        </div>
      )}
    </section>
  );
}
