import { useEffect, useRef, useState } from "react";

const ZOOM_MIN= 1;
const ZOOM_MAX= 8;
const PASSO_BOTAO= 1.5;
const PASSO_TECLADO= 40;
const ZOOM_DUPLO= 3;
const VISTA_INICIAL= { s: 1, x: 0, y: 0 };

function limitar(valor, minimo, maximo) {
  return Math.min(maximo, Math.max(minimo, valor));
}

function prender(vista, largura, altura) {
  return {
    s: vista.s,
    x: limitar(vista.x, largura * (1 - vista.s), 0),
    y: limitar(vista.y, altura * (1 - vista.s), 0),
  };
}

function aproximar(vista, fator, px, py, largura, altura) {
  const s= limitar(vista.s * fator, ZOOM_MIN, ZOOM_MAX);
  const razao= s / vista.s;
  return prender(
    { s, x: px - (px - vista.x) * razao, y: py - (py - vista.y) * razao },
    largura,
    altura,
  );
}

function nivelTexto(s) {
  return `${s.toFixed(1).replace(".", ",")}×`;
}

export default function ImagemComZoom({ observacao, descricao, botoes= true }) {
  const { imagem, bbox }= observacao;
  const caixa= bbox && bbox.length === 4 ? bbox : null;
  const area= useRef(null);
  const ponteiros= useRef(new Map());
  const pinca= useRef(null);
  const [tamanho, setTamanho]= useState(null);
  const [falhou, setFalhou]= useState(false);
  const [vista, setVista]= useState(VISTA_INICIAL);

  useEffect(() => {
    setVista(VISTA_INICIAL);
  }, [imagem.url]);

  useEffect(() => {
    const no= area.current;
    if (!no) return undefined;
    function aoRodar(evento) {
      evento.preventDefault();
      const rect= no.getBoundingClientRect();
      const fator= Math.exp(-evento.deltaY * 0.0015);
      zoomEm(fator, evento.clientX - rect.left, evento.clientY - rect.top);
    }
    no.addEventListener("wheel", aoRodar, { passive: false });
    return () => no.removeEventListener("wheel", aoRodar);
  }, []);

  function alterar(transformar) {
    const no= area.current;
    if (!no) return;
    const largura= no.clientWidth;
    const altura= no.clientHeight;
    setVista((atual) => prender(transformar(atual, largura, altura), largura, altura));
  }

  function zoomEm(fator, px, py) {
    alterar((atual, largura, altura) => aproximar(atual, fator, px ?? largura / 2, py ?? altura / 2, largura, altura));
  }

  function repor() {
    alterar(() => VISTA_INICIAL);
  }

  function deslocar(dx, dy) {
    alterar((atual) => ({ ...atual, x: atual.x + dx, y: atual.y + dy }));
  }

  function aoPonteiroBaixo(evento) {
    if (evento.pointerType === "mouse" && evento.button !== 0) return;
    ponteiros.current.set(evento.pointerId, { x: evento.clientX, y: evento.clientY });
    pinca.current= null;
    area.current.setPointerCapture(evento.pointerId);
  }

  function aoPonteiroMover(evento) {
    const ponto= ponteiros.current.get(evento.pointerId);
    if (!ponto) return;
    const dx= evento.clientX - ponto.x;
    const dy= evento.clientY - ponto.y;
    ponto.x= evento.clientX;
    ponto.y= evento.clientY;
    if (ponteiros.current.size >= 2) {
      const [primeiro, segundo]= [...ponteiros.current.values()];
      const distancia= Math.hypot(primeiro.x - segundo.x, primeiro.y - segundo.y);
      const rect= area.current.getBoundingClientRect();
      if (pinca.current && pinca.current > 0) {
        zoomEm(distancia / pinca.current, (primeiro.x + segundo.x) / 2 - rect.left, (primeiro.y + segundo.y) / 2 - rect.top);
      }
      pinca.current= distancia;
      return;
    }
    if (vista.s > ZOOM_MIN) deslocar(dx, dy);
  }

  function aoPonteiroSoltar(evento) {
    ponteiros.current.delete(evento.pointerId);
    pinca.current= null;
    if (area.current.hasPointerCapture(evento.pointerId)) area.current.releasePointerCapture(evento.pointerId);
  }

  function aoDuploClique(evento) {
    if (vista.s > ZOOM_MIN) {
      repor();
      return;
    }
    const rect= area.current.getBoundingClientRect();
    zoomEm(ZOOM_DUPLO, evento.clientX - rect.left, evento.clientY - rect.top);
  }

  function aoTeclar(evento) {
    const { key }= evento;
    if (key === "+" || key === "=") {
      evento.preventDefault();
      zoomEm(PASSO_BOTAO);
    } else if (key === "-" || key === "_") {
      evento.preventDefault();
      zoomEm(1 / PASSO_BOTAO);
    } else if (key === "0") {
      evento.preventDefault();
      repor();
    } else if (vista.s > ZOOM_MIN && key.startsWith("Arrow")) {
      evento.preventDefault();
      evento.stopPropagation();
      if (key === "ArrowLeft") deslocar(PASSO_TECLADO, 0);
      if (key === "ArrowRight") deslocar(-PASSO_TECLADO, 0);
      if (key === "ArrowUp") deslocar(0, PASSO_TECLADO);
      if (key === "ArrowDown") deslocar(0, -PASSO_TECLADO);
    }
  }

  if (!imagem.url || falhou) return <p className="foto__falta">Imagem não disponível.</p>;

  return (
    <div className="zoom" style={tamanho ? { "--proporcao": tamanho.w / tamanho.h } : undefined}>
      <div
        ref={area}
        className="zoom__area"
        role="group"
        tabIndex={0}
        aria-label="Imagem ampliável. Use as teclas mais, menos e zero, ou as setas quando estiver ampliada."
        onPointerDown={aoPonteiroBaixo}
        onPointerMove={aoPonteiroMover}
        onPointerUp={aoPonteiroSoltar}
        onPointerCancel={aoPonteiroSoltar}
        onDoubleClick={aoDuploClique}
        onKeyDown={aoTeclar}
      >
        <div className="zoom__camada" style={{ transform: `translate(${vista.x}px, ${vista.y}px) scale(${vista.s})` }}>
          <img
            src={`/api${imagem.url}`}
            alt={descricao ?? ""}
            draggable={false}
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
      </div>
      <div className="zoom__controlos">
        {botoes && (
          <>
            <button type="button" className="botao" onClick={() => zoomEm(PASSO_BOTAO)}>
              Aproximar
            </button>
            <button type="button" className="botao" onClick={() => zoomEm(1 / PASSO_BOTAO)}>
              Afastar
            </button>
            <button type="button" className="botao" onClick={repor}>
              Repor
            </button>
          </>
        )}
        <output className="zoom__nivel" aria-live="polite">
          {nivelTexto(vista.s)}
        </output>
      </div>
    </div>
  );
}
