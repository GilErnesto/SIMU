import * as ToggleGroup from "@radix-ui/react-toggle-group";
import { CircleCheck, Download, Inbox, MapPinned, User, Users } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { ligacaoReportes, listarReportes, obterConfig, urlFotoReporte } from "./api.js";
import { guardar, ler } from "./armazenamento.js";
import DetalheProblema, { ABERTOS, ligacaoNoMapa, tipoProblema, tituloProblema } from "./DetalheProblema.jsx";
import Marca from "./Marca.jsx";
import { NavegacaoTecnico } from "./Navegacao.jsx";
import { Etiqueta, IconeCategoria, Quando, Vazio } from "./ReportesUi.jsx";
import { Ligacao } from "./rota.js";

function CartaoProblema({ config, f, ativo, aoEscolher }) {
  const p= f.properties;
  const foto= urlFotoReporte(p);
  const noMapa= ligacaoNoMapa(p);
  return (
    <li className="cartao-reporte__item">
      <button type="button" className="cartao-reporte" aria-current={ativo ? "true" : undefined} onClick={aoEscolher}>
        {foto ? (
          <img className="cartao-reporte__foto" src={foto} alt="" />
        ) : (
          <span className="cartao-reporte__foto meu-reporte__foto--vazia">
            <IconeCategoria categoria={p.categoria} size={22} />
          </span>
        )}
        <span className="cartao-reporte__corpo">
          <span className="cartao-reporte__titulo">{tituloProblema(config, p)}</span>
          <span className="cartao-reporte__sub">
            <IconeCategoria categoria={p.categoria} size={14} /> {tipoProblema(config, p)}
            {p.confirmacoes > 0 && (
              <span className="cartao-reporte__confirmacoes">
                <Users aria-hidden="true" size={14} /> {p.confirmacoes + 1}
              </span>
            )}
          </span>
          <span className="cartao-reporte__rodape">
            <Etiqueta estado={p.estado} />
            <span className="cartao-reporte__quando">
              <Quando em={p.criado_em} />
              {f.geometry ? "" : " · sem posição"}
            </span>
          </span>
        </span>
      </button>
      {noMapa && (
        <Ligacao para={noMapa} className="cartao-reporte__mapa" aria-label={`Ver ${tituloProblema(config, p)} no mapa`} title="Ver no mapa">
          <MapPinned aria-hidden="true" size={18} />
        </Ligacao>
      )}
    </li>
  );
}

// /tecnico/reportes: inbox of every citizen problem across analyses. The map work happens in each
// analysis (/a/<código>), where these problems also appear; "Ver no mapa" goes there.
export default function PainelReportes() {
  const [config, setConfig]= useState(null);
  const [vista, setVista]= useState("abertos");
  const [categoria, setCategoria]= useState("todas");
  const [todos, setTodos]= useState({ estado: "a-carregar", features: [] });
  const [selecionado, setSelecionado]= useState(() => new URLSearchParams(window.location.search).get("r"));
  const [tecnico, setTecnico]= useState(() => ler("tecnico", ""));
  const [versao, setVersao]= useState(0);
  const detalhe= useRef(null);

  useEffect(() => {
    document.title= "Problemas reportados - SIMU";
    const controlo= new AbortController();
    obterConfig(controlo.signal).then(setConfig).catch(() => {});
    return () => controlo.abort();
  }, []);

  useEffect(() => {
    const controlo= new AbortController();
    listarReportes("todos", null, controlo.signal)
      .then((dados) => setTodos({ estado: "ok", features: dados.features }))
      .catch((e) => e.name !== "AbortError" && setTodos({ estado: "erro", features: [], erro: e.message }));
    return () => controlo.abort();
  }, [versao]);

  const contagens= useMemo(() => {
    const abertos= todos.features.filter((f) => ABERTOS.has(f.properties.estado)).length;
    return { abertos, arquivo: todos.features.length - abertos };
  }, [todos.features]);
  const lista= useMemo(
    () =>
      todos.features.filter(
        (f) =>
          ABERTOS.has(f.properties.estado) === (vista === "abertos") &&
          (categoria === "todas" || f.properties.categoria === categoria),
      ),
    [todos.features, vista, categoria],
  );

  function escolher(token) {
    setSelecionado(token);
    window.history.replaceState({}, "", `/tecnico/reportes?r=${encodeURIComponent(token)}`);
    if (window.matchMedia("(max-width: 1023px)").matches) {
      requestAnimationFrame(() => detalhe.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
    }
  }

  function mudarTecnico(valor) {
    setTecnico(valor);
    guardar("tecnico", valor);
  }

  return (
    <div className="pagina pagina--tecnico">
      <header className="cabecalho">
        <Marca />
        <NavegacaoTecnico />
      </header>
      {!config ? (
        <p className="mensagem">A carregar…</p>
      ) : (
        <main className="tecnico">
          <div className="tecnico__topo">
            <div>
              <h1>Problemas reportados</h1>
              <p className="tecnico__resumo">
                {contagens.abertos === 0
                  ? "Não há nada por tratar."
                  : `${contagens.abertos} ${contagens.abertos === 1 ? "problema por tratar" : "problemas por tratar"}, de cidadãos de todas as zonas`}
              </p>
            </div>
            <div className="tecnico__ferramentas">
              <label className="campo-icone">
                <User aria-hidden="true" size={18} />
                <span className="visualmente-escondido">Técnico</span>
                <input
                  autoComplete="name"
                  maxLength={128}
                  placeholder="O seu nome (técnico)"
                  value={tecnico}
                  onChange={(e) => mudarTecnico(e.target.value)}
                />
              </label>
              <div className="exportar" role="group" aria-label="Exportar todos os problemas">
                <span className="exportar__rotulo">
                  <Download aria-hidden="true" size={18} /> Exportar
                </span>
                <a className="exportar__botao" href={ligacaoReportes("csv")} download>
                  CSV
                </a>
                <a className="exportar__botao" href={ligacaoReportes("geojson")} download>
                  GeoJSON
                </a>
              </div>
            </div>
          </div>

          <div className="tecnico__filtros">
            <ToggleGroup.Root
              type="single"
              className="segmentado"
              aria-label="Que problemas mostrar"
              value={vista}
              onValueChange={(valor) => valor && setVista(valor)}
            >
              <ToggleGroup.Item value="abertos" className="segmentado__item">
                Por tratar <span className="segmentado__contador">{contagens.abertos}</span>
              </ToggleGroup.Item>
              <ToggleGroup.Item value="arquivo" className="segmentado__item">
                Arquivo <span className="segmentado__contador">{contagens.arquivo}</span>
              </ToggleGroup.Item>
            </ToggleGroup.Root>
            <ToggleGroup.Root
              type="single"
              className="pilulas"
              aria-label="Categoria"
              value={categoria}
              onValueChange={(valor) => valor && setCategoria(valor)}
            >
              <ToggleGroup.Item value="todas" className="pilula">
                Todas
              </ToggleGroup.Item>
              {Object.entries(config.categorias).map(([id, c]) => (
                <ToggleGroup.Item key={id} value={id} className="pilula">
                  <IconeCategoria categoria={id} size={16} />
                  {c.rotulo}
                </ToggleGroup.Item>
              ))}
            </ToggleGroup.Root>
          </div>

          <div className="tecnico__grelha">
            <section className="tecnico__lista" aria-label="Lista de problemas">
              {todos.estado === "erro" && (
                <p className="alerta alerta--erro" role="alert">
                  {todos.erro}
                </p>
              )}
              {todos.estado === "a-carregar" && (
                <div className="cartao esqueleto" aria-label="A carregar">
                  <span />
                  <span />
                </div>
              )}
              {todos.estado === "ok" && lista.length === 0 && (
                <Vazio icone={vista === "abertos" ? CircleCheck : Inbox} titulo={vista === "abertos" ? "Tudo tratado" : "O arquivo está vazio"}>
                  {vista === "abertos" ? "Não há problemas por tratar nesta categoria." : "Os problemas resolvidos aparecem aqui."}
                </Vazio>
              )}
              <ul className="lista-reportes">
                {lista.map((f) => (
                  <CartaoProblema
                    key={f.properties.token}
                    config={config}
                    f={f}
                    ativo={f.properties.token === selecionado}
                    aoEscolher={() => escolher(f.properties.token)}
                  />
                ))}
              </ul>
            </section>
            <section className="tecnico__detalhe" ref={detalhe} aria-label="Problema escolhido">
              {selecionado ? (
                <DetalheProblema
                  config={config}
                  token={selecionado}
                  tecnico={tecnico}
                  aoMudar={() => setVersao((n) => n + 1)}
                  aoFechar={() => {
                    setSelecionado(null);
                    window.history.replaceState({}, "", "/tecnico/reportes");
                  }}
                />
              ) : (
                <Vazio icone={Inbox} titulo="Escolha um problema">
                  Veja a fotografia do cidadão e trate-o aqui, ou abra-o no mapa da análise com o botão de localização.
                </Vazio>
              )}
            </section>
          </div>
        </main>
      )}
    </div>
  );
}
