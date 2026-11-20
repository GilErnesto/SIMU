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

// Anonymous citizen id: no account, so reports and notifications belong to this browser.
export function idCidadao() {
  let id= ler("simu.cidadao", "");
  if (!/^[A-Za-z0-9-]{8,64}$/.test(id)) {
    const aleatorio= globalThis.crypto?.randomUUID
      ? globalThis.crypto.randomUUID()
      : Array.from({ length: 32 }, () => Math.floor(Math.random() * 16).toString(16)).join("");
    id= aleatorio;
    guardar("simu.cidadao", id);
  }
  return id;
}
