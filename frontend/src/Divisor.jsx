import { useEffect, useRef, useState } from "react";

const MINIMO= 20;
const MAXIMO= 80;
const PASSO= 5;
const PADRAO= 50;

function limitar(valor) {
  return Math.min(MAXIMO, Math.max(MINIMO, Math.round(valor)));
}

export default function Divisor({ valor, aoMudar }) {
  const ref= useRef(null);
  const [aArrastar, setAArrastar]= useState(false);
  const [vertical, setVertical]= useState(true);

  useEffect(() => {
    const consulta= window.matchMedia("(min-width: 1100px)");
    const atualizar= () => setVertical(consulta.matches);
    atualizar();
    consulta.addEventListener("change", atualizar);
    return () => consulta.removeEventListener("change", atualizar);
  }, []);

  function percentagem(evento) {
    const contentor= ref.current.parentElement;
    const caixa= contentor.getBoundingClientRect();
    const fracao= vertical
      ? (caixa.right - evento.clientX) / caixa.width
      : (caixa.bottom - evento.clientY) / caixa.height;
    return limitar(fracao * 100);
  }

  function comecar(evento) {
    if (evento.button !== 0) return;
    evento.currentTarget.setPointerCapture(evento.pointerId);
    setAArrastar(true);
  }

  function mover(evento) {
    if (!aArrastar) return;
    const pct= percentagem(evento);
    ref.current.closest(".analise").style.setProperty("--fotos", `${pct}%`);
    ref.current.setAttribute("aria-valuenow", String(pct));
  }

  function terminar() {
    if (!aArrastar) return;
    setAArrastar(false);
    aoMudar(Number(ref.current.getAttribute("aria-valuenow")));
  }

  function teclar(evento) {
    const maisFotos= vertical ? "ArrowLeft" : "ArrowUp";
    const menosFotos= vertical ? "ArrowRight" : "ArrowDown";
    const novo= {
      [maisFotos]: valor + PASSO,
      [menosFotos]: valor - PASSO,
      Home: MINIMO,
      End: MAXIMO,
    }[evento.key];
    if (novo === undefined) return;
    evento.preventDefault();
    aoMudar(limitar(novo));
  }

  return (
    <div
      ref={ref}
      className="divisor"
      data-a-arrastar={aArrastar}
      role="separator"
      tabIndex={0}
      aria-label="Dividir o espaço entre o mapa e as fotografias"
      aria-orientation={vertical ? "vertical" : "horizontal"}
      aria-valuemin={MINIMO}
      aria-valuemax={MAXIMO}
      aria-valuenow={valor}
      aria-valuetext={`Fotografias ocupam ${valor}% do espaço`}
      onPointerDown={comecar}
      onPointerMove={mover}
      onPointerUp={terminar}
      onPointerCancel={terminar}
      onDoubleClick={() => aoMudar(PADRAO)}
      onKeyDown={teclar}
    >
      <span className="divisor__pega" aria-hidden="true" />
    </div>
  );
}
