import { useCallback, useEffect, useRef, useState } from "react";

import { corrigirElemento, listarElementos, ligacaoExportacao, obterConfig, obterElemento } from "./api.js";
import Detalhe from "./Detalhe.jsx";
import Lista from "./Lista.jsx";
import Mapa from "./Mapa.jsx";
import { ESTADOS, lerNumero, rotuloCategoria } from "./rotulos.js";

const SEM_FILTROS= { categoria: "", estado: "" };

function lerTecnico() {
  try {
    return localStorage.getItem("tecnico") || "";
  } catch {
    return "";
  }
}

function guardarTecnico(valor) {
  try {
    localStorage.setItem("tecnico", valor);
  } catch {
    return;
  }
}

export default function App() {
  const [config, setConfig]= useState({ estado: "a-carregar" });
  const [lista, setLista]= useState({ estado: "a-carregar", features: [] });
  const [filtros, setFiltros]= useState(SEM_FILTROS);
  const [selecionadoId, setSelecionadoId]= useState(null);
  const [foco, setFoco]= useState(null);
  const [detalhe, setDetalhe]= useState({ estado: "a-carregar" });
  const [vista, setVista]= useState("mapa");
  const [tecnico, setTecnico]= useState(lerTecnico);
  const [modoMover, setModoMover]= useState(false);
  const [candidata, setCandidata]= useState(null);
  const [tentativaConfig, setTentativaConfig]= useState(0);
  const [tentativaLista, setTentativaLista]= useState(0);
  const [tentativaDetalhe, setTentativaDetalhe]= useState(0);
  const gatilho= useRef(null);

  useEffect(() => {
    const controlo= new AbortController();
    setConfig({ estado: "a-carregar" });
    obterConfig(controlo.signal)
      .then((dados) => setConfig({ estado: "ok", dados }))
      .catch((erro) => {
        if (erro.name !== "AbortError") setConfig({ estado: "erro", erro: erro.message });
      });
    return () => controlo.abort();
  }, [tentativaConfig]);

  useEffect(() => {
    if (config.estado === "ok") document.title= `Ctrl + F ${config.dados.nome}`;
  }, [config]);

  useEffect(() => {
    const controlo= new AbortController();
    setLista((anterior) => ({ ...anterior, estado: "a-carregar" }));
    listarElementos(filtros, controlo.signal)
      .then((dados) => setLista({ estado: "ok", features: dados.features }))
      .catch((erro) => {
        if (erro.name !== "AbortError") setLista({ estado: "erro", features: [], erro: erro.message });
      });
    return () => controlo.abort();
  }, [filtros, tentativaLista]);

  useEffect(() => {
    if (selecionadoId === null) return undefined;
    const controlo= new AbortController();
    setDetalhe({ estado: "a-carregar" });
    obterElemento(selecionadoId, controlo.signal)
      .then((dados) => setDetalhe({ estado: "ok", dados }))
      .catch((erro) => {
        if (erro.name !== "AbortError") setDetalhe({ estado: "erro", erro: erro.message });
      });
    return () => controlo.abort();
  }, [selecionadoId, tentativaDetalhe]);

  const selecionar= useCallback(
    (id, origem) => {
      gatilho.current= document.activeElement;
      setSelecionadoId(id);
      setModoMover(false);
      setCandidata(null);
      if (origem === "lista") {
        const feature= lista.features.find((f) => f.properties.id === id);
        if (feature) {
          const [lon, lat]= feature.geometry.coordinates;
          setFoco({ lat, lon });
        }
      }
    },
    [lista.features],
  );

  const fechar= useCallback(() => {
    setSelecionadoId(null);
    setModoMover(false);
    setCandidata(null);
    const anterior= gatilho.current;
    if (anterior && anterior.isConnected) anterior.focus();
  }, []);

  useEffect(() => {
    if (selecionadoId === null) return undefined;
    function aoPremir(evento) {
      if (evento.key === "Escape") fechar();
    }
    window.addEventListener("keydown", aoPremir);
    return () => window.removeEventListener("keydown", aoPremir);
  }, [selecionadoId, fechar]);

  async function guardar(corpo) {
    const dados= await corrigirElemento(selecionadoId, corpo);
    setDetalhe({ estado: "ok", dados });
    setCandidata(null);
    setModoMover(false);
    setTentativaLista((n) => n + 1);
  }

  function mudarFiltro(campo, valor) {
    setFiltros((atuais) => ({ ...atuais, [campo]: valor }));
  }

  function mudarTecnico(valor) {
    setTecnico(valor);
    guardarTecnico(valor);
  }

  if (config.estado !== "ok") {
    return (
      <main className="arranque">
        <h1>Ctrl + F</h1>
        {config.estado === "a-carregar" && <p>A carregar a configuração.</p>}
        {config.estado === "erro" && (
          <div className="mensagem mensagem--erro" role="alert">
            <p>{config.erro}</p>
            <button type="button" className="botao" onClick={() => setTentativaConfig((n) => n + 1)}>
              Tentar de novo
            </button>
          </div>
        )}
      </main>
    );
  }

  const dados= config.dados;
  const temFiltros= Boolean(filtros.categoria || filtros.estado);
  const candidataNumeros= candidata
    ? { lat: lerNumero(candidata.lat), lon: lerNumero(candidata.lon) }
    : null;

  return (
    <div className="app">
      <a className="saltar" href="#lista">
        Saltar para a lista
      </a>
      <header className="cabecalho">
        <h1 className="cabecalho__titulo">
          Ctrl + F <span className="cabecalho__lugar">{dados.nome}</span>
        </h1>
        <div className="cabecalho__exportar">
          <a className="botao botao--secundario" href={ligacaoExportacao("geojson", filtros.estado)} download>
            Exportar GeoJSON
          </a>
          <a className="botao botao--secundario" href={ligacaoExportacao("csv", filtros.estado)} download>
            Exportar CSV
          </a>
        </div>
      </header>

      <form className="filtros" onSubmit={(evento) => evento.preventDefault()}>
        <div className="campo">
          <label htmlFor="filtro-categoria">Categoria</label>
          <select id="filtro-categoria" value={filtros.categoria} onChange={(evento) => mudarFiltro("categoria", evento.target.value)}>
            <option value="">Todas</option>
            {Object.keys(dados.categorias).map((nome) => (
              <option key={nome} value={nome}>
                {rotuloCategoria(dados, nome)}
              </option>
            ))}
          </select>
        </div>
        <div className="campo">
          <label htmlFor="filtro-estado">Estado</label>
          <select id="filtro-estado" value={filtros.estado} onChange={(evento) => mudarFiltro("estado", evento.target.value)}>
            <option value="">Todos</option>
            {dados.estados.map((estado) => (
              <option key={estado} value={estado}>
                {ESTADOS[estado] ?? estado}
              </option>
            ))}
          </select>
        </div>
        <div className="campo campo--tecnico">
          <label htmlFor="tecnico">Técnico</label>
          <input id="tecnico" autoComplete="name" value={tecnico} onChange={(evento) => mudarTecnico(evento.target.value)} />
        </div>
      </form>

      <nav className="separadores" aria-label="Vista">
        <button type="button" className="botao" aria-pressed={vista === "mapa"} onClick={() => setVista("mapa")}>
          Mapa
        </button>
        <button type="button" className="botao" aria-pressed={vista === "lista"} onClick={() => setVista("lista")}>
          Lista
        </button>
      </nav>

      <main className="corpo" data-vista={vista} data-selecionado={selecionadoId !== null}>
        <Lista
          config={dados}
          lista={lista}
          selecionadoId={selecionadoId}
          temFiltros={temFiltros}
          aoSelecionar={selecionar}
          aoRepetir={() => setTentativaLista((n) => n + 1)}
          aoLimpar={() => setFiltros(SEM_FILTROS)}
        />
        <section className={modoMover ? "mapa mapa--escolher" : "mapa"} aria-label="Mapa dos elementos">
          <Mapa
            config={dados}
            features={lista.features}
            selecionadoId={selecionadoId}
            foco={foco}
            vista={vista}
            modoMover={modoMover}
            candidata={candidataNumeros}
            aoSelecionar={selecionar}
            aoEscolherPosicao={(lat, lon) => setCandidata({ lat: lat.toFixed(6), lon: lon.toFixed(6) })}
          />
        </section>
        <Detalhe
          config={dados}
          selecionadoId={selecionadoId}
          detalhe={detalhe}
          tecnico={tecnico}
          modoMover={modoMover}
          candidata={candidata}
          aoFechar={fechar}
          aoRepetir={() => setTentativaDetalhe((n) => n + 1)}
          aoGuardar={guardar}
          aoAlternarMover={() => setModoMover((ativo) => !ativo)}
          aoMudarCandidata={setCandidata}
        />
      </main>
    </div>
  );
}
