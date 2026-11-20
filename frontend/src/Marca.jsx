import logo from "./logo.png";
import { Ligacao } from "./rota.js";

export default function Marca() {
  return (
    <Ligacao para="/" className="marca">
      <img className="marca__logo" src={logo} alt="" width="260" height="231" />
      <span>SIMU</span>
    </Ligacao>
  );
}
