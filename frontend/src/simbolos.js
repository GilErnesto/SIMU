const TINTA= "#15333A";
const VERMELHO= "#c1121f";
const AZUL= "#1d4ed8";
const VERDE= "#15803d";

const TRIANGULO= "M16 5 L29 27 H3 Z";
const TRIANGULO_INVERTIDO= "M3 5 H29 L16 27 Z";
const OCTOGONO= "M11 4 H21 L28 11 V21 L21 28 H11 L4 21 V11 Z";
const LOSANGO= "M16 3 L29 16 L16 29 L3 16 Z";

function tracado(d, cor, largura= 2) {
  return `<path d="${d}" fill="none" stroke="${cor}" stroke-width="${largura}" stroke-linecap="round" stroke-linejoin="round"/>`;
}

function poligono(d, fundo, aro, larguraAro) {
  return (
    `<path d="${d}" fill="${TINTA}" stroke="${TINTA}" stroke-width="${larguraAro + 2.6}" stroke-linejoin="round"/>` +
    `<path d="${d}" fill="${fundo}" stroke="${aro}" stroke-width="${larguraAro}" stroke-linejoin="round"/>`
  );
}

function circulo(raio, fundo, aro, larguraAro) {
  return (
    `<circle cx="16" cy="16" r="${raio + 1.8}" fill="${TINTA}"/>` +
    `<circle cx="16" cy="16" r="${raio}" fill="#ffffff"/>` +
    `<circle cx="16" cy="16" r="${raio - larguraAro / 2 - 0.6}" fill="${fundo}" stroke="${aro}" stroke-width="${larguraAro}"/>`
  );
}

function retangulo(x, y, largura, altura, fundo, aro= "#ffffff") {
  return (
    `<rect x="${x - 1.3}" y="${y - 1.3}" width="${largura + 2.6}" height="${altura + 2.6}" rx="4" fill="${TINTA}"/>` +
    `<rect x="${x}" y="${y}" width="${largura}" height="${altura}" rx="2.6" fill="${fundo}" stroke="${aro}" stroke-width="1.4"/>`
  );
}

const SETA_CIMA= tracado("M16 22V11M11.8 15.2L16 11l4.2 4.2", "#ffffff", 2.4);
const SETA_DIREITA= tracado("M8 16h15M19 12l4 4-4 4", "#ffffff", 2.2);

const SINAIS= {
  perigo: () => poligono(TRIANGULO, "#ffffff", VERMELHO, 3.4) + tracado("M16 13.5v7M16 23.6v.4", TINTA, 2.6),
  cedencia: () => poligono(TRIANGULO_INVERTIDO, "#ffffff", VERMELHO, 3.4),
  stop: () => poligono(OCTOGONO, VERMELHO, "#ffffff", 2) + tracado("M10.5 16H21.5", "#ffffff", 3),
  proibicao: () => circulo(12, "#ffffff", VERMELHO, 4.4),
  limite_velocidade: () =>
    circulo(12, "#ffffff", VERMELHO, 4.4) + tracado("M11 19.6a6 6 0 0 1 10 0", TINTA, 1.8) + tracado("M16 19.6l2.6-4.4", TINTA, 1.8),
  obrigacao: () => circulo(12, AZUL, AZUL, 0.1) + SETA_CIMA,
  prescricao: () => retangulo(4, 4, 24, 24, AZUL) + SETA_CIMA,
  informacao: () => retangulo(4, 4, 24, 24, AZUL) + tracado("M16 14.5v7.5M16 10.2v.4", "#ffffff", 3),
  pre_sinalizacao: () => retangulo(2.5, 8, 27, 16, AZUL) + tracado("M8 13h16M8 16h16M8 19h10", "#ffffff", 1.6),
  direcao: () => retangulo(2.5, 8, 27, 16, AZUL) + SETA_DIREITA,
  confirmacao: () => retangulo(2.5, 8, 27, 16, VERDE) + SETA_DIREITA,
  localidades: () => retangulo(2.5, 8, 27, 16, "#ffffff", TINTA) + tracado("M8 14h16M8 18h11", TINTA, 1.8),
  complementares: () => retangulo(5, 10, 22, 12, "#facc15", TINTA) + tracado("M9 13.5l5 5M15 13.5l5 5M21 13.5l3 3", TINTA, 1.6),
  painel_adicional: () => retangulo(6, 11, 20, 10, "#ffffff", TINTA) + tracado("M10 16h12", TINTA, 1.8),
  turistico: () => retangulo(2.5, 8, 27, 16, "#7c4a1e") + tracado("M11 13l5 6 5-6", "#ffffff", 1.8),
  temporaria: () => poligono(LOSANGO, "#ea580c", "#ffffff", 2) + tracado("M16 11v6.5M16 21v.4", TINTA, 2.6),
  semaforo: () =>
    `<rect x="8.2" y="1.7" width="15.6" height="28.6" rx="6.4" fill="${TINTA}"/>` +
    '<rect x="9.8" y="3.3" width="12.4" height="25.4" rx="5" fill="#1f2933"/>' +
    '<circle cx="16" cy="9" r="2.9" fill="#ef4444"/><circle cx="16" cy="16" r="2.9" fill="#f59e0b"/><circle cx="16" cy="23" r="2.9" fill="#22c55e"/>',
  outro: () =>
    `<circle cx="16" cy="16" r="13.8" fill="${TINTA}"/><circle cx="16" cy="16" r="12" fill="#6b7280" stroke="#ffffff" stroke-width="1.4"/>` +
    tracado("M12.8 12.8a3.3 3.3 0 1 1 4.7 3c-1.1.6-1.5 1.2-1.5 2.4M16 22.2v.4", "#ffffff", 2.2),
};

function emblema(variavel, glifo) {
  return (
    `<circle cx="16" cy="16" r="14.6" fill="${TINTA}"/>` +
    `<circle cx="16" cy="16" r="12.9" style="fill:var(${variavel})" stroke="#ffffff" stroke-width="1.5"/>` +
    glifo
  );
}

const LAMPADA=
  '<path d="M16 6.6a6.2 6.2 0 0 0-3.7 11.2c.7.5 1 1.1 1 1.8h5.4c0-.7.3-1.3 1-1.8A6.2 6.2 0 0 0 16 6.6z" fill="#ffffff"/>' +
  tracado("M13.4 22.2h5.2M14.5 24.6h3", "#ffffff", 1.8);

const CAIXOTE=
  tracado("M9.6 10.6h12.8M13.8 10.6V8.6h4.4v2", "#ffffff", 2) +
  '<path d="M11 12.8l.9 10.2a1.6 1.6 0 0 0 1.6 1.4h5a1.6 1.6 0 0 0 1.6-1.4l.9-10.2z" fill="#ffffff"/>' +
  tracado("M14.2 15.2v6.6M17.8 15.2v6.6", "#6d28d9", 1.4);

const CATEGORIAS= {
  iluminacao: () => emblema("--c1", LAMPADA),
  residuos: () => emblema("--c2", CAIXOTE),
};

function selo(estado) {
  if (estado === "validado") {
    return `<g transform="translate(24 24)"><circle r="6.6" fill="${VERDE}" stroke="#ffffff" stroke-width="1.6"/>${tracado("M-3 .2l2.3 2.5L3.3-2.4", "#ffffff", 1.9)}</g>`;
  }
  if (estado === "corrigido") {
    return `<g transform="translate(24 24)"><circle r="6.6" fill="#b45309" stroke="#ffffff" stroke-width="1.6"/>${tracado("M-3.2 0H3.2", "#ffffff", 2.2)}</g>`;
  }
  return "";
}

export function corpoSimbolo(categoria, classe) {
  if (categoria === "sinal") return (SINAIS[classe] ?? SINAIS.outro)();
  return (CATEGORIAS[categoria] ?? SINAIS.outro)();
}

export function svgSimbolo(categoria, classe, estado= "auto") {
  const corpo= corpoSimbolo(categoria, classe);
  const conteudo= estado === "rejeitado" ? `<g opacity="0.5">${corpo}</g><circle cx="16" cy="16" r="15" fill="none" stroke="#b42318" stroke-width="1.8" stroke-dasharray="3.2 3"/>` : corpo + selo(estado);
  return `<svg class="simbolo" viewBox="0 0 32 32" aria-hidden="true" focusable="false">${conteudo}</svg>`;
}
