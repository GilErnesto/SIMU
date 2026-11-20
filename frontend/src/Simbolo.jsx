import { svgSimbolo } from "./simbolos.js";

export default function Simbolo({ categoria, classe, estado= "auto", className= "" }) {
  return (
    <span
      className={`pino pino--legenda pino--${estado} ${className}`.trim()}
      aria-hidden="true"
      dangerouslySetInnerHTML={{ __html: svgSimbolo(categoria, classe, estado) }}
    />
  );
}
