const IMAGENS= [".jpg", ".jpeg", ".png"];
const VIDEOS= [".mp4", ".mov", ".m4v", ".avi", ".webm"];
const GPX= [".gpx"];

export function tipoDe(nome) {
  const minusculas= nome.toLowerCase();
  const termina= (lista) => lista.some((sufixo) => minusculas.endsWith(sufixo));
  if (termina(IMAGENS)) return "imagem";
  if (termina(VIDEOS)) return "video";
  if (termina(GPX)) return "gpx";
  return null;
}

export function chaveDe(ficheiro) {
  return `${ficheiro.name}|${ficheiro.size}|${ficheiro.lastModified}`;
}

async function lerEntrada(entrada) {
  if (entrada.isFile) {
    return [await new Promise((resolver, rejeitar) => entrada.file(resolver, rejeitar))];
  }
  const leitor= entrada.createReader();
  const filhos= [];
  for (;;) {
    const lote= await new Promise((resolver, rejeitar) => leitor.readEntries(resolver, rejeitar));
    if (lote.length === 0) break;
    filhos.push(...lote);
  }
  const listas= await Promise.all(filhos.map(lerEntrada));
  return listas.flat();
}

export async function ficheirosDoArrasto(transferencia) {
  const entradas= [...transferencia.items]
    .filter((item) => item.kind === "file")
    .map((item) => item.webkitGetAsEntry?.())
    .filter(Boolean);
  if (entradas.length === 0) return [...transferencia.files];
  const listas= await Promise.all(entradas.map(lerEntrada));
  return listas.flat();
}

export function resumir(ficheiros) {
  const contagem= { imagem: 0, video: 0, gpx: 0 };
  let tamanho= 0;
  for (const ficheiro of ficheiros) {
    const tipo= tipoDe(ficheiro.name);
    if (tipo) contagem[tipo]+= 1;
    tamanho+= ficheiro.size;
  }
  return { ...contagem, tamanho };
}
