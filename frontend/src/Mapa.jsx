import L from "leaflet";
import "leaflet.markercluster/dist/MarkerCluster.css";
import { useEffect, useMemo, useRef } from "react";
import { MapContainer, Marker, TileLayer, useMap, useMapEvents } from "react-leaflet";
import MarkerClusterGroup from "react-leaflet-cluster";

import { indiceCategoria, percentagem, rotuloClasse, rotuloEstado } from "./rotulos.js";

function iconeGrupo(grupo) {
  const total= grupo.getChildCount();
  return L.divIcon({
    className: "grupo-caixa",
    html: `<span class="grupo"><span aria-hidden="true">${total}</span><span class="grupo__nome">${total} elementos</span></span>`,
    iconSize: [44, 44],
    iconAnchor: [22, 22],
  });
}

function icone(indice, estado, ativo) {
  const classes= `pino pino--c${indice} pino--${estado}${ativo ? " pino--ativo" : ""}`;
  return L.divIcon({
    className: "pino-caixa",
    html: `<span class="${classes}"></span>`,
    iconSize: [44, 44],
    iconAnchor: [22, 22],
  });
}

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
}) {
  const [lonMin, latMin, lonMax, latMax]= config.bbox;
  const limites= [
    [latMin, lonMin],
    [latMax, lonMax],
  ];
  const marcadores= useMemo(
    () =>
      features.map((feature) => {
        const p= feature.properties;
        const [lon, lat]= feature.geometry.coordinates;
        const nome= rotuloClasse(config, p.categoria, p.classe);
        return {
          id: p.id,
          posicao: [lat, lon],
          titulo: `${nome}, ${rotuloEstado(p.estado)}, confiança ${percentagem(p.confianca)}`,
          icone: icone(indiceCategoria(config, p.categoria), p.estado, p.id === selecionadoId),
        };
      }),
    [config, features, selecionadoId],
  );
  const posicaoCandidata=
    candidata && Number.isFinite(candidata.lat) && Number.isFinite(candidata.lon)
      ? [candidata.lat, candidata.lon]
      : null;

  return (
    <MapContainer bounds={limites} className="mapa__area" maxZoom={20}>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        maxNativeZoom={19}
        maxZoom={20}
      />
      <AjustarTamanho vista={vista} />
      <AjustarVista features={features} bbox={config.bbox} />
      <Foco alvo={foco} />
      <EscolherPosicao ativo={modoMover} aoEscolher={aoEscolherPosicao} />
      <MarkerClusterGroup iconCreateFunction={iconeGrupo} showCoverageOnHover={false}>
        {marcadores.map((m) => (
          <Marker
            key={m.id}
            position={m.posicao}
            icon={m.icone}
            title={m.titulo}
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
      {posicaoCandidata && (
        <Marker position={posicaoCandidata} icon={ICONE_CANDIDATO} keyboard={false} interactive={false} />
      )}
    </MapContainer>
  );
}
