import { useRef, useState } from "react";

import { enviarAnalise } from "./api.js";
import Barra from "./Barra.jsx";
import { chaveDe, ficheirosDoArrasto, resumir, tipoDe } from "./ficheiros.js";
import { formatarTamanho, lerNumero } from "./rotulos.js";

const TIPOS= { imagem: "Imagem", video: "Vídeo", gpx: "GPX" };
const MOSTRADOS= 50;

function plural(n, singular, pluralTexto) {
  return `${n} ${n === 1 ? singular : pluralTexto}`;
}

export default function ZonaDeEnvio({ aoEnviar, aoComecar }) {
  const [ficheiros, setFicheiros]= useState([]);
  const [ignorados, setIgnorados]= useState(0);
  const [aArrastar, setAArrastar]= useState(false);
  const [nome, setNome]= useState("");
  const [fps, setFps]= useState("2");
  const [desfasamento, setDesfasamento]= useState("0");
  const [progresso, setProgresso]= useState(null);
  const [erro, setErro]= useState(null);
  const [enviada, setEnviada]= useState(false);
  const entradaFicheiros= useRef(null);
  const entradaPasta= useRef(null);
  const aEnviar= progresso !== null;
  const resumo= resumir(ficheiros);
  const analisaveis= resumo.imagem + resumo.video;
  const videoSemGpx= resumo.video > 0 && resumo.gpx === 0;

  function adicionar(novos) {
    const validos= novos.filter((ficheiro) => tipoDe(ficheiro.name));
    setIgnorados((n) => n + novos.length - validos.length);
    setFicheiros((atuais) => {
      const existentes= new Set(atuais.map(chaveDe));
      return [...atuais, ...validos.filter((ficheiro) => !existentes.has(chaveDe(ficheiro)))];
    });
    setEnviada(false);
    setErro(null);
  }

  async function aoSoltar(evento) {
    evento.preventDefault();
    setAArrastar(false);
    adicionar(await ficheirosDoArrasto(evento.dataTransfer));
  }

  function aoEscolher(evento) {
    adicionar([...evento.target.files]);
    evento.target.value= "";
  }

  function remover(chave) {
    setFicheiros((atuais) => atuais.filter((ficheiro) => chaveDe(ficheiro) !== chave));
  }

  function limpar() {
    setFicheiros([]);
    setIgnorados(0);
  }

  async function enviar() {
    aoComecar?.();
    setProgresso(0);
    setErro(null);
    try {
      const resposta= await enviarAnalise(
        {
          ficheiros,
          nome,
          offsetS: lerNumero(desfasamento) || 0,
          fps: lerNumero(fps) || 2,
        },
        setProgresso,
      );
      setFicheiros([]);
      setIgnorados(0);
      setNome("");
      setEnviada(true);
      aoEnviar(resposta);
    } catch (falha) {
      setErro(falha.message);
    } finally {
      setProgresso(null);
    }
  }

  return (
    <section className="envio" aria-labelledby="titulo-envio">
      <h2 id="titulo-envio" className="envio__titulo">
        Nova análise
      </h2>
      <div
        className={aArrastar ? "zona zona--ativa" : "zona"}
        onDragOver={(evento) => {
          evento.preventDefault();
          setAArrastar(true);
        }}
        onDragLeave={() => setAArrastar(false)}
        onDrop={aoSoltar}
      >
        <p className="zona__texto">Largue aqui as fotografias e os vídeos</p>
        <p className="zona__ajuda">
          Fotografias JPG ou PNG, de preferência com GPS. Vídeos MP4, MOV, AVI ou WEBM, de preferência com o ficheiro
          GPX gravado ao mesmo tempo. Sem GPS ou sem GPX a análise corre na mesma, mas os elementos ficam sem posição
          no mapa.
        </p>
        <div className="acoes acoes--centro">
          <button type="button" className="botao" disabled={aEnviar} onClick={() => entradaFicheiros.current?.click()}>
            Escolher ficheiros
          </button>
          <button type="button" className="botao" disabled={aEnviar} onClick={() => entradaPasta.current?.click()}>
            Escolher pasta
          </button>
        </div>
        <input
          ref={entradaFicheiros}
          type="file"
          multiple
          hidden
          accept=".jpg,.jpeg,.png,.mp4,.mov,.m4v,.avi,.webm,.gpx"
          onChange={aoEscolher}
        />
        <input ref={entradaPasta} type="file" hidden webkitdirectory="" directory="" multiple onChange={aoEscolher} />
      </div>

      {enviada && (
        <p className="mensagem mensagem--ok" role="status">
          Análise enviada. Pode continuar a trabalhar: o estado aparece na lista abaixo.
        </p>
      )}
      {ignorados > 0 && (
        <p className="nota" role="status">
          {plural(ignorados, "ficheiro ignorado", "ficheiros ignorados")} por não ser imagem, vídeo ou GPX.
        </p>
      )}

      {ficheiros.length > 0 && (
        <div className="selecionados">
          <p className="selecionados__resumo">
            {[
              resumo.imagem > 0 && plural(resumo.imagem, "imagem", "imagens"),
              resumo.video > 0 && plural(resumo.video, "vídeo", "vídeos"),
              resumo.gpx > 0 && plural(resumo.gpx, "GPX", "GPX"),
            ]
              .filter(Boolean)
              .join(", ")}
            , {formatarTamanho(resumo.tamanho)}
          </p>
          {videoSemGpx && (
            <p className="aviso">
              Há vídeos sem ficheiro GPX. A análise corre na mesma, mas os elementos desses vídeos ficam sem posição no
              mapa.
            </p>
          )}
          <div className="campo">
            <label htmlFor="nome-analise">Nome da análise (opcional)</label>
            <input
              id="nome-analise"
              value={nome}
              maxLength={120}
              disabled={aEnviar}
              onChange={(evento) => setNome(evento.target.value)}
            />
          </div>
          {resumo.video > 0 && (
            <details className="opcoes">
              <summary>Opções do vídeo</summary>
              <div className="campos-par">
                <div className="campo">
                  <label htmlFor="fps">Imagens por segundo</label>
                  <input id="fps" inputMode="decimal" value={fps} disabled={aEnviar} onChange={(e) => setFps(e.target.value)} />
                </div>
                <div className="campo">
                  <label htmlFor="desfasamento">Início do vídeo face ao GPX (segundos)</label>
                  <input
                    id="desfasamento"
                    inputMode="decimal"
                    value={desfasamento}
                    disabled={aEnviar}
                    onChange={(e) => setDesfasamento(e.target.value)}
                  />
                </div>
              </div>
              <p className="nota">
                Por omissão o vídeo começa à mesma hora que o GPX. Se começou depois, indique quantos segundos.
              </p>
            </details>
          )}

          <div className="acoes">
            <button type="button" className="botao botao--principal" disabled={aEnviar || analisaveis === 0} onClick={enviar}>
              {aEnviar ? "A enviar" : "Analisar"}
            </button>
            <button type="button" className="botao botao--secundario" disabled={aEnviar} onClick={limpar}>
              Limpar
            </button>
          </div>
          {analisaveis === 0 && <p className="nota">Falta pelo menos uma imagem ou um vídeo.</p>}
          {aEnviar && progresso < 1 && (
            <Barra
              rotulo="Progresso do envio"
              valor={progresso}
              maximo={1}
              texto={`A enviar, ${Math.round(progresso * 100)}%`}
            />
          )}
          {aEnviar && progresso >= 1 && <Barra rotulo="Envio concluído" texto="A guardar os ficheiros no servidor" />}

          <ul className="selecionados__lista">
            {ficheiros.slice(0, MOSTRADOS).map((ficheiro) => (
              <li key={chaveDe(ficheiro)} className="selecionado">
                <span className="selecionado__tipo">{TIPOS[tipoDe(ficheiro.name)]}</span>
                <span className="selecionado__nome">{ficheiro.name}</span>
                <span className="selecionado__tamanho">{formatarTamanho(ficheiro.size)}</span>
                <button
                  type="button"
                  className="botao botao--secundario"
                  disabled={aEnviar}
                  aria-label={`Remover ${ficheiro.name}`}
                  onClick={() => remover(chaveDe(ficheiro))}
                >
                  Remover
                </button>
              </li>
            ))}
          </ul>
          {ficheiros.length > MOSTRADOS && (
            <p className="nota">e mais {ficheiros.length - MOSTRADOS} ficheiros que não estão na lista.</p>
          )}
        </div>
      )}
      {erro && (
        <p className="mensagem mensagem--erro" role="alert">
          {erro}
        </p>
      )}
    </section>
  );
}
