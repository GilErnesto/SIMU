const BASE= "/api";

async function mensagemErro(resposta) {
  try {
    const corpo= await resposta.json();
    const detalhe= corpo.detail;
    if (typeof detalhe === "string") return detalhe;
    if (Array.isArray(detalhe)) {
      return detalhe.map((erro) => String(erro.msg).replace(/^Value error, /, "")).join(" ");
    }
  } catch {
    return `Erro ${resposta.status} do servidor.`;
  }
  return `Erro ${resposta.status} do servidor.`;
}

async function pedir(caminho, opcoes) {
  let resposta;
  try {
    resposta= await fetch(`${BASE}${caminho}`, opcoes);
  } catch (erro) {
    if (erro.name === "AbortError") throw erro;
    throw new Error("Não foi possível contactar o servidor. Confirme que a API está a correr.");
  }
  if (!resposta.ok) throw new Error(await mensagemErro(resposta));
  return resposta.json();
}

export function obterConfig(sinal) {
  return pedir("/config", { signal: sinal });
}

function parametrosDe({ analise, categoria, classe, estado, minObservacoes, minConfianca, comReportes }) {
  const parametros= new URLSearchParams();
  if (analise) parametros.set("analise", analise);
  if (categoria) parametros.set("categoria", categoria);
  if (classe) parametros.set("classe", classe);
  if (estado) parametros.set("estado", estado);
  if (minObservacoes) parametros.set("min_observacoes", minObservacoes);
  if (minConfianca) parametros.set("min_confianca", minConfianca);
  if (comReportes) parametros.set("com_reportes", "true");
  const texto= parametros.toString();
  return texto ? `?${texto}` : "";
}

export function listarElementos(filtros, sinal) {
  return pedir(`/elementos${parametrosDe(filtros)}`, { signal: sinal });
}

export function listarAnalises(sinal) {
  return pedir("/analises", { signal: sinal });
}

export function obterAnalise(token, sinal) {
  return pedir(`/analises/${encodeURIComponent(token)}`, { signal: sinal });
}

export function apagarAnalise(token) {
  return pedir(`/analises/${encodeURIComponent(token)}`, { method: "DELETE" });
}

export function criarAnaliseZona({ bbox, nome }) {
  return pedir("/analises/zona", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ bbox, nome }),
  });
}

export function listarDuplicados(token, sinal) {
  return pedir(`/analises/${encodeURIComponent(token)}/duplicados`, { signal: sinal });
}

export function enviarAnalise({ ficheiros, nome, offsetS, fps }, aoProgredir) {
  return new Promise((resolver, rejeitar) => {
    const dados= new FormData();
    ficheiros.forEach((ficheiro) => dados.append("ficheiros", ficheiro, ficheiro.name));
    dados.append("nome", nome || "");
    dados.append("offset_s", String(offsetS ?? 0));
    dados.append("fps", String(fps ?? 2));
    const pedido= new XMLHttpRequest();
    pedido.open("POST", `${BASE}/analises`);
    pedido.upload.onprogress= (evento) => {
      if (evento.lengthComputable) aoProgredir(evento.loaded / evento.total);
    };
    pedido.upload.onload= () => aoProgredir(1);
    pedido.onerror= () =>
      rejeitar(new Error("Não foi possível enviar os ficheiros. Confirme que o servidor está a correr."));
    pedido.onload= () => {
      let corpo= null;
      try {
        corpo= JSON.parse(pedido.responseText);
      } catch {
        corpo= null;
      }
      if (pedido.status === 201 && corpo) {
        resolver(corpo);
        return;
      }
      const detalhe= corpo?.detail;
      const texto= typeof detalhe === "string" ? detalhe : `Erro ${pedido.status} do servidor.`;
      rejeitar(new Error(pedido.status === 413 ? "O envio é maior do que o servidor aceita." : texto));
    };
    pedido.send(dados);
  });
}

export function obterElemento(id, sinal) {
  return pedir(`/elementos/${id}`, { signal: sinal });
}

export function corrigirElemento(id, corpo) {
  return pedir(`/elementos/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(corpo),
  });
}

export function juntarElementos(id, origem, autor) {
  return pedir(`/elementos/${id}/juntar`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ origem, autor }),
  });
}

export function separarElemento(id, observacoes, autor) {
  return pedir(`/elementos/${id}/separar`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ observacoes, autor }),
  });
}

export function ligacaoExportacao(formato, filtros) {
  return `${BASE}/export.${formato}${parametrosDe(filtros)}`;
}

// Citizen reports (backend: pipeline/catalog/reportes.py).
export function criarReporte({ foto, cidadao, lon, lat }) {
  const corpo= new FormData();
  corpo.append("foto", foto);
  corpo.append("cidadao", cidadao);
  if (Number.isFinite(lon) && Number.isFinite(lat)) {
    corpo.append("lon", String(lon));
    corpo.append("lat", String(lat));
  }
  return pedir("/reportes", { method: "POST", body: corpo });
}

export function obterReporte(token, sinal) {
  return pedir(`/reportes/${encodeURIComponent(token)}`, { signal: sinal });
}

export function enviarReporte(token, corpo) {
  return pedir(`/reportes/${encodeURIComponent(token)}/enviar`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(corpo),
  });
}

export function listarReportes(estado, categoria, sinal, analise) {
  const parametros= new URLSearchParams({ estado });
  if (categoria) parametros.set("categoria", categoria);
  if (analise) parametros.set("analise", analise);
  return pedir(`/reportes?${parametros}`, { signal: sinal });
}

export function mudarEstadoReporte(token, corpo) {
  return pedir(`/reportes/${encodeURIComponent(token)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(corpo),
  });
}

export function ligacaoReportes(formato) {
  return `${BASE}/reportes.${formato}`;
}

export function urlFotoReporte(reporte) {
  return reporte?.foto ? `${BASE}${reporte.foto}` : null;
}

export function reportesDoCidadao(cidadao, sinal) {
  return pedir(`/cidadaos/${encodeURIComponent(cidadao)}/reportes`, { signal: sinal });
}

export function notificacoesDoCidadao(cidadao, sinal) {
  return pedir(`/cidadaos/${encodeURIComponent(cidadao)}/notificacoes`, { signal: sinal });
}

export function marcarNotificacoesLidas(cidadao) {
  return pedir(`/cidadaos/${encodeURIComponent(cidadao)}/notificacoes/lidas`, { method: "POST" });
}
