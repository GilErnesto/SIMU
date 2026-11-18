import { useEffect, useRef, useState } from "react";

import { listarAnalises } from "./api.js";
import ConfirmarApagar from "./ConfirmarApagar.jsx";
import ProgressoDaAnalise from "./ProgressoDaAnalise.jsx";
import { Ligacao } from "./rota.js";
import { ESTADOS_ANALISE, analiseEmCurso, formatarDataHora } from "./rotulos.js";

const INTERVALO_MS= 3000;

function Detalhe({ analise }) {
  if (analiseEmCurso(analise)) {
    return <ProgressoDaAnalise analise={analise} />;
  }
  if (analise.estado === "falhou") {
    return <p className="analise-item__meta mensagem--erro">{analise.erro || "A análise falhou."}</p>;
  }
  const avisos= analise.avisos.length;
  return (
    <p className="analise-item__meta">
      {analise.n_elementos} {analise.n_elementos === 1 ? "elemento" : "elementos"} em {analise.total}{" "}
      {analise.total === 1 ? "imagem" : "imagens"}
      {avisos > 0 ? `, ${avisos} ${avisos === 1 ? "aviso" : "avisos"}` : ""}
    </p>
  );
}

function BotaoApagar({ analise, aoPedir }) {
  return (
    <button
      type="button"
      className="analise-item__apagar"
      aria-label={`Apagar a análise ${analise.nome}`}
      aria-disabled={analise.estado === "a_processar" ? "true" : undefined}
      title="Apagar análise"
      onClick={() => aoPedir(analise)}
    >
      <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">
        <path
          d="M4 7h16M10 7V4h4v3M6.5 7l1 13h9l1-13M10 11v6M14 11v6"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </button>
  );
}

export default function ListaAnalises({ versao }) {
  const [estado, setEstado]= useState({ fase: "a-carregar", analises: [] });
  const [tentativa, setTentativa]= useState(0);
  const [aApagar, setAApagar]= useState(null);
  const [aviso, setAviso]= useState(null);
  const titulo= useRef(null);

  function pedirApagar(analise) {
    if (analise.estado === "a_processar") {
      setAviso({ tipo: "erro", texto: `Espere que a análise «${analise.nome}» acabe para a poder apagar.` });
      return;
    }
    setAviso(null);
    setAApagar(analise);
  }

  function aoApagar(analise, resultado) {
    setEstado((atual) => ({ ...atual, analises: atual.analises.filter((a) => a.token !== analise.token) }));
    setAApagar(null);
    const extra= resultado.ficheiros_por_apagar > 0
      ? ` ${resultado.ficheiros_por_apagar} ${resultado.ficheiros_por_apagar === 1 ? "fotografia anonimizada ficou" : "fotografias anonimizadas ficaram"} no servidor e tem de ${resultado.ficheiros_por_apagar === 1 ? "ser apagada" : "ser apagadas"} à mão em data/anon.`
      : "";
    setAviso({
      tipo: extra ? "erro" : "ok",
      texto: `Análise «${analise.nome}» apagada: ${resultado.elementos} ${resultado.elementos === 1 ? "elemento" : "elementos"} e ${resultado.imagens} ${resultado.imagens === 1 ? "imagem" : "imagens"}.${extra}`,
      moverFoco: true,
    });
  }

  useEffect(() => {
    if (aviso?.moverFoco) titulo.current?.focus();
  }, [aviso]);

  useEffect(() => {
    let parado= false;
    let temporizador;
    const controlo= new AbortController();
    async function carregar() {
      try {
        const dados= await listarAnalises(controlo.signal);
        if (parado) return;
        setEstado({ fase: "ok", analises: dados });
        if (dados.some(analiseEmCurso)) temporizador= setTimeout(carregar, INTERVALO_MS);
      } catch (erro) {
        if (erro.name === "AbortError" || parado) return;
        setEstado((atual) => ({ fase: "erro", analises: atual.analises, erro: erro.message }));
      }
    }
    carregar();
    return () => {
      parado= true;
      clearTimeout(temporizador);
      controlo.abort();
    };
  }, [versao, tentativa]);

  return (
    <section className="analises" aria-labelledby="titulo-analises">
      <h2 id="titulo-analises" className="analises__titulo" ref={titulo} tabIndex={-1}>
        As suas análises
      </h2>
      {aviso && (
        <p className={`mensagem mensagem--${aviso.tipo}`} role={aviso.tipo === "erro" ? "alert" : "status"}>
          {aviso.texto}
        </p>
      )}
      {estado.fase === "a-carregar" && <p className="mensagem">A carregar as análises.</p>}
      {estado.fase === "erro" && (
        <div className="mensagem mensagem--erro" role="alert">
          <p>{estado.erro}</p>
          <button type="button" className="botao" onClick={() => setTentativa((n) => n + 1)}>
            Tentar de novo
          </button>
        </div>
      )}
      {estado.fase === "ok" && estado.analises.length === 0 && (
        <p className="mensagem">Ainda não há análises. Largue ficheiros na zona acima para começar.</p>
      )}
      {estado.analises.length > 0 && (
        <ul className="analises__lista">
          {estado.analises.map((analise) => (
            <li key={analise.token} className="analise-item">
              <div className="analise-item__topo">
                <Ligacao para={`/a/${analise.token}`} className="analise-item__nome">
                  {analise.nome}
                </Ligacao>
                <span className={`estado estado--${analise.estado}`}>{ESTADOS_ANALISE[analise.estado]}</span>
                <BotaoApagar analise={analise} aoPedir={pedirApagar} />
              </div>
              <Detalhe analise={analise} />
              <p className="analise-item__data">{formatarDataHora(analise.criada_em)}</p>
            </li>
          ))}
        </ul>
      )}
      {aApagar && (
        <ConfirmarApagar
          analise={aApagar}
          aoCancelar={() => setAApagar(null)}
          aoApagar={(resultado) => aoApagar(aApagar, resultado)}
        />
      )}
    </section>
  );
}
