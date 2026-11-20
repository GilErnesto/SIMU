import { useEffect, useRef, useState } from "react";
import { MapContainer, Marker, TileLayer, useMapEvents } from "react-leaflet";
import L from "leaflet";

import { criarReporte, enviarReporte, obterConfig, obterReporte } from "./api.js";
import { idCidadao } from "./armazenamento.js";
import FotoReporte from "./FotoReporte.jsx";
import Marca from "./Marca.jsx";
import Navegacao from "./Navegacao.jsx";
import { descreverEvento, ESTADOS_REPORTE, formatarDataHora, rotuloCategoria, rotuloClasse, rotuloProblema } from "./rotulos.js";
import { ir, Ligacao } from "./rota.js";

const ESPERA_FOTO_MS= 1000;
const ICONE_LOCAL= L.divIcon({
  className: "pino-caixa",
  html: '<span class="pino pino--candidato"></span>',
  iconSize: [44, 44],
  iconAnchor: [22, 22],
});

function localizacao() {
  // Browsers only give the location on HTTPS or localhost; without it the worker tries the photo's GPS.
  return new Promise((resolver) => {
    if (!navigator.geolocation) {
      resolver(null);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (posicao) => resolver({ lon: posicao.coords.longitude, lat: posicao.coords.latitude }),
      () => resolver(null),
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 },
    );
  });
}

function Pagina({ titulo, children }) {
  return (
    <div className="pagina">
      <header className="cabecalho cabecalho--simples cabecalho--inicio">
        <Marca />
        <Navegacao />
      </header>
      <main className="reporte">
        <h1 className="reporte__titulo">{titulo}</h1>
        {children}
      </main>
    </div>
  );
}

// /reportar: take or choose a photo; it is sent at once and the worker looks for objects in it.
export function NovoReporte() {
  const [erro, setErro]= useState(null);
  const [aEnviar, setAEnviar]= useState(false);
  const entrada= useRef(null);

  async function escolher(evento) {
    const foto= evento.target.files?.[0];
    evento.target.value= "";
    if (!foto) return;
    setErro(null);
    setAEnviar(true);
    try {
      const posicao= await localizacao();
      const { token }= await criarReporte({ foto, cidadao: idCidadao(), lon: posicao?.lon, lat: posicao?.lat });
      ir(`/reportar/${token}`);
    } catch (falha) {
      setErro(falha.message);
      setAEnviar(false);
    }
  }

  return (
    <Pagina titulo="Reportar um problema">
      <p>
        Viu um sinal danificado, um candeeiro apagado ou um contentor cheio? Tire uma fotografia: o sistema encontra os
        objetos e só tem de tocar no que quer reportar.
      </p>
      <input
        ref={entrada}
        id="foto-reporte"
        className="visualmente-escondido"
        type="file"
        accept="image/jpeg,image/png"
        capture="environment"
        onChange={escolher}
      />
      <button type="button" className="botao botao--principal reporte__foto" disabled={aEnviar} onClick={() => entrada.current?.click()}>
        {aEnviar ? "A enviar a fotografia…" : "Tirar ou escolher fotografia"}
      </button>
      <p className="nota">
        Os rostos e as matrículas são desfocados antes de a fotografia ser guardada. A localização é pedida ao browser
        para indicar onde está o problema.
      </p>
      {erro && (
        <p className="mensagem mensagem--erro" role="alert">
          {erro}
        </p>
      )}
    </Pagina>
  );
}

function EscolherNoMapa({ config, posicao, aoEscolher }) {
  function Cliques() {
    useMapEvents({ click: (evento) => aoEscolher({ lat: evento.latlng.lat, lon: evento.latlng.lng }) });
    return null;
  }
  const [lonMin, latMin, lonMax, latMax]= config.bbox;
  return (
    <MapContainer
      className="reporte__mapa"
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
      <Cliques />
      {posicao && <Marker position={[posicao.lat, posicao.lon]} icon={ICONE_LOCAL} interactive={false} />}
    </MapContainer>
  );
}

function Escolha({ config, reporte, aoEnviado }) {
  const [indice, setIndice]= useState(reporte.caixas.length === 1 ? 0 : null);
  const [semCaixa, setSemCaixa]= useState(reporte.caixas.length === 0);
  const [categoria, setCategoria]= useState("");
  const [problema, setProblema]= useState("");
  const [descricao, setDescricao]= useState("");
  const [posicao, setPosicao]= useState(null);
  const [erro, setErro]= useState(null);
  const [aEnviar, setAEnviar]= useState(false);

  const categoriaEscolhida= semCaixa ? categoria : indice !== null ? reporte.caixas[indice].categoria : "";
  const problemas= config.categorias[categoriaEscolhida]?.problemas ?? [];
  const precisaPosicao= reporte.lat === null;

  function descreverCaixa(caixa) {
    return `${rotuloCategoria(config, caixa.categoria)}: ${rotuloClasse(config, caixa.categoria, caixa.classe)}`;
  }

  function escolherCaixa(novo) {
    setIndice(novo);
    setSemCaixa(false);
    if (reporte.caixas[novo].categoria !== categoriaEscolhida) setProblema("");
  }

  async function enviar(evento) {
    evento.preventDefault();
    if (!categoriaEscolhida) {
      setErro("Toque no objeto que quer reportar, ou indique o tipo.");
      return;
    }
    if (!problema) {
      setErro("Escolha qual é o problema.");
      return;
    }
    setErro(null);
    setAEnviar(true);
    try {
      const corpo= { problema, descricao: descricao.trim() || null };
      if (semCaixa) corpo.categoria= categoria;
      else corpo.indice= indice;
      if (posicao) Object.assign(corpo, posicao);
      aoEnviado(await enviarReporte(reporte.token, corpo));
    } catch (falha) {
      setErro(falha.message);
      setAEnviar(false);
    }
  }

  return (
    <form className="reporte__passos" onSubmit={enviar}>
      <section>
        <h2>1. Qual é o objeto?</h2>
        {reporte.caixas.length > 0 ? (
          <p className="nota">Toque na caixa do objeto com o problema.</p>
        ) : (
          <p className="nota">Não encontrámos nenhum objeto na fotografia. Indique o tipo abaixo.</p>
        )}
        <FotoReporte reporte={reporte} escolhida={semCaixa ? null : indice} aoEscolher={escolherCaixa} rotuloCaixa={descreverCaixa} />
        {reporte.caixas.length > 0 && (
          <ul className="reporte__objetos">
            {reporte.caixas.map((caixa, i) => (
              <li key={i}>
                <button
                  type="button"
                  className={!semCaixa && i === indice ? "botao" : "botao botao--secundario"}
                  aria-pressed={!semCaixa && i === indice}
                  onClick={() => escolherCaixa(i)}
                >
                  {i + 1}. {descreverCaixa(caixa)}
                </button>
              </li>
            ))}
            <li>
              <button
                type="button"
                className={semCaixa ? "botao" : "botao botao--secundario"}
                aria-pressed={semCaixa}
                onClick={() => {
                  setSemCaixa(true);
                  setIndice(null);
                  setProblema("");
                }}
              >
                O objeto não está assinalado
              </button>
            </li>
          </ul>
        )}
        {semCaixa && (
          <div className="campo">
            <label htmlFor="reporte-categoria">Tipo de objeto</label>
            <select
              id="reporte-categoria"
              value={categoria}
              onChange={(e) => {
                setCategoria(e.target.value);
                setProblema("");
              }}
            >
              <option value="">Escolha…</option>
              {Object.entries(config.categorias).map(([id, c]) => (
                <option key={id} value={id}>
                  {c.rotulo}
                </option>
              ))}
            </select>
          </div>
        )}
      </section>

      {categoriaEscolhida && (
        <fieldset className="reporte__problemas">
          <legend>
            <h2>2. Qual é o problema?</h2>
          </legend>
          {problemas.map((p) => (
            <label key={p.id} className="opcao">
              <input type="radio" name="problema" value={p.id} checked={problema === p.id} onChange={() => setProblema(p.id)} />
              {p.rotulo}
            </label>
          ))}
          <div className="campo">
            <label htmlFor="reporte-descricao">Detalhes (opcional)</label>
            <textarea id="reporte-descricao" rows={3} maxLength={1000} value={descricao} onChange={(e) => setDescricao(e.target.value)} />
          </div>
        </fieldset>
      )}

      {categoriaEscolhida && precisaPosicao && (
        <section>
          <h2>3. Onde é?</h2>
          <p className="nota">
            Não conseguimos obter a localização. Toque no mapa no sítio do problema (opcional, mas ajuda o técnico a
            encontrá-lo).
          </p>
          <EscolherNoMapa config={config} posicao={posicao} aoEscolher={setPosicao} />
        </section>
      )}

      {erro && (
        <p className="mensagem mensagem--erro" role="alert">
          {erro}
        </p>
      )}
      <button type="submit" className="botao botao--principal" disabled={aEnviar}>
        {aEnviar ? "A enviar…" : "Enviar reporte"}
      </button>
    </form>
  );
}

function Seguimento({ config, reporte }) {
  return (
    <section className="reporte__seguimento">
      <p className={`etiqueta etiqueta--${reporte.estado}`}>{ESTADOS_REPORTE[reporte.estado] ?? reporte.estado}</p>
      <p>
        <strong>{rotuloProblema(config, reporte.categoria, reporte.problema)}</strong>
        {reporte.classe ? `, ${rotuloClasse(config, reporte.categoria, reporte.classe)}` : `, ${rotuloCategoria(config, reporte.categoria)}`}
      </p>
      {reporte.descricao && <p>{reporte.descricao}</p>}
      <FotoReporte reporte={reporte} />
      <h2>Histórico</h2>
      <ol className="historico">
        {reporte.eventos.map((e, i) => (
          <li key={i}>
            <span className="historico__quando">{formatarDataHora(e.em)}</span> {descreverEvento(e)}
          </li>
        ))}
      </ol>
      <p className="nota">Quando o reporte mudar de estado, recebe uma notificação em Notificações.</p>
    </section>
  );
}

// /reportar/<token>: waits for the photo's objects, lets the citizen pick one, then follows the report.
export function PaginaReporte({ token }) {
  const [config, setConfig]= useState(null);
  const [reporte, setReporte]= useState(null);
  const [erro, setErro]= useState(null);
  const [enviado, setEnviado]= useState(false);

  useEffect(() => {
    const controlo= new AbortController();
    obterConfig(controlo.signal).then(setConfig).catch((e) => e.name !== "AbortError" && setErro(e.message));
    return () => controlo.abort();
  }, []);

  useEffect(() => {
    const controlo= new AbortController();
    let temporizador;
    function carregar() {
      obterReporte(token, controlo.signal)
        .then((dados) => {
          setReporte(dados);
          if (dados.estado_foto === "na_fila") temporizador= setTimeout(carregar, ESPERA_FOTO_MS);
        })
        .catch((e) => e.name !== "AbortError" && setErro(e.message));
    }
    carregar();
    return () => {
      controlo.abort();
      clearTimeout(temporizador);
    };
  }, [token]);

  let conteudo;
  if (erro) {
    conteudo= (
      <p className="mensagem mensagem--erro" role="alert">
        {erro}
      </p>
    );
  } else if (!reporte || !config) {
    conteudo= <p className="mensagem">A carregar…</p>;
  } else if (reporte.estado_foto === "na_fila") {
    conteudo= (
      <p className="mensagem" role="status">
        A procurar sinais, candeeiros e contentores na fotografia…
      </p>
    );
  } else if (reporte.estado_foto === "falhou") {
    conteudo= (
      <div className="mensagem mensagem--erro" role="alert">
        <p>Não foi possível analisar a fotografia: {reporte.erro}</p>
        <Ligacao para="/reportar" className="botao">
          Tentar outra fotografia
        </Ligacao>
      </div>
    );
  } else if (reporte.estado === "rascunho") {
    conteudo= (
      <Escolha
        config={config}
        reporte={reporte}
        aoEnviado={(dados) => {
          setReporte(dados);
          setEnviado(true);
        }}
      />
    );
  } else {
    conteudo= (
      <>
        {enviado && (
          <p className="mensagem mensagem--ok" role="status">
            Reporte enviado. Obrigado! Pode acompanhá-lo nesta página.
          </p>
        )}
        <Seguimento config={config} reporte={reporte} />
      </>
    );
  }
  return <Pagina titulo={reporte?.estado && reporte.estado !== "rascunho" ? "O seu reporte" : "Reportar um problema"}>{conteudo}</Pagina>;
}
