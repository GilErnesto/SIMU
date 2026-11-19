import { useEffect, useState } from "react";

import ListaAnalises from "./ListaAnalises.jsx";
import ZonaDeEnvio from "./ZonaDeEnvio.jsx";
import { Ligacao } from "./rota.js";

export default function Inicio() {
  const [versao, setVersao]= useState(0);

  useEffect(() => {
    document.title= "SIMU";
  }, []);

  return (
    <div className="pagina">
      <header className="cabecalho cabecalho--simples">
        <Ligacao para="/" className="marca">
          SIMU
        </Ligacao>
      </header>
      <main className="inicio">
        <h1 className="inicio__titulo">Sistema de Identificação de Mobiliário Urbano</h1>
        <ZonaDeEnvio aoEnviar={() => setVersao((n) => n + 1)} />
        <ListaAnalises versao={versao} />
      </main>
    </div>
  );
}
