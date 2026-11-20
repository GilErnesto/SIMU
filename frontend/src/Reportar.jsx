import L from "leaflet";
import {
  Camera,
  Check,
  CircleCheck,
  CircleHelp,
  Images,
  LoaderCircle,
  MapPin,
  MousePointerClick,
  Plus,
  ScanSearch,
  Send,
  ShieldCheck,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { MapContainer, Marker, TileLayer, useMapEvents } from "react-leaflet";

import { criarReporte, enviarReporte, obterConfig, obterReporte } from "./api.js";
import { idCidadao } from "./armazenamento.js";
import FotoReporte from "./FotoReporte.jsx";
import { CabecalhoCidadao } from "./Navegacao.jsx";
import { Etiqueta, IconeCategoria, LinhaDoTempo, Quando } from "./ReportesUi.jsx";
import { rotuloCategoria, rotuloClasse, rotuloProblema } from "./rotulos.js";
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

export function PaginaCidadao({ children, largura= "media" }) {
  return (
    <div className="pagina pagina--cidadao">
      <CabecalhoCidadao />
      <main className={`cidadao cidadao--${largura}`}>{children}</main>
    </div>
  );
}

const PASSOS_INICIO= [
  { Icone: Camera, titulo: "Fotografe", texto: "o sinal, candeeiro ou contentor" },
  { Icone: MousePointerClick, titulo: "Toque no objeto", texto: "e diga qual é o problema" },
  { Icone: CircleCheck, titulo: "Acompanhe", texto: "e receba uma notificação quando estiver resolvido" },
];

// /reportar: take or choose a photo; it is sent at once and the worker looks for objects in it.
export function NovoReporte() {
  const [erro, setErro]= useState(null);
  const [aEnviar, setAEnviar]= useState(false);
  const camara= useRef(null);
  const galeria= useRef(null);

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
    <PaginaCidadao largura="larga">
      <div className="inicio-grelha">
      <section className="cartao cartao--destaque inicio-reporte">
        <span className="inicio-reporte__icone" aria-hidden="true">
          <Camera size={34} strokeWidth={1.9} />
        </span>
        <h1>Viu algum problema na rua?</h1>
        <p className="inicio-reporte__sub">
          Sinais danificados, candeeiros apagados, contentores cheios: tire uma fotografia e a Câmara trata do resto.
        </p>
        <input ref={camara} className="visualmente-escondido" type="file" accept="image/jpeg,image/png" capture="environment" onChange={escolher} tabIndex={-1} />
        <input ref={galeria} className="visualmente-escondido" type="file" accept="image/jpeg,image/png" onChange={escolher} tabIndex={-1} />
        <div className="inicio-reporte__botoes">
          <button type="button" className="botao-g botao-g--principal" disabled={aEnviar} onClick={() => camara.current?.click()}>
            {aEnviar ? <LoaderCircle className="a-rodar" aria-hidden="true" size={20} /> : <Camera aria-hidden="true" size={20} />}
            {aEnviar ? "A enviar a fotografia…" : "Tirar fotografia"}
          </button>
          <button type="button" className="botao-g botao-g--secundario" disabled={aEnviar} onClick={() => galeria.current?.click()}>
            <Images aria-hidden="true" size={20} />
            Escolher da galeria
          </button>
        </div>
        {erro && (
          <p className="alerta alerta--erro" role="alert">
            {erro}
          </p>
        )}
      </section>

      <div className="inicio-grelha__lado">
      <h2 className="passos-inicio__titulo">Como funciona</h2>
      <ol className="passos-inicio">
        {PASSOS_INICIO.map(({ Icone, titulo, texto }, i) => (
          <li key={titulo} className="passos-inicio__passo">
            <span className="passos-inicio__numero">{i + 1}</span>
            <Icone aria-hidden="true" size={22} />
            <span>
              <strong>{titulo}</strong> {texto}
            </span>
          </li>
        ))}
      </ol>

      <p className="nota-privacidade">
        <ShieldCheck aria-hidden="true" size={18} />
        Os rostos e as matrículas são desfocados antes de a fotografia ser guardada. A localização só serve para
        indicar onde está o problema.
      </p>
      </div>
      </div>
    </PaginaCidadao>
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
      className="cartao__mapa"
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

function Passo({ numero, titulo, feito, children }) {
  return (
    <section className="cartao passo" aria-labelledby={`passo-${numero}`}>
      <h2 id={`passo-${numero}`} className="passo__titulo">
        <span className={feito ? "passo__numero passo__numero--feito" : "passo__numero"}>
          {feito ? <Check aria-hidden="true" size={16} strokeWidth={3} /> : numero}
        </span>
        {titulo}
      </h2>
      {children}
    </section>
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
  const pronto= Boolean(categoriaEscolhida && problema);

  function nomeCaixa(caixa) {
    return rotuloClasse(config, caixa.categoria, caixa.classe);
  }

  function escolherCaixa(novo) {
    if (reporte.caixas[novo].categoria !== categoriaEscolhida) setProblema("");
    setIndice(novo);
    setSemCaixa(false);
  }

  function semAssinalar() {
    setSemCaixa(true);
    setIndice(null);
    setProblema("");
  }

  async function enviar(evento) {
    evento.preventDefault();
    if (!pronto) {
      setErro(categoriaEscolhida ? "Escolha qual é o problema." : "Toque no objeto que quer reportar.");
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

  const resumo= categoriaEscolhida
    ? [
        semCaixa ? rotuloCategoria(config, categoria) : nomeCaixa(reporte.caixas[indice]),
        problema ? rotuloProblema(config, categoriaEscolhida, problema) : null,
      ]
        .filter(Boolean)
        .join(" · ")
    : "Nenhum objeto escolhido";

  return (
    <form className="fluxo" onSubmit={enviar}>
      <header className="fluxo__cabeca">
        <h1>Novo reporte</h1>
        <p>Diga-nos o que está mal. Demora menos de um minuto.</p>
      </header>

      <div className="fluxo__colunas">
      <div className="fluxo__coluna fluxo__coluna--foto">
      <Passo numero={1} titulo="Qual é o objeto?" feito={Boolean(categoriaEscolhida)}>
        <p className="passo__ajuda">
          {reporte.caixas.length > 0
            ? `Encontrámos ${reporte.caixas.length} ${reporte.caixas.length === 1 ? "objeto" : "objetos"}. Toque na fotografia ou escolha da lista.`
            : "Não encontrámos nenhum objeto na fotografia. Escolha o tipo abaixo."}
        </p>
        <FotoReporte reporte={reporte} escolhida={semCaixa ? null : indice} aoEscolher={escolherCaixa} rotuloCaixa={nomeCaixa} />
        <div className="grelha-objetos" role="group" aria-label="Objetos na fotografia">
          {reporte.caixas.map((caixa, i) => {
            const ativo= !semCaixa && i === indice;
            return (
              <button key={i} type="button" className="objeto" aria-pressed={ativo} onClick={() => escolherCaixa(i)}>
                <span className="objeto__numero">{i + 1}</span>
                <IconeCategoria categoria={caixa.categoria} size={20} />
                <span className="objeto__texto">
                  <span className="objeto__nome">{nomeCaixa(caixa)}</span>
                  <span className="objeto__tipo">{rotuloCategoria(config, caixa.categoria)}</span>
                </span>
                {ativo && <Check className="objeto__visto" aria-hidden="true" size={18} strokeWidth={3} />}
              </button>
            );
          })}
          {reporte.caixas.length > 0 && (
            <button type="button" className="objeto objeto--outro" aria-pressed={semCaixa} onClick={semAssinalar}>
              <CircleHelp aria-hidden="true" size={20} />
              <span className="objeto__texto">
                <span className="objeto__nome">Não está assinalado</span>
                <span className="objeto__tipo">Escolho o tipo à mão</span>
              </span>
            </button>
          )}
        </div>
        {semCaixa && (
          <div className="grelha-tipos" role="radiogroup" aria-label="Tipo de objeto">
            {Object.entries(config.categorias).map(([id, c]) => (
              <button
                key={id}
                type="button"
                role="radio"
                aria-checked={categoria === id}
                className="tipo"
                onClick={() => {
                  setCategoria(id);
                  setProblema("");
                }}
              >
                <IconeCategoria categoria={id} size={26} />
                {c.rotulo}
              </button>
            ))}
          </div>
        )}
      </Passo>
      </div>

      <div className="fluxo__coluna">
      {!categoriaEscolhida && (
        <div className="cartao passo passo--espera">
          <h2 className="passo__titulo">
            <span className="passo__numero">2</span>
            Qual é o problema?
          </h2>
          <p className="passo__ajuda">Escolha primeiro o objeto na fotografia.</p>
        </div>
      )}
      {categoriaEscolhida && (
        <Passo numero={2} titulo="Qual é o problema?" feito={Boolean(problema)}>
          <div className="grelha-problemas" role="radiogroup" aria-label="Problema">
            {problemas.map((p) => (
              <label key={p.id} className="problema">
                <input type="radio" name="problema" value={p.id} checked={problema === p.id} onChange={() => setProblema(p.id)} />
                <span className="problema__marca" aria-hidden="true">
                  <Check size={14} strokeWidth={3.5} />
                </span>
                {p.rotulo}
              </label>
            ))}
          </div>
          <label className="campo-g">
            <span className="campo-g__rotulo">
              Detalhes <span className="campo-g__opcional">(opcional)</span>
            </span>
            <textarea
              rows={3}
              maxLength={1000}
              placeholder="Por exemplo: está assim desde a tempestade de ontem"
              value={descricao}
              onChange={(e) => setDescricao(e.target.value)}
            />
          </label>
        </Passo>
      )}

      {categoriaEscolhida && precisaPosicao && (
        <Passo numero={3} titulo="Onde é?" feito={Boolean(posicao)}>
          <p className="passo__ajuda">
            <MapPin aria-hidden="true" size={16} /> Não conseguimos obter a localização. Toque no mapa no sítio do
            problema (opcional, mas ajuda a encontrá-lo).
          </p>
          <EscolherNoMapa config={config} posicao={posicao} aoEscolher={setPosicao} />
        </Passo>
      )}

      <div className="barra-envio">
        <div className="barra-envio__dentro">
          <span className="barra-envio__resumo">{resumo}</span>
          <button type="submit" className="botao-g botao-g--principal" disabled={aEnviar || !pronto}>
            {aEnviar ? <LoaderCircle className="a-rodar" aria-hidden="true" size={18} /> : <Send aria-hidden="true" size={18} />}
            {aEnviar ? "A enviar…" : "Enviar reporte"}
          </button>
        </div>
        {erro && (
          <p className="alerta alerta--erro barra-envio__erro" role="alert">
            {erro}
          </p>
        )}
      </div>
      </div>
      </div>
    </form>
  );
}

function Seguimento({ config, reporte, acabado }) {
  return (
    <div className="fluxo">
      {acabado && (
        <section className="cartao sucesso" role="status">
          <span className="sucesso__icone" aria-hidden="true">
            <CircleCheck size={30} />
          </span>
          <div>
            <h1>Reporte enviado. Obrigado!</h1>
            <p>A equipa da Câmara vai analisá-lo. Recebe uma notificação sempre que o estado mudar.</p>
          </div>
        </section>
      )}
      <section className="cartao seguimento">
        <div className="seguimento__cabeca">
          <span className="seguimento__icone" aria-hidden="true">
            <IconeCategoria categoria={reporte.categoria} size={22} />
          </span>
          <div>
            {!acabado && <p className="seguimento__antes">O seu reporte</p>}
            <h2>{rotuloProblema(config, reporte.categoria, reporte.problema)}</h2>
            <p className="seguimento__sub">
              {reporte.classe ? rotuloClasse(config, reporte.categoria, reporte.classe) : rotuloCategoria(config, reporte.categoria)}
              {" · "}
              <Quando em={reporte.criado_em} />
            </p>
          </div>
          <Etiqueta estado={reporte.estado} grande />
        </div>
        {reporte.descricao && <blockquote className="seguimento__descricao">{reporte.descricao}</blockquote>}
        <div className="seguimento__colunas">
          <FotoReporte reporte={reporte} />
          <div>
            <h3 className="seguimento__titulo">Histórico</h3>
            <LinhaDoTempo eventos={reporte.eventos} />
          </div>
        </div>
      </section>
      <Ligacao para="/reportar" className="botao-g botao-g--secundario botao-g--largo">
        <Plus aria-hidden="true" size={18} />
        Reportar outro problema
      </Ligacao>
    </div>
  );
}

// /reportar/<token>: waits for the photo's objects, lets the citizen pick one, then follows the report.
export function PaginaReporte({ token }) {
  const [config, setConfig]= useState(null);
  const [reporte, setReporte]= useState(null);
  const [erro, setErro]= useState(null);
  const [acabado, setAcabado]= useState(false);

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

  if (erro) {
    return (
      <PaginaCidadao>
        <p className="alerta alerta--erro" role="alert">
          {erro}
        </p>
      </PaginaCidadao>
    );
  }
  if (!reporte || !config || reporte.estado_foto === "na_fila") {
    return (
      <PaginaCidadao>
        <section className="cartao a-analisar" role="status" aria-live="polite">
          <span className="a-analisar__icone" aria-hidden="true">
            <ScanSearch size={30} />
          </span>
          <h1>A analisar a fotografia</h1>
          <p>A procurar sinais, candeeiros e contentores. Demora só uns segundos.</p>
          <div className="a-analisar__barra" aria-hidden="true">
            <span />
          </div>
        </section>
      </PaginaCidadao>
    );
  }
  if (reporte.estado_foto === "falhou") {
    return (
      <PaginaCidadao>
        <section className="cartao">
          <p className="alerta alerta--erro" role="alert">
            Não foi possível analisar a fotografia: {reporte.erro}
          </p>
          <Ligacao para="/reportar" className="botao-g botao-g--principal">
            <Camera aria-hidden="true" size={18} />
            Tentar outra fotografia
          </Ligacao>
        </section>
      </PaginaCidadao>
    );
  }
  return (
    <PaginaCidadao largura={reporte.estado === "rascunho" ? "larga" : "media"}>
      {reporte.estado === "rascunho" ? (
        <Escolha
          config={config}
          reporte={reporte}
          aoEnviado={(dados) => {
            setReporte(dados);
            setAcabado(true);
            window.scrollTo({ top: 0, behavior: "smooth" });
          }}
        />
      ) : (
        <Seguimento config={config} reporte={reporte} acabado={acabado} />
      )}
    </PaginaCidadao>
  );
}
