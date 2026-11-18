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

export function Foto({ observacao, marcada, aoMarcar }) {
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
      {aoMarcar && (
        <label className="fotos__marcar">
          <input type="checkbox" checked={!!marcada} onChange={() => aoMarcar(observacao.id)} /> Separar esta fotografia
        </label>
      )}
    </figure>
  );
}

export default function Fotos({ config, selecionadoId, detalhe, aoAvaliar, aoRepetir, tecnico, aoMudarTecnico, aoSeparar }) {
  const titulo= useRef(null);
  const [marcadas, setMarcadas]= useState(() => new Set());
  const [aConfirmar, setAConfirmar]= useState(false);
  const [mensagem, setMensagem]= useState(null);
  const p= detalhe.estado === "ok" ? detalhe.dados.properties : null;

  useEffect(() => {
    if (selecionadoId !== null) titulo.current?.focus({ preventScroll: true });
  }, [selecionadoId]);

  useEffect(() => {
    setMarcadas(new Set());
    setAConfirmar(false);
    setMensagem(null);
  }, [selecionadoId]);

  function alternarMarcada(id) {
    setMarcadas((anteriores) => {
      const proximas= new Set(anteriores);
      if (proximas.has(id)) proximas.delete(id);
      else proximas.add(id);
      return proximas;
    });
    setAConfirmar(false);
  }

  async function confirmarSeparacao() {
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
          {p.observacoes.map((observacao) =>
            p.observacoes.length > 1 ? (
              <Foto
                key={observacao.id}
                observacao={observacao}
                marcada={marcadas.has(observacao.id)}
                aoMarcar={alternarMarcada}
              />
            ) : (
              <Foto key={observacao.id} observacao={observacao} />
            ),
          )}
        </div>
      )}
      {(marcadas.size > 0 || mensagem) && (
        <div className="fotos__separar">
          {marcadas.size > 0 && (
            <>
              <p className="nota">
                Separar {marcadas.size} {marcadas.size === 1 ? "fotografia" : "fotografias"} para um novo elemento sem
                posição (depois indique a posição em Avaliar). Tem de ficar pelo menos uma fotografia neste elemento.
              </p>
              <div className="campo">
                <label htmlFor="tecnico-separar">O seu nome</label>
                <input
                  id="tecnico-separar"
                  autoComplete="name"
                  value={tecnico}
                  onChange={(evento) => aoMudarTecnico(evento.target.value)}
                />
              </div>
              <div className="acoes">
                {!aConfirmar && (
                  <button
                    type="button"
                    className="botao"
                    disabled={marcadas.size >= p.observacoes.length}
                    onClick={() => setAConfirmar(true)}
                  >
                    Separar
                  </button>
                )}
                {aConfirmar && (
                  <>
                    <button type="button" className="botao botao--perigo" onClick={confirmarSeparacao}>
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
