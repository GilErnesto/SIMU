import { useEffect, useRef, useState } from "react";

import { IconeAviso } from "./icones.jsx";

export default function ChipAvisos({ avisos }) {
  const [aberto, setAberto]= useState(false);
  const raiz= useRef(null);

  useEffect(() => {
    if (!aberto) return undefined;
    function aoClicarFora(evento) {
      if (raiz.current && !raiz.current.contains(evento.target)) setAberto(false);
    }
    document.addEventListener("pointerdown", aoClicarFora);
    return () => document.removeEventListener("pointerdown", aoClicarFora);
  }, [aberto]);

  if (!avisos || avisos.length === 0) return null;
  const semGps= avisos.some((aviso) => aviso.includes("GPS indisponível"));
  const texto= `${avisos.length} ${avisos.length === 1 ? "aviso" : "avisos"}`;

  function aoPremir(evento) {
    if (evento.key === "Escape" && aberto) {
      evento.stopPropagation();
      setAberto(false);
      raiz.current?.querySelector("button")?.focus();
    }
  }

  return (
    <div className="menu" ref={raiz} onKeyDown={aoPremir}>
      <button
        type="button"
        className={semGps ? "chip chip--gps" : "chip"}
        aria-expanded={aberto}
        aria-controls="lista-avisos"
        onClick={() => setAberto((valor) => !valor)}
      >
        <IconeAviso tamanho={18} />
        {texto}
      </button>
      {aberto && (
        <div id="lista-avisos" className="flutuante flutuante--direita flutuante--larga">
          <p className="flutuante__titulo">Avisos desta análise</p>
          <ul className="avisos__lista">
            {avisos.map((aviso) => (
              <li key={aviso}>{aviso}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
