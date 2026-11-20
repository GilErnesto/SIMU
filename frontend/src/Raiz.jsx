import Inicio from "./Inicio.jsx";
import Notificacoes from "./Notificacoes.jsx";
import PaginaAnalise from "./PaginaAnalise.jsx";
import PainelReportes from "./PainelReportes.jsx";
import { NovoReporte, PaginaReporte } from "./Reportar.jsx";
import { tokenDaRota, useCaminho } from "./rota.js";

export default function Raiz() {
  const caminho= useCaminho().replace(/\/+$/, "") || "/";
  const token= tokenDaRota(caminho);
  if (token) return <PaginaAnalise key={token} token={token} />;
  if (caminho === "/reportar") return <NovoReporte />;
  const reporte= caminho.match(/^\/reportar\/([A-Za-z0-9_-]+)$/);
  if (reporte) return <PaginaReporte key={reporte[1]} token={reporte[1]} />;
  if (caminho === "/notificacoes") return <Notificacoes />;
  if (caminho === "/tecnico/reportes") return <PainelReportes />;
  return <Inicio />;
}
