import L from "leaflet";
import { useEffect, useMemo, useState } from "react";
import { MapContainer, Marker, TileLayer, useMap } from "react-leaflet";

import { ligacaoReportesCsv, listarReportes, mudarEstadoReporte, obterConfig, obterReporte } from "./api.js";
import { guardar, ler } from "./armazenamento.js";
import FotoReporte from "./FotoReporte.jsx";
import Marca from "./Marca.jsx";
import Navegacao from "./Navegacao.jsx";
import { descreverEvento, ESTADOS_REPORTE, formatarDataHora, rotuloCategoria, rotuloClasse, rotuloProblema } from "./rotulos.js";

const ORIGENS= { browser: "localização do telemóvel", exif: "GPS da fotografia", mapa: "indicada no mapa pelo cidadão" };

function icone(estado, ativo) {
  return L.divIcon({
    className: "pino-caixa",
    html: `<span class="pino pino--problema pino--reporte-${estado}${ativo ? " pino--ativo" : ""}"></span>`,
    iconSize: [44, 44],
    iconAnchor: [22, 22],
  });
}

function Enquadrar({ features, selecionado }) {
  const mapa= useMap();
  const chave= features.map((f) => f.properties.token).join(",");
  useEffect(() => {
    if (features.length === 0) return;
    const limites= L.latLngBounds(features.map((f) => [f.geometry.coordinates[1], f.geometry.coordinates[0]]));
    mapa.fitBounds(limites, { maxZoom: 18, padding: [40, 40], animate: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapa, chave]);
  useEffect(() => {
    const alvo= features.find((f) => f.properties.token === selecionado);
    if (alvo) mapa.setView([alvo.geometry.coordinates[1], alvo.geometry.coordinates[0]], Math.max(mapa.getZoom(), 17), { animate: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapa, selecionado, chave]);
  return null;
}

function titulo(config, p) {
  const problema= rotuloProblema(config, p.categoria, p.problema);
  const tipo= p.classe ? rotuloClasse(config, p.categoria, p.classe) : rotuloCategoria(config, p.categoria);
  return `${problema} (${tipo})`;
}

function Detalhe({ config, token, tecnico, aoMudar }) {
  const [reporte, setReporte]= useState(null);
  const [nota, setNota]= useState("");
  const [erro, setErro]= useState(null);
  const [aGuardar, setAGuardar]= useState(false);

  useEffect(() => {
    const controlo= new AbortController();
    setReporte(null);
    setNota("");
    setErro(null);
    obterReporte(token, controlo.signal)
      .then(setReporte)
      .catch((e) => e.name !== "AbortError" && setErro(e.message));
    return () => controlo.abort();
  }, [token]);

  async function mudar(estado) {
    if (!tecnico.trim()) {
      setErro("Indique o seu nome no campo Técnico.");
      return;
    }
    setAGuardar(true);
    setErro(null);
    try {
      const dados= await mudarEstadoReporte(token, { autor: tecnico.trim(), estado, nota: nota.trim() || null });
      setReporte(dados);
      setNota("");
      aoMudar();
    } catch (falha) {
      setErro(falha.message);
    } finally {
      setAGuardar(false);
    }
  }

  if (erro && !reporte) {
    return (
      <p className="mensagem mensagem--erro" role="alert">
        {erro}
      </p>
    );
  }
  if (!reporte) return <p className="mensagem">A carregar o reporte…</p>;
  const aberto= reporte.estado === "aberto" || reporte.estado === "em_resolucao";
  return (
    <article className="painel-reporte">
      <h2>{titulo(config, reporte)}</h2>
      <p className={`etiqueta etiqueta--${reporte.estado}`}>{ESTADOS_REPORTE[reporte.estado] ?? reporte.estado}</p>
      {reporte.descricao && <p className="painel-reporte__descricao">“{reporte.descricao}”</p>}
      <FotoReporte reporte={reporte} />
      <dl className="painel-reporte__dados">
        <dt>Recebido</dt>
        <dd>{formatarDataHora(reporte.criado_em)}</dd>
        <dt>Posição</dt>
        <dd>
          {reporte.lat === null
            ? "Desconhecida"
            : `${reporte.lat.toFixed(5)}, ${reporte.lon.toFixed(5)} (${ORIGENS[reporte.origem_posicao] ?? reporte.origem_posicao})`}
        </dd>
        <dt>No catálogo</dt>
        <dd>{reporte.elemento_id ? `Elemento n.º ${reporte.elemento_id}` : "Sem elemento correspondente a menos de 15 m"}</dd>
      </dl>

      <div className="campo">
        <label htmlFor="nota-reporte">Nota para o cidadão (opcional)</label>
        <textarea id="nota-reporte" rows={2} maxLength={1000} value={nota} onChange={(e) => setNota(e.target.value)} />
      </div>
      <div className="acoes">
        {aberto ? (
          <>
            {reporte.estado === "aberto" && (
              <button type="button" className="botao botao--secundario" disabled={aGuardar} onClick={() => mudar("em_resolucao")}>
                Em resolução
              </button>
            )}
            <button type="button" className="botao botao--principal" disabled={aGuardar} onClick={() => mudar("resolvido")}>
              Resolvido
            </button>
            <button type="button" className="botao botao--secundario" disabled={aGuardar} onClick={() => mudar("rejeitado")}>
              Não precisa de intervenção
            </button>
          </>
        ) : (
          <button type="button" className="botao botao--secundario" disabled={aGuardar} onClick={() => mudar("aberto")}>
            Reabrir
          </button>
        )}
      </div>
      {erro && (
        <p className="mensagem--erro" role="alert">
          {erro}
        </p>
      )}
      <p className="nota">O cidadão recebe uma notificação a cada mudança de estado.</p>

      <h3>Histórico</h3>
      <ol className="historico">
        {reporte.eventos.map((e, i) => (
          <li key={i}>
            <span className="historico__quando">{formatarDataHora(e.em)}</span> {descreverEvento(e)}
          </li>
        ))}
      </ol>
    </article>
  );
}

// /tecnico/reportes: the queue of citizens' reports, on a map and a list; the archive keeps the rest.
export default function PainelReportes() {
  const [config, setConfig]= useState(null);
  const [vista, setVista]= useState("abertos");
  const [categoria, setCategoria]= useState("");
  const [lista, setLista]= useState({ estado: "a-carregar", features: [] });
  const [selecionado, setSelecionado]= useState(() => new URLSearchParams(window.location.search).get("r"));
  const [tecnico, setTecnico]= useState(() => ler("tecnico", ""));
  const [versao, setVersao]= useState(0);

  useEffect(() => {
    const controlo= new AbortController();
    obterConfig(controlo.signal).then(setConfig).catch(() => {});
    return () => controlo.abort();
  }, []);

  useEffect(() => {
    const controlo= new AbortController();
    listarReportes(vista, categoria, controlo.signal)
      .then((dados) => setLista({ estado: "ok", features: dados.features }))
      .catch((e) => e.name !== "AbortError" && setLista({ estado: "erro", features: [], erro: e.message }));
    return () => controlo.abort();
  }, [vista, categoria, versao]);

  const comPosicao= useMemo(() => lista.features.filter((f) => f.geometry), [lista.features]);

  function mudarTecnico(valor) {
    setTecnico(valor);
    guardar("tecnico", valor);
  }

  if (!config) return <p className="mensagem">A carregar…</p>;
  const [lonMin, latMin, lonMax, latMax]= config.bbox;
  return (
    <div className="pagina">
      <header className="cabecalho cabecalho--simples cabecalho--inicio">
        <Marca />
        <Navegacao />
      </header>
      <div className="faixa-tecnico">
        <label htmlFor="tecnico-reportes">Técnico</label>
        <input id="tecnico-reportes" autoComplete="name" maxLength={128} value={tecnico} onChange={(e) => mudarTecnico(e.target.value)} />
        <a className="botao botao--secundario" href={ligacaoReportesCsv()} download>
          Exportar arquivo (CSV)
        </a>
      </div>
      <main className="painel-reportes">
        <section className="painel-reportes__lista" aria-labelledby="titulo-reportes">
          <h1 id="titulo-reportes">Reportes dos cidadãos</h1>
          <div className="acoes" role="group" aria-label="Que reportes mostrar">
            {[
              ["abertos", "Por tratar"],
              ["arquivo", "Arquivo"],
            ].map(([id, rotulo]) => (
              <button
                key={id}
                type="button"
                className={vista === id ? "botao" : "botao botao--secundario"}
                aria-pressed={vista === id}
                onClick={() => {
                  setVista(id);
                  setSelecionado(null);
                }}
              >
                {rotulo}
              </button>
            ))}
            <select aria-label="Categoria" value={categoria} onChange={(e) => setCategoria(e.target.value)}>
              <option value="">Todas as categorias</option>
              {Object.entries(config.categorias).map(([id, c]) => (
                <option key={id} value={id}>
                  {c.rotulo}
                </option>
              ))}
            </select>
          </div>
          <MapContainer
            className="painel-reportes__mapa"
            bounds={[
              [latMin, lonMin],
              [latMax, lonMax],
            ]}
            maxZoom={20}
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
              maxNativeZoom={19}
              maxZoom={20}
            />
            <Enquadrar features={comPosicao} selecionado={selecionado} />
            {comPosicao.map((f) => (
              <Marker
                key={f.properties.token}
                position={[f.geometry.coordinates[1], f.geometry.coordinates[0]]}
                icon={icone(f.properties.estado, f.properties.token === selecionado)}
                title={titulo(config, f.properties)}
                eventHandlers={{ click: () => setSelecionado(f.properties.token) }}
              />
            ))}
          </MapContainer>
          {lista.estado === "erro" && (
            <p className="mensagem mensagem--erro" role="alert">
              {lista.erro}
            </p>
          )}
          {lista.estado === "ok" && lista.features.length === 0 && (
            <p className="mensagem">{vista === "abertos" ? "Não há reportes por tratar." : "O arquivo está vazio."}</p>
          )}
          <ul className="lista__itens">
            {lista.features.map((f) => {
              const p= f.properties;
              return (
                <li key={p.token}>
                  <button
                    type="button"
                    className="item"
                    aria-current={p.token === selecionado ? "true" : undefined}
                    onClick={() => setSelecionado(p.token)}
                  >
                    <span className={`pino pino--legenda pino--problema pino--reporte-${p.estado}`} aria-hidden="true" />
                    <span className="item__texto">
                      <span className="item__nome">{titulo(config, p)}</span>
                      <span className="item__meta">
                        {ESTADOS_REPORTE[p.estado] ?? p.estado}, {formatarDataHora(p.criado_em)}
                        {f.geometry ? "" : ", sem posição"}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
        <section className="painel-reportes__detalhe" aria-label="Reporte escolhido">
          {selecionado ? (
            <Detalhe config={config} token={selecionado} tecnico={tecnico} aoMudar={() => setVersao((n) => n + 1)} />
          ) : (
            <p className="mensagem">Escolha um reporte na lista ou no mapa.</p>
          )}
        </section>
      </main>
    </div>
  );
}
