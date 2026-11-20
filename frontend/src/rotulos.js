export const ESTADOS= {
  auto: "Por rever",
  validado: "Validado",
  corrigido: "Corrigido",
  rejeitado: "Rejeitado",
};

export const METODOS= {
  triangulacao: "Triangulação de várias imagens",
  monocular: "Estimativa a partir de uma imagem",
  manual: "Indicada pelo técnico",
};

export const FONTES= {
  mapillary: "Mapillary",
  kartaview: "KartaView",
  video: "Vídeo",
  upload: "Ficheiro enviado",
  cidadao: "Reporte de um cidadão",
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

export const ESTADOS_REPORTE= {
  aberto: "Por tratar",
  em_resolucao: "Em resolução",
  resolvido: "Resolvido",
  rejeitado: "Sem intervenção",
  rascunho: "Por enviar",
};

// One line of a report's history: what happened, by whom, and the note.
export function descreverEvento(evento) {
  const doCidadao= evento.autor === "cidadão";
  const acoes= {
    rascunho: "Fotografia enviada",
    aberto: doCidadao ? "Reporte enviado" : "Reaberto",
    em_resolucao: "Em resolução",
    resolvido: "Resolvido",
    rejeitado: "Considerado sem necessidade de intervenção",
  };
  const acao= acoes[evento.estado] ?? evento.estado;
  const quem= doCidadao ? "" : ` por ${evento.autor}`;
  const nota= evento.nota && evento.nota !== acao && evento.estado !== "rascunho" ? `: ${evento.nota}` : "";
  return `${acao}${quem}${nota}`;
}

export function rotuloProblema(config, categoria, problema) {
  return config?.categorias?.[categoria]?.problemas?.find((p) => p.id === problema)?.rotulo ?? problema;
}
