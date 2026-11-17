import { useEffect, useState } from "react";

import { listarAnalises } from "./api.js";
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

export default function ListaAnalises({ versao }) {
  const [estado, setEstado]= useState({ fase: "a-carregar", analises: [] });
  const [tentativa, setTentativa]= useState(0);

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
      <h2 id="titulo-analises" className="analises__titulo">
        As suas análises
      </h2>
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
              </div>
              <Detalhe analise={analise} />
              <p className="analise-item__data">{formatarDataHora(analise.criada_em)}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
