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
