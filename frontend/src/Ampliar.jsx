import { useEffect, useRef } from "react";

import { Foto } from "./Fotos.jsx";
import { IconeFechar, IconeSetaDireita, IconeSetaEsquerda } from "./icones.jsx";

export default function Ampliar({ observacoes, indice, aoMudar, aoFechar }) {
  const dialogo= useRef(null);
  const total= observacoes.length;
  const observacao= observacoes[indice];

  useEffect(() => {
    const no= dialogo.current;
    if (no && !no.open) no.showModal();
    return () => {
      if (no?.open) no.close();
    };
  }, []);

  function anterior() {
    aoMudar((indice - 1 + total) % total);
  }

  function seguinte() {
    aoMudar((indice + 1) % total);
  }

  function aoPremir(evento) {
    if (total < 2) return;
    if (evento.key === "ArrowLeft") {
      evento.preventDefault();
      anterior();
    } else if (evento.key === "ArrowRight") {
      evento.preventDefault();
      seguinte();
    }
  }

  function aoClicar(evento) {
    if (evento.target === dialogo.current) aoFechar();
  }

  if (!observacao) return null;
  return (
    <dialog
      ref={dialogo}
      className="ampliar"
      aria-label={`Fotografia ${indice + 1} de ${total}`}
      onCancel={(evento) => {
        evento.preventDefault();
        aoFechar();
      }}
      onKeyDown={aoPremir}
      onClick={aoClicar}
    >
      <div className="ampliar__cabeca">
        <p className="ampliar__contagem" role="status">
          Fotografia {indice + 1} de {total}
        </p>
        <button type="button" className="botao botao--icone" aria-label="Fechar a fotografia" onClick={aoFechar} autoFocus>
          <IconeFechar />
        </button>
      </div>
      <div className="ampliar__corpo">
        {total > 1 && (
          <button type="button" className="botao botao--icone" aria-label="Fotografia anterior" onClick={anterior}>
            <IconeSetaEsquerda />
          </button>
        )}
        <div className="ampliar__foto">
          <Foto observacao={observacao} comZoom />
        </div>
        {total > 1 && (
          <button type="button" className="botao botao--icone" aria-label="Fotografia seguinte" onClick={seguinte}>
            <IconeSetaDireita />
          </button>
        )}
      </div>
    </dialog>
  );
}
