import { useEffect, useRef, useState } from "react";

import { ligacaoExportacao, ligacaoReportes } from "./api.js";
import { IconeExportar, IconeSetaBaixo } from "./icones.jsx";

const FORMATOS= [
  { id: "geojson", nome: "GeoJSON", ajuda: "Para o mapa e programas de SIG" },
  { id: "csv", nome: "CSV", ajuda: "Para folhas de cálculo" },
];

export default function MenuExportar({ token, filtros, mostrados }) {
  const [aberto, setAberto]= useState(false);
  const raiz= useRef(null);
  const comFiltros= Object.values(filtros).some(Boolean);

  useEffect(() => {
    if (!aberto) return undefined;
    function aoClicarFora(evento) {
      if (raiz.current && !raiz.current.contains(evento.target)) setAberto(false);
    }
    document.addEventListener("pointerdown", aoClicarFora);
    return () => document.removeEventListener("pointerdown", aoClicarFora);
  }, [aberto]);

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
        className="botao botao--principal"
        aria-expanded={aberto}
        aria-controls="menu-exportar"
        onClick={() => setAberto((valor) => !valor)}
      >
        <IconeExportar />
        Exportar
        <IconeSetaBaixo tamanho={16} />
      </button>
      {aberto && (
        <div id="menu-exportar" className="flutuante flutuante--direita">
          <p className="flutuante__titulo">Escolha o formato</p>
          <ul className="menu__lista">
            {FORMATOS.map((formato) => (
              <li key={formato.id}>
                <a
                  className="menu__opcao"
                  href={ligacaoExportacao(formato.id, { ...filtros, analise: token })}
                  download
                  onClick={() => setAberto(false)}
                >
                  <span className="menu__nome">{formato.nome}</span>
                  <span className="nota">{formato.ajuda}</span>
                </a>
              </li>
            ))}
          </ul>
          <p className="flutuante__titulo">Problemas reportados (todas as zonas)</p>
          <ul className="menu__lista">
            {FORMATOS.map((formato) => (
              <li key={formato.id}>
                <a className="menu__opcao" href={ligacaoReportes(formato.id)} download onClick={() => setAberto(false)}>
                  <span className="menu__nome">Problemas em {formato.nome}</span>
                  <span className="nota">Com o histórico de cada um</span>
                </a>
              </li>
            ))}
          </ul>
          {comFiltros && (
            <p className="nota flutuante__nota">
              Inclui só os {mostrados} {mostrados === 1 ? "elemento" : "elementos"} que passam nos filtros.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
