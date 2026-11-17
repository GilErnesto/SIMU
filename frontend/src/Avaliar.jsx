import { useEffect, useRef, useState } from "react";

import { Foto } from "./Fotos.jsx";
import { lerNumero, rotuloClasse, rotuloEstado } from "./rotulos.js";

function aoFocar(evento) {
  evento.currentTarget.scrollIntoView({ block: "center" });
}

export default function Avaliar({
  config,
  dados,
  tecnico,
  modoMover,
  candidata,
  aoMudarTecnico,
  aoGuardar,
  aoFechar,
  aoAlternarMover,
  aoMudarCandidata,
}) {
  const titulo= useRef(null);
  const [escolhida, setEscolhida]= useState(null);
  const [aGuardar, setAGuardar]= useState(false);
  const [mensagem, setMensagem]= useState(null);
  const p= dados.properties;
  const classe= escolhida ?? p.classe;
  const classes= config.categorias[p.categoria]?.classes ?? [];
  const [lon, lat]= dados.geometry.coordinates;
  const campoLat= candidata ? candidata.lat : lat.toFixed(6);
  const campoLon= candidata ? candidata.lon : lon.toFixed(6);

  useEffect(() => {
    titulo.current?.focus();
  }, []);

  useEffect(() => {
    setEscolhida(null);
    setMensagem(null);
  }, [p.id]);

  async function executar(corpo) {
    if (!tecnico.trim()) {
      setMensagem({ tipo: "erro", texto: "Indique o seu nome antes de guardar." });
      return;
    }
    setAGuardar(true);
    setMensagem(null);
    try {
      await aoGuardar({ ...corpo, autor: tecnico.trim() });
      setEscolhida(null);
      setMensagem({ tipo: "ok", texto: "Alteração guardada." });
    } catch (erro) {
      setMensagem({ tipo: "erro", texto: erro.message });
    } finally {
      setAGuardar(false);
    }
  }

  function guardarPosicao() {
    const novaLat= lerNumero(candidata?.lat ?? "");
    const novaLon= lerNumero(candidata?.lon ?? "");
    if (!Number.isFinite(novaLat) || !Number.isFinite(novaLon)) {
      setMensagem({ tipo: "erro", texto: "Indique uma latitude e uma longitude válidas." });
      return;
    }
    executar({ lat: novaLat, lon: novaLon });
  }

  return (
    <aside className="avaliar" role="dialog" aria-modal="false" aria-labelledby="titulo-avaliar" data-a-escolher={modoMover}>
      <div className="avaliar__cabeca">
        <h2 id="titulo-avaliar" className="painel__titulo" ref={titulo} tabIndex={-1}>
          Avaliar: {rotuloClasse(config, p.categoria, p.classe)}
        </h2>
        <button type="button" className="botao botao--secundario" onClick={aoFechar}>
          Fechar
        </button>
      </div>
      <p className="nota">Estado atual: {rotuloEstado(p.estado)}. Cada alteração fica registada com o seu nome.</p>

      {p.observacoes.length > 0 && (
        <div className="avaliar__foto">
          <Foto observacao={p.observacoes[0]} />
        </div>
      )}

      <div className="campo">
        <label htmlFor="tecnico">O seu nome</label>
        <input id="tecnico" autoComplete="name" value={tecnico} onFocus={aoFocar} onChange={(e) => aoMudarTecnico(e.target.value)} />
      </div>

      <section className="bloco" aria-labelledby="titulo-decisao">
        <h3 id="titulo-decisao" className="bloco__titulo">
          Decisão
        </h3>
        <div className="acoes">
          <button type="button" className="botao botao--principal" disabled={aGuardar || p.estado === "validado"} onClick={() => executar({ estado: "validado" })}>
            Validar
          </button>
          <button type="button" className="botao" disabled={aGuardar || p.estado === "rejeitado"} onClick={() => executar({ estado: "rejeitado" })}>
            Rejeitar
          </button>
          <button type="button" className="botao botao--secundario" disabled={aGuardar || p.estado === "auto"} onClick={() => executar({ estado: "auto" })}>
            Voltar a por rever
          </button>
        </div>
        <p className="nota">Rejeitar não apaga o elemento: fica registado no histórico de correções.</p>
      </section>

      <section className="bloco" aria-labelledby="titulo-classe">
        <h3 id="titulo-classe" className="bloco__titulo">
          Corrigir o tipo
        </h3>
        <div className="campo">
          <label htmlFor="classe">Tipo</label>
          <select id="classe" value={classe} onFocus={aoFocar} onChange={(evento) => setEscolhida(evento.target.value)}>
            {classes.map((c) => (
              <option key={c.id} value={c.id}>
                {c.rotulo}
              </option>
            ))}
          </select>
        </div>
        <button type="button" className="botao" disabled={aGuardar || classe === p.classe} onClick={() => executar({ classe })}>
          Guardar tipo
        </button>
      </section>

      <section className="bloco" aria-labelledby="titulo-posicao">
        <h3 id="titulo-posicao" className="bloco__titulo">
          Corrigir a posição
        </h3>
        <div className="campos-par">
          <div className="campo">
            <label htmlFor="lat">Latitude</label>
            <input id="lat" inputMode="decimal" value={campoLat} onFocus={aoFocar} onChange={(e) => aoMudarCandidata({ lat: e.target.value, lon: campoLon })} />
          </div>
          <div className="campo">
            <label htmlFor="lon">Longitude</label>
            <input id="lon" inputMode="decimal" value={campoLon} onFocus={aoFocar} onChange={(e) => aoMudarCandidata({ lat: campoLat, lon: e.target.value })} />
          </div>
        </div>
        <div className="acoes">
          <button type="button" className="botao" aria-pressed={modoMover} onClick={aoAlternarMover}>
            {modoMover ? "A escolher no mapa: clique para parar" : "Escolher no mapa"}
          </button>
          <button type="button" className="botao" disabled={aGuardar || !candidata} onClick={guardarPosicao}>
            Guardar posição
          </button>
        </div>
      </section>

      <div className="estado-guardar" role={mensagem?.tipo === "erro" ? "alert" : "status"}>
        {mensagem && <p className={mensagem.tipo === "erro" ? "mensagem--erro" : "mensagem--ok"}>{mensagem.texto}</p>}
      </div>
    </aside>
  );
}
