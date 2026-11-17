export default function Barra({ rotulo, valor= null, maximo= 1, texto }) {
  const indeterminada= valor === null;
  const fracao= indeterminada ? 0 : Math.min(1, Math.max(0, valor / Math.max(maximo, 1)));
  const percentagem= Math.round(fracao * 100);
  return (
    <div className="progresso" role="status">
      <div
        className={indeterminada ? "barra barra--indeterminada" : "barra"}
        role="progressbar"
        aria-label={rotulo}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={indeterminada ? undefined : percentagem}
      >
        <div className="barra__valor" style={indeterminada ? undefined : { width: `${percentagem}%` }} />
      </div>
      <span>{texto ?? (indeterminada ? "" : `${percentagem}%`)}</span>
    </div>
  );
}
