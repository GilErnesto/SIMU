import { useCallback, useEffect, useRef, useState } from "react";

import {
  corrigirElemento,
  ligacaoExportacao,
  listarElementos,
  obterAnalise,
  obterConfig,
  obterElemento,
} from "./api.js";
import Avaliar from "./Avaliar.jsx";
import Divisor from "./Divisor.jsx";
import Filtros, { FILTROS_VAZIOS, contarFiltros } from "./Filtros.jsx";
import Fotos from "./Fotos.jsx";
import ListaElementos from "./ListaElementos.jsx";
import Mapa from "./Mapa.jsx";
import ProgressoDaAnalise from "./ProgressoDaAnalise.jsx";
import { Ligacao } from "./rota.js";
import { ESTADOS_ANALISE, analiseEmCurso, lerNumero } from "./rotulos.js";

const INTERVALO_MS= 3000;

function ler(chave, padrao) {
  try {
    return localStorage.getItem(chave) ?? padrao;
  } catch {
    return padrao;
  }
}

function guardar(chave, valor) {
  try {
    localStorage.setItem(chave, valor);
  } catch {
    return;
  }
}

function Avisos({ avisos }) {
  if (!avisos || avisos.length === 0) return null;
  return (
    <section className="avisos" aria-labelledby="titulo-avisos">
      <h3 id="titulo-avisos" className="bloco__titulo">
        Avisos
      </h3>
      <ul>
        {avisos.map((aviso) => (
          <li key={aviso}>{aviso}</li>
        ))}
      </ul>
    </section>
  );
}

function EstadoDaAnalise({ analise }) {
  const falhou= analise.estado === "falhou";
  return (
    <main className="estado-analise">
      <h2 className="painel__titulo">{falhou ? "A análise falhou" : "A análise está em curso"}</h2>
      <ProgressoDaAnalise analise={analise} />
      {analiseEmCurso(analise) && (
        <p>
          Esta página atualiza-se sozinha. Pode fechá-la ou voltar ao início e enviar outra análise: a análise
          continua e fica na lista da página inicial.
        </p>
      )}
      {falhou && <p className="mensagem--erro">{analise.erro || "Sem detalhe do erro."}</p>}
      <Avisos avisos={analise.avisos} />
      <Ligacao para="/" className="botao">
        Voltar ao início
      </Ligacao>
    </main>
  );
}

export default function PaginaAnalise({ token }) {
  const [pedido, setPedido]= useState({ fase: "a-carregar" });
  const [config, setConfig]= useState({ fase: "a-carregar" });
  const [filtros, setFiltros]= useState(FILTROS_VAZIOS);
  const [lista, setLista]= useState({ estado: "a-carregar", features: [] });
  const [selecionadoId, setSelecionadoId]= useState(null);
  const [foco, setFoco]= useState(null);
  const [detalhe, setDetalhe]= useState({ estado: "a-carregar" });
  const [aba, setAba]= useState("mapa");
  const [fotosPct, setFotosPct]= useState(() => Number(ler("simu.fotos", "50")) || 50);
  const [filtrosAbertos, setFiltrosAbertos]= useState(false);
  const [avaliar, setAvaliar]= useState(false);
  const [tecnico, setTecnico]= useState(() => ler("tecnico", ""));
  const [modoMover, setModoMover]= useState(false);
  const [candidata, setCandidata]= useState(null);
  const [tentativaAnalise, setTentativaAnalise]= useState(0);
  const [tentativaConfig, setTentativaConfig]= useState(0);
  const [tentativaLista, setTentativaLista]= useState(0);
  const [tentativaDetalhe, setTentativaDetalhe]= useState(0);
  const gatilho= useRef(null);
  const analise= pedido.fase === "ok" ? pedido.dados : null;
  const concluida= analise?.estado === "concluida";

  useEffect(() => {
    let parado= false;
    let temporizador;
    const controlo= new AbortController();
    async function carregar() {
      try {
        const dados= await obterAnalise(token, controlo.signal);
        if (parado) return;
        setPedido({ fase: "ok", dados });
        if (analiseEmCurso(dados)) temporizador= setTimeout(carregar, INTERVALO_MS);
      } catch (erro) {
        if (erro.name !== "AbortError" && !parado) setPedido({ fase: "erro", erro: erro.message });
      }
    }
    carregar();
    return () => {
      parado= true;
      clearTimeout(temporizador);
      controlo.abort();
    };
  }, [token, tentativaAnalise]);

  useEffect(() => {
    const controlo= new AbortController();
    obterConfig(controlo.signal)
      .then((dados) => setConfig({ fase: "ok", dados }))
      .catch((erro) => {
        if (erro.name !== "AbortError") setConfig({ fase: "erro", erro: erro.message });
      });
    return () => controlo.abort();
  }, [tentativaConfig]);

  useEffect(() => {
    if (analise) document.title= `${analise.nome} - SIMU`;
  }, [analise?.nome]);

  useEffect(() => {
    if (!concluida) return undefined;
    const controlo= new AbortController();
    setLista((anterior) => ({ ...anterior, estado: "a-carregar" }));
    listarElementos({ ...filtros, analise: token }, controlo.signal)
      .then((dados) => setLista({ estado: "ok", features: dados.features }))
      .catch((erro) => {
        if (erro.name !== "AbortError") setLista({ estado: "erro", features: [], erro: erro.message });
      });
    return () => controlo.abort();
  }, [concluida, token, filtros, tentativaLista]);

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

  const fecharAvaliar= useCallback(() => {
    setAvaliar(false);
    setModoMover(false);
    setCandidata(null);
    const anterior= gatilho.current;
    if (anterior && anterior.isConnected) anterior.focus();
  }, []);

  const desselecionar= useCallback(() => {
    setSelecionadoId(null);
    setAvaliar(false);
    setModoMover(false);
    setCandidata(null);
  }, []);

  useEffect(() => {
    function aoPremir(evento) {
      if (evento.key !== "Escape") return;
      if (filtrosAbertos) setFiltrosAbertos(false);
      else if (avaliar) fecharAvaliar();
      else if (selecionadoId !== null) desselecionar();
    }
    window.addEventListener("keydown", aoPremir);
    return () => window.removeEventListener("keydown", aoPremir);
  }, [filtrosAbertos, avaliar, selecionadoId, fecharAvaliar, desselecionar]);

  const selecionar= useCallback(
    (id, origem) => {
      gatilho.current= document.activeElement;
      setSelecionadoId(id);
      setAvaliar(false);
      setModoMover(false);
      setCandidata(null);
      setAba("fotos");
      if (origem === "lista") {
        const feature= lista.features.find((f) => f.properties.id === id);
        if (feature?.geometry) {
          const [lon, lat]= feature.geometry.coordinates;
          setFoco({ lat, lon });
        }
      }
    },
    [lista.features],
  );

  function abrirAvaliar() {
    gatilho.current= document.activeElement;
    setAvaliar(true);
  }

  async function guardarCorrecao(corpo) {
    const dados= await corrigirElemento(selecionadoId, corpo);
    setDetalhe({ estado: "ok", dados });
    setCandidata(null);
    setModoMover(false);
    setTentativaLista((n) => n + 1);
  }

  function mudarFiltros(alteracao) {
    setFiltros((atuais) => ({ ...atuais, ...alteracao }));
  }

  function mudarTecnico(valor) {
    setTecnico(valor);
    guardar("tecnico", valor);
  }

  function mudarDivisao(valor) {
    setFotosPct(valor);
    guardar("simu.fotos", String(valor));
  }

  const cabecalho= (
    <header className="cabecalho">
      <Ligacao para="/" className="marca">
        SIMU
      </Ligacao>
      {analise && (
        <div className="cabecalho__titulo">
          <h1>{analise.nome}</h1>
          <span className={`estado estado--${analise.estado}`}>{ESTADOS_ANALISE[analise.estado]}</span>
        </div>
      )}
      {concluida && config.fase === "ok" && (
        <div className="cabecalho__acoes">
          <button
            type="button"
            className="botao"
            aria-expanded={filtrosAbertos}
            aria-controls="painel-filtros"
            onClick={() => setFiltrosAbertos((aberto) => !aberto)}
          >
            Filtros{contarFiltros(filtros) > 0 ? ` (${contarFiltros(filtros)})` : ""}
          </button>
          <a className="botao botao--secundario" href={ligacaoExportacao("geojson", { ...filtros, analise: token })} download>
            Exportar GeoJSON
          </a>
          <a className="botao botao--secundario" href={ligacaoExportacao("csv", { ...filtros, analise: token })} download>
            Exportar CSV
          </a>
        </div>
      )}
    </header>
  );

  if (pedido.fase === "a-carregar") {
    return (
      <div className="pagina">
        {cabecalho}
        <main className="estado-analise">
          <p className="mensagem">A carregar a análise.</p>
        </main>
      </div>
    );
  }
  if (pedido.fase === "erro") {
    return (
      <div className="pagina">
        {cabecalho}
        <main className="estado-analise">
          <div className="mensagem mensagem--erro" role="alert">
            <p>{pedido.erro}</p>
            <div className="acoes">
              <button type="button" className="botao" onClick={() => setTentativaAnalise((n) => n + 1)}>
                Tentar de novo
              </button>
              <Ligacao para="/" className="botao botao--secundario">
                Voltar ao início
              </Ligacao>
            </div>
          </div>
        </main>
      </div>
    );
  }
  if (!concluida) {
    return (
      <div className="pagina">
        {cabecalho}
        <EstadoDaAnalise analise={analise} />
      </div>
    );
  }
  if (config.fase !== "ok") {
    return (
      <div className="pagina">
        {cabecalho}
        <main className="estado-analise">
          {config.fase === "a-carregar" ? (
            <p className="mensagem">A carregar a configuração.</p>
          ) : (
            <div className="mensagem mensagem--erro" role="alert">
              <p>{config.erro}</p>
              <button type="button" className="botao" onClick={() => setTentativaConfig((n) => n + 1)}>
                Tentar de novo
              </button>
            </div>
          )}
        </main>
      </div>
    );
  }

  const dadosConfig= config.dados;
  const candidataNumeros= candidata ? { lat: lerNumero(candidata.lat), lon: lerNumero(candidata.lon) } : null;
  const vazia= analise.n_elementos === 0
    ? "Esta análise não encontrou elementos. Veja os avisos para perceber porquê."
    : "Sem elementos para mostrar.";

  return (
    <div className="analise" style={{ "--fotos": `${fotosPct}%` }}>
      <a className="saltar" href="#lista">
        Saltar para a lista
      </a>
      {cabecalho}
      {filtrosAbertos && (
        <Filtros
          config={dadosConfig}
          filtros={filtros}
          mostrados={lista.features.length}
          total={analise.n_elementos}
          aoMudar={mudarFiltros}
          aoLimpar={() => setFiltros(FILTROS_VAZIOS)}
          aoFechar={() => setFiltrosAbertos(false)}
        />
      )}
      {analise.avisos.length > 0 && (
        <details className="faixa-avisos" open={analise.avisos.some((aviso) => aviso.includes("GPS indisponível"))}>
          <summary>
            {analise.avisos.length} {analise.avisos.length === 1 ? "aviso" : "avisos"} desta análise
          </summary>
          <Avisos avisos={analise.avisos} />
        </details>
      )}

      <nav className="separadores" aria-label="Vista">
        {[
          ["lista", "Lista"],
          ["mapa", "Mapa"],
          ["fotos", "Fotografias"],
        ].map(([valor, texto]) => (
          <button key={valor} type="button" className="botao" aria-pressed={aba === valor} onClick={() => setAba(valor)}>
            {texto}
          </button>
        ))}
      </nav>

      {avaliar && modoMover && (
        <div className="faixa-mover" role="status">
          <span>Clique no mapa para escolher a nova posição.</span>
          <button type="button" className="botao" onClick={() => setModoMover(false)}>
            Concluir
          </button>
        </div>
      )}

      <main className="corpo" data-aba={aba} data-avaliar={avaliar && detalhe.estado === "ok"}>
        <ListaElementos
          config={dadosConfig}
          lista={lista}
          selecionadoId={selecionadoId}
          temFiltros={contarFiltros(filtros) > 0}
          vazia={vazia}
          aoSelecionar={selecionar}
          aoRepetir={() => setTentativaLista((n) => n + 1)}
          aoLimpar={() => setFiltros(FILTROS_VAZIOS)}
        />
        <section className="centro" aria-label="Mapa e fotografias">
          <div className="paineis">
            <section className={modoMover ? "painel-mapa mapa mapa--escolher" : "painel-mapa mapa"} aria-label="Mapa">
              <Mapa
                config={dadosConfig}
                features={lista.features}
                selecionadoId={selecionadoId}
                foco={foco}
                vista={`${fotosPct}-${aba}`}
                modoMover={modoMover}
                candidata={candidataNumeros}
                aoSelecionar={selecionar}
                aoEscolherPosicao={(lat, lon) => setCandidata({ lat: lat.toFixed(6), lon: lon.toFixed(6) })}
              />
              {lista.estado === "ok" && lista.features.length > 0 && !lista.features.some((f) => f.geometry) && (
                <p className="mapa__aviso" role="status">
                  Nenhum elemento tem posição, porque as fotografias não têm GPS. A lista e as fotografias continuam
                  disponíveis, e pode indicar a posição de cada elemento ao avaliá-lo.
                </p>
              )}
            </section>
            <Divisor valor={fotosPct} aoMudar={mudarDivisao} />
            <Fotos
              config={dadosConfig}
              selecionadoId={selecionadoId}
              detalhe={detalhe}
              aoAvaliar={abrirAvaliar}
              aoRepetir={() => setTentativaDetalhe((n) => n + 1)}
            />
          </div>
        </section>
        {avaliar && detalhe.estado === "ok" && (
          <Avaliar
            config={dadosConfig}
            dados={detalhe.dados}
            tecnico={tecnico}
            modoMover={modoMover}
            candidata={candidata}
            aoMudarTecnico={mudarTecnico}
            aoGuardar={guardarCorrecao}
            aoFechar={fecharAvaliar}
            aoAlternarMover={() => setModoMover((ativo) => !ativo)}
            aoMudarCandidata={setCandidata}
          />
        )}
      </main>
    </div>
  );
}
