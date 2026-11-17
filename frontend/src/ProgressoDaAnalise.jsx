import Barra from "./Barra.jsx";
import { formatarEspera, segundosDesde } from "./rotulos.js";

const FILA_LONGA_S= 60;

export default function ProgressoDaAnalise({ analise }) {
  if (analise.estado === "na_fila") {
    const espera= segundosDesde(analise.criada_em);
    return (
      <>
        <Barra rotulo="Análise na fila" texto="Na fila, à espera do worker" />
        {espera >= FILA_LONGA_S && (
          <p className="nota">
            Está na fila há {formatarEspera(espera)}. Se o worker não estiver a correr, arranque-o com{" "}
            <code>python -m pipeline.worker</code>.
          </p>
        )}
      </>
    );
  }
  if (analise.estado === "a_processar") {
    if (analise.total === 0) {
      return <Barra rotulo="Preparação dos ficheiros" texto="A preparar os ficheiros" />;
    }
    const percentagem= Math.round((analise.feitas / analise.total) * 100);
    return (
      <Barra
        rotulo="Progresso da análise"
        valor={analise.feitas}
        maximo={analise.total}
        texto={`Imagem ${analise.feitas} de ${analise.total}, ${percentagem}%`}
      />
    );
  }
  return null;
}
