import { useEffect, useRef, useState } from "react";
import { CircleMarker, MapContainer, Rectangle, useMap, useMapEvents } from "react-leaflet";

import { criarAnaliseZona, obterConfig } from "./api.js";
import CamadaMapa from "./CamadaMapa.jsx";
import "./zona.css";

const ZONA_MAX_GRAUS= 0.02;
const METROS_POR_GRAU= 111320;
const TOLERANCIA= 1e-9;

function arredondar(numero) {
  return Number(numero.toFixed(6));
}

function retangulo(a, b) {
  return {
    lonMin: Math.min(a[1], b[1]),
    latMin: Math.min(a[0], b[0]),
    lonMax: Math.max(a[1], b[1]),
    latMax: Math.max(a[0], b[0]),
  };
}

function bboxDe(zona) {
  return [zona.lonMin, zona.latMin, zona.lonMax, zona.latMax].map(arredondar);
}

function textoDe(zona) {
  return bboxDe(zona).join(",");
}

function lerCoordenadas(texto) {
  const partes= texto.split(",").map((parte) => parte.trim());
  if (partes.length !== 4 || partes.some((parte) => parte === "" || !Number.isFinite(Number(parte)))) {
    return { erro: "Escreva quatro números separados por vírgulas: lon_min, lat_min, lon_max, lat_max." };
  }
  const [a, b, c, d]= partes.map(Number);
  if (a < -180 || a > 180 || c < -180 || c > 180 || b < -90 || b > 90 || d < -90 || d > 90) {
    return { erro: "Os valores estão fora do intervalo: longitude entre -180 e 180, latitude entre -90 e 90." };
  }
  const zona= { lonMin: Math.min(a, c), latMin: Math.min(b, d), lonMax: Math.max(a, c), latMax: Math.max(b, d) };
  if (zona.lonMin === zona.lonMax || zona.latMin === zona.latMax) {
    return { erro: "A zona tem de ter área: os dois cantos não podem estar alinhados." };
  }
  return { zona };
}

function demasiadoGrande(zona) {
  return zona.lonMax - zona.lonMin > ZONA_MAX_GRAUS + TOLERANCIA || zona.latMax - zona.latMin > ZONA_MAX_GRAUS + TOLERANCIA;
}

function dimensoesDe(zona) {
  const latitudeMedia= ((zona.latMin + zona.latMax) / 2) * (Math.PI / 180);
  return {
    largura: (zona.lonMax - zona.lonMin) * METROS_POR_GRAU * Math.cos(latitudeMedia),
    altura: (zona.latMax - zona.latMin) * METROS_POR_GRAU,
  };
}

function arredondarMetros(metros) {
  return Math.round(metros / 10) * 10;
}

function limitesDe(bbox) {
  return [
    [bbox[1], bbox[0]],
    [bbox[3], bbox[2]],
  ];
}

function Escolha({ cantoInicial, zona, aoTocar }) {
  const mapa= useMap();

  useMapEvents({
    click: (evento) => aoTocar(evento.latlng),
  });

  useEffect(() => {
    mapa.invalidateSize();
    const observador= new ResizeObserver(() => mapa.invalidateSize());
    observador.observe(mapa.getContainer());
    return () => observador.disconnect();
  }, [mapa]);

  return (
    <>
      {zona && (
        <Rectangle
          bounds={limitesDe([zona.lonMin, zona.latMin, zona.lonMax, zona.latMax])}
          pathOptions={{ className: "zona-retangulo", interactive: false }}
        />
      )}
      {cantoInicial && (
        <CircleMarker
          center={cantoInicial}
          radius={7}
          pathOptions={{ className: "zona-canto", interactive: false }}
        />
      )}
    </>
  );
}

export default function ZonaNoMapa({ aoFechar, aoEnviar }) {
  const dialogo= useRef(null);
  const titulo= useRef(null);
  const [config, setConfig]= useState(null);
  const [erroConfig, setErroConfig]= useState(null);
  const [cantoInicial, setCantoInicial]= useState(null);
  const [zona, setZona]= useState(null);
  const [texto, setTexto]= useState("");
  const [erroTexto, setErroTexto]= useState(null);
  const [nome, setNome]= useState("");
  const [enviando, setEnviando]= useState(false);
  const [erro, setErro]= useState(null);

  useEffect(() => {
    const no= dialogo.current;
    if (no && !no.open) no.showModal();
    titulo.current?.focus();
    return () => {
      if (no?.open) no.close();
    };
  }, []);

  useEffect(() => {
    const controlo= new AbortController();
    obterConfig(controlo.signal)
      .then(setConfig)
      .catch((falha) => {
        if (falha.name !== "AbortError") setErroConfig(falha.message);
      });
    return () => controlo.abort();
  }, []);

  function limparSelecao() {
    setCantoInicial(null);
    setZona(null);
    setTexto("");
    setErroTexto(null);
  }

  function aoTocar(latlng) {
    setErro(null);
    const ponto= [latlng.lat, latlng.lng];
    if (!cantoInicial) {
      setCantoInicial(ponto);
      setZona(null);
      setTexto("");
      setErroTexto(null);
      return;
    }
    const nova= retangulo(cantoInicial, ponto);
    if (nova.lonMin === nova.lonMax || nova.latMin === nova.latMax) return;
    setCantoInicial(null);
    setZona(nova);
    setTexto(textoDe(nova));
    setErroTexto(null);
  }

  function aoEditarTexto(valor) {
    setTexto(valor);
    setCantoInicial(null);
    setErro(null);
    if (valor.trim() === "") {
      setZona(null);
      setErroTexto(null);
      return;
    }
    const leitura= lerCoordenadas(valor);
    setZona(leitura.zona || null);
    setErroTexto(leitura.erro || null);
  }

  async function enviar(evento) {
    evento.preventDefault();
    if (!zona || demasiadoGrande(zona) || enviando) return;
    setEnviando(true);
    setErro(null);
    try {
      const resposta= await criarAnaliseZona({ bbox: bboxDe(zona), nome: nome.trim() });
      aoEnviar(resposta);
    } catch (falha) {
      setErro(falha.message);
      setEnviando(false);
    }
  }

  const grande= zona && demasiadoGrande(zona);
  const dimensoes= zona && dimensoesDe(zona);

  return (
    <dialog
      ref={dialogo}
      className="dialogo zona-dialogo"
      aria-labelledby="titulo-zona-mapillary"
      onCancel={(evento) => {
        evento.preventDefault();
        aoFechar();
      }}
    >
      <div className="zona-dialogo__cabeca">
        <h2 id="titulo-zona-mapillary" className="dialogo__titulo" ref={titulo} tabIndex={-1}>
          Analisar uma zona do Mapillary
        </h2>
        <button type="button" className="botao botao--secundario" onClick={aoFechar}>
          Fechar
        </button>
      </div>
      <form className="zona-painel__form" onSubmit={enviar}>
        {erroConfig && (
          <p className="mensagem mensagem--erro" role="alert">
            Não foi possível carregar o mapa. {erroConfig}
          </p>
        )}
        {!config && !erroConfig && <p className="mensagem">A carregar o mapa.</p>}
        {config && (
          <>
            <p className="nota" id="instrucao-zona">
              Toque no mapa para marcar um canto da zona e toque noutro canto para fechar o retângulo.
            </p>
            <MapContainer bounds={limitesDe(config.bbox)} className="zona-mapa" maxZoom={20} doubleClickZoom={false}>
              <CamadaMapa />
              <Escolha cantoInicial={cantoInicial} zona={zona} aoTocar={aoTocar} />
            </MapContainer>
          </>
        )}

        {zona && dimensoes && (
          <p className="zona-painel__medida">
            Zona de cerca de {arredondarMetros(dimensoes.largura)} m por {arredondarMetros(dimensoes.altura)} m
          </p>
        )}
        {zona && dimensoes && !grande && (
          <p className="nota">
            Cada 100 imagens demoram cerca de 3 minutos. Zonas com mais de 1500 imagens são recusadas: em ruas densas
            escolha uma área pequena (cerca de 300 m de lado).
          </p>
        )}
        {grande && (
          <p className="mensagem mensagem--erro" role="status">
            A zona é grande demais: no máximo cerca de 2 km de lado.
          </p>
        )}

        <div className="campo">
          <label htmlFor="coordenadas-zona">Coordenadas (lon_min,lat_min,lon_max,lat_max)</label>
          <input
            id="coordenadas-zona"
            value={texto}
            disabled={enviando}
            autoComplete="off"
            spellCheck={false}
            aria-invalid={erroTexto ? "true" : undefined}
            aria-describedby={erroTexto ? "erro-coordenadas" : undefined}
            onChange={(evento) => aoEditarTexto(evento.target.value)}
          />
          {erroTexto && (
            <p id="erro-coordenadas" className="mensagem mensagem--erro">
              {erroTexto}
            </p>
          )}
        </div>

        <div className="campo">
          <label htmlFor="nome-zona">Nome da análise (opcional)</label>
          <input
            id="nome-zona"
            value={nome}
            maxLength={120}
            disabled={enviando}
            onChange={(evento) => setNome(evento.target.value)}
          />
        </div>

        <div className="acoes">
          <button type="submit" className="botao botao--principal" disabled={!zona || grande || enviando}>
            {enviando ? "A enviar" : "Analisar esta zona"}
          </button>
          <button type="button" className="botao botao--secundario" disabled={enviando} onClick={limparSelecao}>
            Limpar
          </button>
        </div>

        {erro && (
          <p className="mensagem mensagem--erro" role="alert">
            {erro}
          </p>
        )}
        <p className="nota">As imagens vêm do Mapillary (CC BY-SA 4.0). O worker precisa do MAPILLARY_TOKEN configurado.</p>
      </form>
    </dialog>
  );
}
