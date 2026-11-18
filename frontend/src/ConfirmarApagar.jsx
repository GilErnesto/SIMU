import { useEffect, useRef, useState } from "react";

import { apagarAnalise } from "./api.js";

function contar(n, singular, plural) {
  return `${n} ${n === 1 ? singular : plural}`;
}

export default function ConfirmarApagar({ analise, aoCancelar, aoApagar }) {
  const dialogo= useRef(null);
  const [estado, setEstado]= useState({ fase: "confirmar" });
  const aApagar= estado.fase === "a-apagar";

  useEffect(() => {
    const no= dialogo.current;
    if (no && !no.open) no.showModal();
    return () => {
      if (no?.open) no.close();
    };
  }, []);

  async function confirmar() {
    setEstado({ fase: "a-apagar" });
    try {
      aoApagar(await apagarAnalise(analise.token));
    } catch (erro) {
      setEstado({ fase: "erro", erro: erro.message });
    }
  }

  return (
    <dialog
      ref={dialogo}
      className="dialogo"
      aria-labelledby="titulo-apagar"
      aria-describedby="texto-apagar"
      onCancel={(evento) => {
        evento.preventDefault();
        if (!aApagar) aoCancelar();
      }}
    >
      <h2 id="titulo-apagar" className="dialogo__titulo">
        Apagar a análise «{analise.nome}»?
      </h2>
      <p id="texto-apagar" className="dialogo__texto">
        Isto apaga {contar(analise.n_elementos, "elemento", "elementos")} e {contar(analise.total, "imagem", "imagens")},
        as correções feitas pelo técnico e as fotografias anonimizadas guardadas no servidor. Não dá para desfazer.
      </p>
      {estado.fase === "erro" && (
        <p className="mensagem mensagem--erro" role="alert">
          {estado.erro}
        </p>
      )}
      <div className="dialogo__acoes">
        <button type="button" className="botao" autoFocus onClick={aoCancelar} disabled={aApagar}>
          Cancelar
        </button>
        <button type="button" className="botao botao--perigo" onClick={confirmar} disabled={aApagar}>
          {aApagar ? "A apagar a análise." : estado.fase === "erro" ? "Tentar apagar de novo" : "Apagar análise"}
        </button>
      </div>
    </dialog>
  );
}
