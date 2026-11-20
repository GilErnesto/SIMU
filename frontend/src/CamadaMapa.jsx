import { leafletLayer } from "protomaps-leaflet";
import { useEffect } from "react";
import { useMap } from "react-leaflet";

const URL_MAPA= "/mapa/portugal.pmtiles";
const ATRIBUICAO= '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>, <a href="https://protomaps.com">Protomaps</a>';

export default function CamadaMapa() {
  const mapa= useMap();
  useEffect(() => {
    const camada= leafletLayer({
      url: URL_MAPA,
      flavor: "light",
      lang: "pt",
      attribution: ATRIBUICAO,
      maxDataZoom: 15,
      maxZoom: 20,
    });
    camada.addTo(mapa);
    return () => {
      camada.remove();
    };
  }, [mapa]);
  return null;
}
