import { useEffect, useRef, useState } from "react";

import { ImagemComCaixa } from "./Fotos.jsx";
import { IconeFechar } from "./icones.jsx";
import Juntar from "./Juntar.jsx";
import { lerNumero, rotuloClasse, rotuloEstado } from "./rotulos.js";
import { Ligacao } from "./rota.js";

const FOTOS_NA_TIRA= 4;

function aoFocar(evento) {
  evento.currentTarget.scrollIntoView({ block: "center" });
}

export default function Avaliar({
  config,
  dados,
  tecnico,
  modoMover,
  candidata,
  aoGuardar,
  aoFechar,
  aoAlternarMover,
  aoMudarCandidata,
  vizinhos,
  aoJuntar,
  aoAmpliar,
}) {
  const titulo= useRef(null);
  const [escolhida, setEscolhida]= useState(null);
  const [aGuardar, setAGuardar]= useState(false);
  const [mensagem, setMensagem]= useState(null);
  const p= dados.properties;
  const classe= escolhida ?? p.classe;
  const classes= config.categorias[p.categoria]?.classes ?? [];
  const semPosicao= !dados.geometry;
  const [lon, lat]= semPosicao ? [null, null] : dados.geometry.coordinates;
  const campoLat= candidata ? candidata.lat : lat === null ? "" : lat.toFixed(6);
  const campoLon= candidata ? candidata.lon : lon === null ? "" : lon.toFixed(6);

  useEffect(() => {
    titulo.current?.focus({ preventScroll: true });
  }, []);

  useEffect(() => {
    setEscolhida(null);
    setMensagem(null);
  }, [p.id]);

  function exigirNome() {
    if (tecnico.trim()) return true;
    setMensagem({ tipo: "erro", texto: "Indique o nome do técnico na página inicial.", ligacao: true });
    return false;
  }

  async function executar(corpo) {
    if (!exigirNome()) return;
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

  async function juntarComVizinho(origemId) {
    if (!exigirNome()) return;
    setAGuardar(true);
    setMensagem(null);
    try {
      await aoJuntar(origemId, tecnico.trim());
      setMensagem({ tipo: "ok", texto: "Elementos juntados." });
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

  const fotos= p.observacoes.slice(0, FOTOS_NA_TIRA);

  return (
    <section className="avaliar" aria-labelledby="titulo-avaliar" data-a-escolher={modoMover}>
      <div className="avaliar__cabeca">
        <div>
          <h2 id="titulo-avaliar" className="painel__titulo" ref={titulo} tabIndex={-1}>
            Avaliar: {rotuloClasse(config, p.categoria, p.classe)}
          </h2>
          <p className="nota">Estado atual: {rotuloEstado(p.estado)}.</p>
        </div>
        <button type="button" className="botao botao--icone avaliar__fechar" aria-label="Fechar a avaliação" onClick={aoFechar}>
          <IconeFechar />
        </button>
      </div>

      {fotos.length > 0 && (
        <ul className="tira" aria-label="Fotografias do elemento">
          {fotos.map((observacao, indice) => (
            <li key={observacao.id}>
              <button
                type="button"
                className="tira__foto"
                aria-label={`Ampliar a fotografia ${indice + 1} de ${p.observacoes.length}`}
                onClick={() => aoAmpliar(indice)}
              >
                <ImagemComCaixa observacao={observacao} />
              </button>
            </li>
          ))}
          {p.observacoes.length > FOTOS_NA_TIRA && (
            <li className="tira__mais nota">+{p.observacoes.length - FOTOS_NA_TIRA}</li>
          )}
        </ul>
      )}

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
          {semPosicao ? "Indicar a posição" : "Corrigir a posição"}
        </h3>
        {semPosicao && (
          <p className="nota">
            Este elemento não tem posição porque a fotografia não tem GPS. Escreva as coordenadas ou escolha o ponto no mapa.
          </p>
        )}
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

      <details className="recolhido">
        <summary>Juntar com outro elemento{vizinhos.length > 0 ? ` (${vizinhos.length} perto)` : ""}</summary>
        <Juntar config={config} vizinhos={vizinhos} desativado={aGuardar} aoJuntar={juntarComVizinho} semTitulo />
      </details>

      <div className="estado-guardar" role={mensagem?.tipo === "erro" ? "alert" : "status"}>
        {mensagem && <p className={mensagem.tipo === "erro" ? "mensagem--erro" : "mensagem--ok"}>{mensagem.texto}</p>}
        {mensagem?.ligacao && (
          <Ligacao para="/" className="botao botao--ligacao">
            Ir para a página inicial
          </Ligacao>
        )}
      </div>
    </section>
  );
}
