import Inicio from "./Inicio.jsx";
import PaginaAnalise from "./PaginaAnalise.jsx";
import { tokenDaRota, useCaminho } from "./rota.js";

export default function Raiz() {
  const caminho= useCaminho();
  const token= tokenDaRota(caminho);
  return token ? <PaginaAnalise key={token} token={token} /> : <Inicio />;
}
