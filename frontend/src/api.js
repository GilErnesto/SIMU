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

export function listarElementos(
  { categoria, estado, minObservacoes, minConfianca },
  sinal,
) {
  const parametros= new URLSearchParams();
  if (categoria) parametros.set("categoria", categoria);
  if (estado) parametros.set("estado", estado);
  if (minObservacoes) parametros.set("min_observacoes", minObservacoes);
  if (minConfianca) parametros.set("min_confianca", minConfianca);
  const texto= parametros.toString();
  return pedir(`/elementos${texto ? `?${texto}` : ""}`, { signal: sinal });
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

export function ligacaoExportacao(
  formato,
  { categoria, estado, minObservacoes, minConfianca },
) {
  const parametros= new URLSearchParams();
  if (categoria) parametros.set("categoria", categoria);
  if (estado) parametros.set("estado", estado);
  if (minObservacoes) parametros.set("min_observacoes", minObservacoes);
  if (minConfianca) parametros.set("min_confianca", minConfianca);
  const texto= parametros.toString();
  return `${BASE}/export.${formato}${texto ? `?${texto}` : ""}`;
}
