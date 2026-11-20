export function ler(chave, padrao) {
  try {
    return localStorage.getItem(chave) ?? padrao;
  } catch {
    return padrao;
  }
}

export function guardar(chave, valor) {
  try {
    localStorage.setItem(chave, valor);
  } catch {
    return;
  }
}
