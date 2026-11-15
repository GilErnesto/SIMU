import { useCallback, useEffect, useRef, useState } from "react";

import { corrigirElemento, listarElementos, ligacaoExportacao, obterConfig, obterElemento } from "./api.js";
import Detalhe from "./Detalhe.jsx";
import Lista from "./Lista.jsx";
import Mapa from "./Mapa.jsx";
import { ESTADOS, lerNumero, percentagem, rotuloCategoria } from "./rotulos.js";

const FILTROS_INICIAIS= { categoria: "", estado: "", minObservacoes: "2", minConfianca: "" };
const FILTROS_VAZIOS= { categoria: "", estado: "", minObservacoes: "", minConfianca: "" };

function resumoExportacao(dados, filtros) {
  const partes= [];
  if (filtros.categoria) partes.push(rotuloCategoria(dados, filtros.categoria));
  if (filtros.estado) partes.push(ESTADOS[filtros.estado] ?? filtros.estado);
  if (filtros.minObservacoes) partes.push(`${filtros.minObservacoes}+ observações`);
  if (filtros.minConfianca) {
    partes.push(`confiança ≥ ${percentagem(Number(filtros.minConfianca))}`);
  }
  return partes.length ? ` (${partes.join(", ")})` : "";
}

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
  const [filtros, setFiltros]= useState(FILTROS_INICIAIS);
  const [total, setTotal]= useState(null);
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
    if (!filtros.minObservacoes && !filtros.minConfianca) {
      setTotal(null);
      return undefined;
    }
    const controlo= new AbortController();
    listarElementos({ categoria: filtros.categoria, estado: filtros.estado }, controlo.signal)
      .then((dados) => setTotal(dados.features.length))
      .catch((erro) => {
        if (erro.name !== "AbortError") setTotal(null);
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
  const temFiltros= Boolean(
    filtros.categoria || filtros.estado || filtros.minObservacoes || filtros.minConfianca,
  );
  const mostrados= lista.features.length;
  const disponiveis= total ?? mostrados;
  const sufixoExportar= resumoExportacao(dados, filtros);
  const candidataNumeros= candidata
    ? { lat: lerNumero(candidata.lat), lon: lerNumero(candidata.lon) }
    : null;

  function mostrarTodos() {
    setFiltros((atuais) => ({ ...atuais, minObservacoes: "", minConfianca: "" }));
  }

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
          <a className="botao botao--secundario" href={ligacaoExportacao("geojson", filtros)} download>
            Exportar GeoJSON{sufixoExportar}
          </a>
          <a className="botao botao--secundario" href={ligacaoExportacao("csv", filtros)} download>
            Exportar CSV{sufixoExportar}
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
        <div className="campo">
          <label htmlFor="filtro-observacoes">Mínimo de observações</label>
          <select
            id="filtro-observacoes"
            value={filtros.minObservacoes}
            onChange={(evento) => mudarFiltro("minObservacoes", evento.target.value)}
          >
            <option value="">Todos</option>
            <option value="2">2 ou mais</option>
            <option value="3">3 ou mais</option>
            <option value="5">5 ou mais</option>
            <option value="10">10 ou mais</option>
          </select>
        </div>
        <div className="campo">
          <label htmlFor="filtro-confianca">Confiança mínima</label>
          <select
            id="filtro-confianca"
            value={filtros.minConfianca}
            onChange={(evento) => mudarFiltro("minConfianca", evento.target.value)}
          >
            <option value="">Todas</option>
            <option value="0.2">20%</option>
            <option value="0.3">30%</option>
            <option value="0.5">50%</option>
            <option value="0.7">70%</option>
          </select>
        </div>
        <div className="campo campo--tecnico">
          <label htmlFor="tecnico">Técnico</label>
          <input id="tecnico" autoComplete="name" value={tecnico} onChange={(evento) => mudarTecnico(evento.target.value)} />
        </div>
        {lista.estado === "ok" && (
          <p className="filtros__resumo" role="status">
            A mostrar {mostrados} de {disponiveis} elementos.
            {mostrados < disponiveis && (
              <button type="button" className="botao botao--ligacao" onClick={mostrarTodos}>
                Mostrar todos
              </button>
            )}
          </p>
        )}
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
          aoLimpar={() => setFiltros(FILTROS_VAZIOS)}
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
