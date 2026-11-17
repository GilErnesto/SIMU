export const ESTADOS= {
  auto: "Por rever",
  validado: "Validado",
  corrigido: "Corrigido",
  rejeitado: "Rejeitado",
};

export const METODOS= {
  triangulacao: "Triangulação de várias imagens",
  monocular: "Estimativa a partir de uma imagem",
};

export const FONTES= {
  mapillary: "Mapillary",
  kartaview: "KartaView",
  video: "Vídeo",
  upload: "Ficheiro enviado",
};

export const ESTADOS_ANALISE= {
  na_fila: "Na fila",
  a_processar: "A analisar",
  concluida: "Concluída",
  falhou: "Falhou",
};

export function rotuloEstado(estado) {
  return ESTADOS[estado] ?? estado;
}

export function rotuloCategoria(config, categoria) {
  return config?.categorias?.[categoria]?.rotulo ?? categoria;
}

export function rotuloClasse(config, categoria, classe) {
  const encontrada= config?.categorias?.[categoria]?.classes?.find((c) => c.id === classe);
  return encontrada?.rotulo ?? classe;
}

export function indiceCategoria(config, categoria) {
  const nomes= Object.keys(config?.categorias ?? {});
  const indice= nomes.indexOf(categoria);
  return (indice < 0 ? 0 : indice) % 3;
}

export function lerNumero(texto) {
  return Number.parseFloat(String(texto).replace(",", "."));
}

export function percentagem(valor) {
  return `${Math.round(valor * 100)}%`;
}

export function formatarData(texto) {
  if (!texto) return "data desconhecida";
  const data= new Date(texto);
  if (Number.isNaN(data.getTime())) return "data desconhecida";
  return data.toLocaleDateString("pt-PT", { year: "numeric", month: "long", day: "numeric" });
}

export function analiseEmCurso(analise) {
  return analise?.estado === "na_fila" || analise?.estado === "a_processar";
}

export function formatarDataHora(texto) {
  if (!texto) return "";
  const data= new Date(texto);
  if (Number.isNaN(data.getTime())) return "";
  return data.toLocaleString("pt-PT", { dateStyle: "medium", timeStyle: "short" });
}

export function segundosDesde(texto) {
  const instante= Date.parse(texto);
  if (Number.isNaN(instante)) return 0;
  return Math.max(0, Math.floor((Date.now() - instante) / 1000));
}

export function formatarEspera(segundos) {
  if (segundos < 90) return `${segundos} s`;
  const minutos= Math.round(segundos / 60);
  if (minutos < 60) return `${minutos} min`;
  const horas= Math.floor(minutos / 60);
  const resto= minutos % 60;
  return resto === 0 ? `${horas} h` : `${horas} h ${resto} min`;
}

export function formatarTamanho(bytes) {
  if (bytes < 1024 * 1024) return `${Math.max(Math.round(bytes / 1024), 1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}
