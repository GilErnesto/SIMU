import L from "leaflet";
import "leaflet.markercluster/dist/MarkerCluster.css";
import { useEffect, useMemo, useRef } from "react";
import { MapContainer, Marker, useMap, useMapEvents } from "react-leaflet";
import MarkerClusterGroup from "react-leaflet-cluster";

import CamadaMapa from "./CamadaMapa.jsx";
import { percentagem, rotuloClasse, rotuloEstado } from "./rotulos.js";
import { svgSimbolo } from "./simbolos.js";

function iconeGrupo(grupo) {
  const total= grupo.getChildCount();
  const duplicado= grupo.getAllChildMarkers().some((marcador) => marcador.options.duplicado);
  return L.divIcon({
    className: duplicado ? "grupo-caixa grupo-caixa--duplicado" : "grupo-caixa",
    html: `<span class="grupo"><span aria-hidden="true">${total}</span><span class="grupo__nome">${total} elementos${duplicado ? ", com possíveis duplicados" : ""}</span></span>`,
    iconSize: [44, 44],
    iconAnchor: [22, 22],
  });
}

function icone(categoria, classe, estado, ativo, duplicado, problema) {
  const classes= `pino pino--${estado}${ativo ? " pino--ativo" : ""}${duplicado ? " pino--duplicado" : ""}${problema ? " pino--com-reporte" : ""}`;
  return L.divIcon({
    className: "pino-caixa",
    html: `<span class="${classes}">${svgSimbolo(categoria, classe, estado)}</span>`,
    iconSize: [44, 44],
    iconAnchor: [22, 22],
  });
}

const SEM_DUPLICADOS= new Set();
const SEM_PROBLEMAS= [];

const ICONE_PROBLEMA_SOLTO= L.divIcon({
  className: "pino-caixa",
  html: '<span class="pino pino--problema"></span>',
  iconSize: [44, 44],
  iconAnchor: [22, 22],
});

const ICONE_CANDIDATO= L.divIcon({
  className: "pino-caixa",
  html: '<span class="pino pino--candidato"></span>',
  iconSize: [44, 44],
  iconAnchor: [22, 22],
});

function AjustarTamanho({ vista }) {
  const mapa= useMap();
  useEffect(() => {
    mapa.invalidateSize();
  }, [mapa, vista]);
  useEffect(() => {
    const observador= new ResizeObserver(() => mapa.invalidateSize());
    observador.observe(mapa.getContainer());
    return () => observador.disconnect();
  }, [mapa]);
  return null;
}

function AjustarVista({ features, bbox }) {
  const mapa= useMap();
  const feito= useRef(false);
  useEffect(() => {
    if (feito.current || features.length === 0) return;
    feito.current= true;
    const limites= L.latLngBounds(features.map((f) => [f.geometry.coordinates[1], f.geometry.coordinates[0]]));
    mapa.fitBounds(limites, { maxZoom: 18, padding: [40, 40], animate: false });
  }, [mapa, features, bbox]);
  return null;
}

function Foco({ alvo }) {
  const mapa= useMap();
  useEffect(() => {
    if (!alvo) return;
    mapa.setView([alvo.lat, alvo.lon], Math.max(mapa.getZoom(), 18), { animate: false });
  }, [mapa, alvo]);
  return null;
}

function EscolherPosicao({ ativo, aoEscolher }) {
  useMapEvents({
    click(evento) {
      if (ativo) aoEscolher(evento.latlng.lat, evento.latlng.lng);
    },
  });
  return null;
}

export default function Mapa({
  config,
  features,
  selecionadoId,
  foco,
  vista,
  modoMover,
  candidata,
  aoSelecionar,
  aoEscolherPosicao,
  duplicadosIds= SEM_DUPLICADOS,
  problemasSoltos= SEM_PROBLEMAS,
  aoAbrirProblemaSolto,
}) {
  const [lonMin, latMin, lonMax, latMax]= config.bbox;
  const comPosicao= useMemo(() => features.filter((feature) => feature.geometry), [features]);
  const limites= [
    [latMin, lonMin],
    [latMax, lonMax],
  ];
  const marcadores= useMemo(
    () =>
      comPosicao.map((feature) => {
        const p= feature.properties;
        const [lon, lat]= feature.geometry.coordinates;
        const nome= rotuloClasse(config, p.categoria, p.classe);
        const duplicado= duplicadosIds.has(p.id);
        return {
          id: p.id,
          duplicado,
          problema: p.reportes_abertos > 0,
          posicao: [lat, lon],
          titulo: `${nome}, ${rotuloEstado(p.estado)}, confiança ${percentagem(p.confianca)}${duplicado ? ", possível duplicado" : ""}${p.reportes_abertos ? `, ${p.reportes_abertos} problema(s) reportado(s)` : ""}`,
          icone: icone(p.categoria, p.classe, p.estado, p.id === selecionadoId, duplicado, p.reportes_abertos > 0),
        };
      }),
    [config, comPosicao, selecionadoId, duplicadosIds],
  );
  const chaveDuplicados= useMemo(() => [...duplicadosIds].sort((x, y) => x - y).join(","), [duplicadosIds]);
  const posicaoCandidata=
    candidata && Number.isFinite(candidata.lat) && Number.isFinite(candidata.lon)
      ? [candidata.lat, candidata.lon]
      : null;

  return (
    <MapContainer bounds={limites} className="mapa__area" maxZoom={20}>
      <CamadaMapa />
      <AjustarTamanho vista={vista} />
      <AjustarVista features={comPosicao} bbox={config.bbox} />
      <Foco alvo={foco} />
      <EscolherPosicao ativo={modoMover} aoEscolher={aoEscolherPosicao} />
      <MarkerClusterGroup key={chaveDuplicados} iconCreateFunction={iconeGrupo} showCoverageOnHover={false}>
        {marcadores.filter((m) => !m.problema).map((m) => (
          <Marker
            key={m.id}
            position={m.posicao}
            icon={m.icone}
            title={m.titulo}
            duplicado={m.duplicado}
            eventHandlers={{
              click: () => aoSelecionar(m.id, "mapa"),
              keydown: (evento) => {
                if (evento.originalEvent.key === "Enter" || evento.originalEvent.key === " ") {
                  evento.originalEvent.preventDefault();
                  aoSelecionar(m.id, "mapa");
                }
              },
            }}
          />
        ))}
      </MarkerClusterGroup>
      {/* Elements with an open citizen problem stay out of the clusters: always visible. */}
        {marcadores.filter((m) => m.problema).map((m) => (
          <Marker
            key={m.id}
            position={m.posicao}
            icon={m.icone}
            title={m.titulo}
            duplicado={m.duplicado}
            zIndexOffset={1000}
            eventHandlers={{
              click: () => aoSelecionar(m.id, "mapa"),
              keydown: (evento) => {
                if (evento.originalEvent.key === "Enter" || evento.originalEvent.key === " ") {
                  evento.originalEvent.preventDefault();
                  aoSelecionar(m.id, "mapa");
                }
              },
            }}
          />
        ))}
      {problemasSoltos.map((f) => (
        <Marker
          key={f.properties.token}
          position={[f.geometry.coordinates[1], f.geometry.coordinates[0]]}
          icon={ICONE_PROBLEMA_SOLTO}
          title={`Problema reportado sem elemento no catálogo: ${f.properties.titulo}`}
          eventHandlers={{ click: () => aoAbrirProblemaSolto?.(f.properties.token) }}
        />
      ))}
      {posicaoCandidata && (
        <Marker position={posicaoCandidata} icon={ICONE_CANDIDATO} keyboard={false} interactive={false} />
      )}
    </MapContainer>
  );
}
