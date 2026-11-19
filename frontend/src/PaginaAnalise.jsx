import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  corrigirElemento,
  juntarElementos,
  listarDuplicados,
  listarElementos,
  obterAnalise,
  obterConfig,
  obterElemento,
  separarElemento,
} from "./api.js";
import Ampliar from "./Ampliar.jsx";
import { guardar, ler } from "./armazenamento.js";
import Avaliar from "./Avaliar.jsx";
import ChipAvisos from "./ChipAvisos.jsx";
import Divisor from "./Divisor.jsx";
import Duplicados from "./Duplicados.jsx";
import { FILTROS_VAZIOS, contarFiltros } from "./Filtros.jsx";
import Fotos from "./Fotos.jsx";
import Lateral from "./Lateral.jsx";
import Mapa from "./Mapa.jsx";
import MenuExportar from "./MenuExportar.jsx";
import ProgressoDaAnalise from "./ProgressoDaAnalise.jsx";
import { Ligacao } from "./rota.js";
import { ESTADOS_ANALISE, analiseEmCurso, lerNumero } from "./rotulos.js";

const INTERVALO_MS= 3000;

function distanciaMetros(lat1, lon1, lat2, lon2) {
  const raio= 6371000;
  const rad= (graus) => (graus * Math.PI) / 180;
  const dLat= rad(lat2 - lat1);
  const dLon= rad(lon2 - lon1);
  const a= Math.sin(dLat / 2) ** 2 + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * raio * Math.asin(Math.sqrt(a));
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
  const [fotosPct, setFotosPct]= useState(() => Number(ler("simu.fotos", "38")) || 38);
  const [lateralRetraida, setLateralRetraida]= useState(() => ler("simu.lateral", "0") === "1");
  const [lateralManual, setLateralManual]= useState(null);
  const [ampliar, setAmpliar]= useState(null);
  const [filtrosAbertos, setFiltrosAbertos]= useState(false);
  const [avaliar, setAvaliar]= useState(false);
  const [tecnico, setTecnico]= useState(() => ler("tecnico", ""));
  const [modoMover, setModoMover]= useState(false);
  const [candidata, setCandidata]= useState(null);
  const [tentativaAnalise, setTentativaAnalise]= useState(0);
  const [tentativaConfig, setTentativaConfig]= useState(0);
  const [tentativaLista, setTentativaLista]= useState(0);
  const [tentativaDetalhe, setTentativaDetalhe]= useState(0);
  const [duplicados, setDuplicados]= useState({ estado: "a-carregar", pares: [] });
  const [duplicadosAbertos, setDuplicadosAbertos]= useState(false);
  const [dispensados, setDispensados]= useState(() => {
    try {
      return new Set(JSON.parse(ler(`simu.dispensados.${token}`, "[]")));
    } catch {
      return new Set();
    }
  });
  const [tentativaDuplicados, setTentativaDuplicados]= useState(0);
  const gatilho= useRef(null);
  const analise= pedido.fase === "ok" ? pedido.dados : null;
  const concluida= analise?.estado === "concluida";
  const avaliarAberto= avaliar && detalhe.estado === "ok";
  const lateralFechada= avaliarAberto ? (lateralManual ?? true) : lateralRetraida;

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

  useEffect(() => {
    if (!concluida) return undefined;
    const controlo= new AbortController();
    setDuplicados((anterior) => ({ ...anterior, estado: "a-carregar" }));
    listarDuplicados(token, controlo.signal)
      .then((dados) => setDuplicados({ estado: "ok", pares: Array.isArray(dados) ? dados : [] }))
      .catch((erro) => {
        if (erro.name !== "AbortError") setDuplicados({ estado: "erro", pares: [] });
      });
    return () => controlo.abort();
  }, [concluida, token, tentativaLista, tentativaDuplicados]);

  const paresVisiveis= useMemo(
    () => duplicados.pares.filter((par) => !dispensados.has(`${par.a}-${par.b}`)),
    [duplicados.pares, dispensados],
  );

  const duplicadosIds= useMemo(() => {
    const ids= new Set();
    paresVisiveis.forEach((par) => {
      ids.add(par.a);
      ids.add(par.b);
    });
    return ids;
  }, [paresVisiveis]);

  const vizinhos= useMemo(() => {
    if (detalhe.estado !== "ok" || !detalhe.dados.geometry) return [];
    const { categoria }= detalhe.dados.properties;
    const [lon0, lat0]= detalhe.dados.geometry.coordinates;
    return lista.features
      .filter(
        (f) =>
          f.geometry &&
          f.properties.id !== selecionadoId &&
          f.properties.categoria === categoria &&
          f.properties.estado !== "rejeitado",
      )
      .map((f) => {
        const [lon, lat]= f.geometry.coordinates;
        return { propriedades: f.properties, distancia: distanciaMetros(lat0, lon0, lat, lon) };
      })
      .filter((vizinho) => vizinho.distancia <= 15)
      .sort((a, b) => a.distancia - b.distancia)
      .map(({ propriedades: p, distancia }) => ({
        id: p.id,
        categoria: p.categoria,
        classe: p.classe,
        distancia,
        n_observacoes: p.n_observacoes,
        confianca: p.confianca,
      }));
  }, [lista.features, detalhe, selecionadoId]);

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
    setLateralManual(null);
  }, [avaliarAberto]);

  useEffect(() => {
    setAmpliar(null);
  }, [selecionadoId]);

  useEffect(() => {
    function aoPremir(evento) {
      if (evento.key !== "Escape") return;
      if (document.querySelector("dialog[open]")) return;
      if (duplicadosAbertos) {
        setDuplicadosAbertos(false);
        return;
      }
      if (avaliar) fecharAvaliar();
      else if (selecionadoId !== null) desselecionar();
    }
    window.addEventListener("keydown", aoPremir);
    return () => window.removeEventListener("keydown", aoPremir);
  }, [duplicadosAbertos, avaliar, selecionadoId, fecharAvaliar, desselecionar]);

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

  function alternarLateral() {
    if (avaliarAberto) {
      setLateralManual(!lateralFechada);
      return;
    }
    const novo= !lateralRetraida;
    setLateralRetraida(novo);
    guardar("simu.lateral", novo ? "1" : "0");
  }

  function alternarFiltros(abrir) {
    if (abrir === true) {
      if (lateralFechada) alternarLateral();
      setFiltrosAbertos(true);
    } else {
      setFiltrosAbertos((aberto) => !aberto);
    }
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

  function dispensar(par) {
    const proximos= new Set(dispensados);
    proximos.add(`${par.a}-${par.b}`);
    guardar(`simu.dispensados.${token}`, JSON.stringify([...proximos]));
    setDispensados(proximos);
  }

  async function juntar(destino, origem, autor) {
    const dados= await juntarElementos(destino, origem, autor);
    setTentativaLista((n) => n + 1);
    if (selecionadoId === destino) setDetalhe({ estado: "ok", dados });
    if (selecionadoId === origem) setSelecionadoId(destino);
  }

  async function separar(observacoes, autor) {
    const resposta= await separarElemento(selecionadoId, observacoes, autor);
    setDetalhe({ estado: "ok", dados: resposta.original });
    setTentativaLista((n) => n + 1);
  }

  function verNoMapa(par) {
    const feature= lista.features.find((f) => f.properties.id === par.a);
    if (feature?.geometry) {
      const [lon, lat]= feature.geometry.coordinates;
      setFoco({ lat, lon });
    }
    setDuplicadosAbertos(false);
    selecionar(par.a, "lista");
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
          <ChipAvisos avisos={analise.avisos} />
          <MenuExportar token={token} filtros={filtros} mostrados={lista.features.length} />
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
    <div className="analise" data-lateral={lateralFechada ? "fechada" : "aberta"} style={{ "--fotos": `${fotosPct}%` }}>
      <a className="saltar" href="#lateral">
        Saltar para a lista
      </a>
      {cabecalho}

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

      <main className="corpo" data-aba={aba} data-avaliar={avaliarAberto} data-lateral={lateralFechada ? "fechada" : "aberta"}>
        <Lateral
          config={dadosConfig}
          lista={lista}
          selecionadoId={selecionadoId}
          filtros={filtros}
          filtrosAbertos={filtrosAbertos}
          totalAnalise={analise.n_elementos}
          pares={paresVisiveis.length}
          fechada={lateralFechada}
          vazia={vazia}
          aoAlternar={alternarLateral}
          aoAlternarFiltros={alternarFiltros}
          aoMudarFiltros={mudarFiltros}
          aoLimparFiltros={() => setFiltros(FILTROS_VAZIOS)}
          aoAbrirDuplicados={() => setDuplicadosAbertos(true)}
          aoSelecionar={selecionar}
          aoRepetir={() => setTentativaLista((n) => n + 1)}
        />
        <section className="centro" aria-label="Mapa e detalhe do elemento">
          <div className="paineis">
            <section className={modoMover ? "painel-mapa mapa mapa--escolher" : "painel-mapa mapa"} aria-label="Mapa">
              <Mapa
                config={dadosConfig}
                features={lista.features}
                selecionadoId={selecionadoId}
                foco={foco}
                vista={`${fotosPct}-${aba}-${lateralFechada}`}
                modoMover={modoMover}
                candidata={candidataNumeros}
                aoSelecionar={selecionar}
                aoEscolherPosicao={(lat, lon) => setCandidata({ lat: lat.toFixed(6), lon: lon.toFixed(6) })}
                duplicadosIds={duplicadosIds}
              />
            </section>
            <Divisor valor={fotosPct} aoMudar={mudarDivisao} />
            <section className="painel-direito" data-modo={avaliarAberto ? "avaliar" : "fotos"} aria-label="Detalhe do elemento">
              <div className="abas" role="group" aria-label="Painel do elemento">
                <button type="button" className="aba" aria-pressed={!avaliarAberto} onClick={fecharAvaliar}>
                  Fotografias
                </button>
                <button
                  type="button"
                  className="aba"
                  aria-pressed={avaliarAberto}
                  disabled={selecionadoId === null}
                  onClick={abrirAvaliar}
                >
                  Avaliar
                </button>
              </div>
              {avaliarAberto ? (
                <Avaliar
                  config={dadosConfig}
                  dados={detalhe.dados}
                  tecnico={tecnico}
                  modoMover={modoMover}
                  candidata={candidata}
                  aoGuardar={guardarCorrecao}
                  aoFechar={fecharAvaliar}
                  aoAlternarMover={() => setModoMover((ativo) => !ativo)}
                  aoMudarCandidata={setCandidata}
                  vizinhos={vizinhos}
                  aoJuntar={(origem, autor) => juntar(selecionadoId, origem, autor)}
                  aoAmpliar={(indice) => setAmpliar({ indice })}
                />
              ) : (
                <Fotos
                  config={dadosConfig}
                  selecionadoId={selecionadoId}
                  detalhe={detalhe}
                  aoRepetir={() => setTentativaDetalhe((n) => n + 1)}
                  tecnico={tecnico}
                  aoMudarTecnico={mudarTecnico}
                  aoSeparar={separar}
                  aoAmpliar={(indice) => setAmpliar({ indice })}
                />
              )}
            </section>
          </div>
        </section>
      </main>
      {duplicadosAbertos && (
        <Duplicados
          config={dadosConfig}
          estado={duplicados.estado}
          pares={duplicados.pares}
          dispensados={dispensados}
          tecnico={tecnico}
          aoJuntar={juntar}
          aoDispensar={dispensar}
          aoVerNoMapa={verNoMapa}
          aoRepetir={() => setTentativaDuplicados((n) => n + 1)}
          aoFechar={() => setDuplicadosAbertos(false)}
        />
      )}
      {ampliar && detalhe.estado === "ok" && (
        <Ampliar
          observacoes={detalhe.dados.properties.observacoes}
          indice={ampliar.indice}
          aoMudar={(indice) => setAmpliar({ indice })}
          aoFechar={() => setAmpliar(null)}
        />
      )}
    </div>
  );
}
