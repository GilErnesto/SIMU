import { useEffect, useRef, useState } from "react";

import { guardar, ler } from "./armazenamento.js";
import ListaAnalises from "./ListaAnalises.jsx";
import Marca from "./Marca.jsx";
import { NavegacaoTecnico } from "./Navegacao.jsx";
import ZonaDeEnvio from "./ZonaDeEnvio.jsx";
import ZonaNoMapa from "./ZonaNoMapa.jsx";

export default function Inicio() {
  const [versao, setVersao]= useState(0);
  const [tecnico, setTecnico]= useState(() => ler("tecnico", ""));
  const [zonaAberta, setZonaAberta]= useState(false);
  const [zonaEnviada, setZonaEnviada]= useState(false);
  const botaoZona= useRef(null);
  const devolverFoco= useRef(false);

  useEffect(() => {
    document.title= "SIMU";
  }, []);

  useEffect(() => {
    if (!zonaAberta && devolverFoco.current) {
      devolverFoco.current= false;
      botaoZona.current?.focus();
    }
  }, [zonaAberta]);

  const atualizar= () => setVersao((n) => n + 1);

  function mudarTecnico(valor) {
    setTecnico(valor);
    guardar("tecnico", valor);
  }

  function abrirZona() {
    setZonaEnviada(false);
    setZonaAberta(true);
  }

  function fecharZona() {
    devolverFoco.current= true;
    setZonaAberta(false);
  }

  function zonaCriada() {
    setZonaEnviada(true);
    fecharZona();
    atualizar();
  }

  return (
    <div className="pagina">
      <header className="cabecalho cabecalho--simples cabecalho--inicio">
        <Marca />
        <NavegacaoTecnico />
      </header>
      <div className="faixa-tecnico">
        <label htmlFor="tecnico-inicio">Técnico</label>
        <input
          id="tecnico-inicio"
          autoComplete="name"
          maxLength={128}
          value={tecnico}
          onChange={(evento) => mudarTecnico(evento.target.value)}
        />
        <button
          ref={botaoZona}
          type="button"
          className="botao faixa-tecnico__zona"
          aria-haspopup="dialog"
          onClick={abrirZona}
        >
          Escolher zona no mapa
        </button>
      </div>
      <main className="inicio">
        <h1 className="inicio__titulo">Sistema de Identificação de Mobiliário Urbano</h1>
        <ZonaDeEnvio aoEnviar={atualizar} aoComecar={() => setZonaEnviada(false)} />
        {zonaEnviada && (
          <p className="mensagem mensagem--ok" role="status">
            Zona enviada. O estado aparece na lista abaixo.
          </p>
        )}
        <ListaAnalises versao={versao} />
      </main>
      {zonaAberta && <ZonaNoMapa aoFechar={fecharZona} aoEnviar={zonaCriada} />}
    </div>
  );
}
