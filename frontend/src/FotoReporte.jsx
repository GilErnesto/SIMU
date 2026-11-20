import { urlFotoReporte } from "./api.js";

// A report's photo with boxes on top, placed in percentages so they follow the image at any size.
// With aoEscolher, every detected box is a button; otherwise only `caixa` is drawn.
export default function FotoReporte({ reporte, escolhida= null, aoEscolher, rotuloCaixa }) {
  const url= urlFotoReporte(reporte);
  if (!url) return <p className="foto__falta">Fotografia ainda não disponível.</p>;
  const { largura, altura }= reporte;
  const caixas= aoEscolher ? reporte.caixas : reporte.caixa ? [{ caixa: reporte.caixa }] : [];
  function estilo([x1, y1, x2, y2]) {
    return {
      left: `${(x1 / largura) * 100}%`,
      top: `${(y1 / altura) * 100}%`,
      width: `${((x2 - x1) / largura) * 100}%`,
      height: `${((y2 - y1) / altura) * 100}%`,
    };
  }
  return (
    <div className="foto-reporte">
      <img src={url} alt="Fotografia do reporte, com rostos e matrículas desfocados" />
      {largura > 0 &&
        caixas.map((item, indice) =>
          aoEscolher ? (
            <button
              key={indice}
              type="button"
              className={indice === escolhida ? "foto-reporte__caixa foto-reporte__caixa--escolhida" : "foto-reporte__caixa"}
              style={estilo(item.caixa)}
              aria-pressed={indice === escolhida}
              aria-label={rotuloCaixa ? rotuloCaixa(item) : `Objeto ${indice + 1}`}
              onClick={() => aoEscolher(indice)}
            >
              <span className="foto-reporte__numero" aria-hidden="true">
                {indice + 1}
              </span>
            </button>
          ) : (
            <span key={indice} className="foto-reporte__caixa foto-reporte__caixa--escolhida" style={estilo(item.caixa)} />
          ),
        )}
    </div>
  );
}
