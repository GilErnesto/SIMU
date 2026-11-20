import { useState } from "react";

import { rotuloClasse } from "./rotulos.js";

function metros(valor) {
  return `${valor.toFixed(1).replace(".", ",")} m`;
}

export default function Juntar({ config, vizinhos, desativado, aoJuntar, semTitulo= false }) {
  const [escolhido, setEscolhido]= useState("");
  const [aConfirmar, setAConfirmar]= useState(false);
  const alvo= vizinhos.find((vizinho) => String(vizinho.id) === escolhido) ?? null;

  function mudar(evento) {
    setEscolhido(evento.target.value);
    setAConfirmar(false);
  }

  async function confirmar() {
    await aoJuntar(alvo.id);
    setEscolhido("");
    setAConfirmar(false);
  }

  return (
    <section className="bloco" aria-label="Juntar com outro elemento">
      {!semTitulo && (
        <h3 id="titulo-juntar" className="bloco__titulo">
          Juntar com outro elemento
        </h3>
      )}
      {vizinhos.length === 0 ? (
        <p className="nota">Não há outros elementos da mesma categoria a menos de 15 metros.</p>
      ) : (
        <>
          <p className="nota">
            As fotografias do elemento escolhido passam para este e esse fica rejeitado. Nada é apagado.
          </p>
          <div className="campo">
            <label htmlFor="juntar-com">Elemento próximo</label>
            <select id="juntar-com" value={escolhido} onChange={mudar}>
              <option value="">Escolher</option>
              {vizinhos.map((vizinho) => (
                <option key={vizinho.id} value={vizinho.id}>
                  {rotuloClasse(config, vizinho.categoria, vizinho.classe)} {vizinho.id}: {metros(vizinho.distancia)}, {vizinho.n_observacoes}{" "}
                  {vizinho.n_observacoes === 1 ? "foto" : "fotos"}
                </option>
              ))}
            </select>
          </div>
          <div className="acoes">
            {!aConfirmar && (
              <button type="button" className="botao" disabled={desativado || !alvo} onClick={() => setAConfirmar(true)}>
                Juntar
              </button>
            )}
            {aConfirmar && (
              <>
                <button type="button" className="botao botao--perigo" disabled={desativado} onClick={confirmar}>
                  Confirmar: juntar o elemento {alvo.id} a este
                </button>
                <button type="button" className="botao botao--secundario" disabled={desativado} onClick={() => setAConfirmar(false)}>
                  Cancelar
                </button>
              </>
            )}
          </div>
        </>
      )}
    </section>
  );
}
