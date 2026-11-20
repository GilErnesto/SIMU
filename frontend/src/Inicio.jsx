import { Map as MapIcone, User } from "lucide-react";
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
      <main className="inicio">
        <div className="inicio__topo">
          <div>
            <h1 className="inicio__titulo">Sistema de Identificação de Mobiliário Urbano</h1>
            <p className="inicio__sub">Envie fotografias ou vídeos, ou escolha uma zona do Mapillary, para encontrar sinais, candeeiros e contentores.</p>
          </div>
          <div className="tecnico__ferramentas">
            <label className="campo-icone">
              <User aria-hidden="true" size={18} />
              <span className="visualmente-escondido">Técnico</span>
              <input
                id="tecnico-inicio"
                autoComplete="name"
                maxLength={128}
                placeholder="O seu nome (técnico)"
                value={tecnico}
                onChange={(evento) => mudarTecnico(evento.target.value)}
              />
            </label>
            <button ref={botaoZona} type="button" className="botao-g botao-g--secundario" aria-haspopup="dialog" onClick={abrirZona}>
              <MapIcone aria-hidden="true" size={18} />
              Escolher zona no mapa
            </button>
          </div>
        </div>
        {zonaEnviada && (
          <p className="mensagem mensagem--ok" role="status">
            Zona enviada. O estado aparece na lista de análises.
          </p>
        )}
        <div className="inicio__grelha">
          <ZonaDeEnvio aoEnviar={atualizar} aoComecar={() => setZonaEnviada(false)} />
          <ListaAnalises versao={versao} />
        </div>
      </main>
      {zonaAberta && <ZonaNoMapa aoFechar={fecharZona} aoEnviar={zonaCriada} />}
    </div>
  );
}
