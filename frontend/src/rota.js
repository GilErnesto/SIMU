import { createElement, useEffect, useState } from "react";

export function useCaminho() {
  const [caminho, setCaminho]= useState(window.location.pathname);
  useEffect(() => {
    const aoMudar= () => setCaminho(window.location.pathname);
    window.addEventListener("popstate", aoMudar);
    return () => window.removeEventListener("popstate", aoMudar);
  }, []);
  return caminho;
}

export function ir(destino) {
  window.history.pushState({}, "", destino);
  window.dispatchEvent(new PopStateEvent("popstate"));
  window.scrollTo(0, 0);
}

export function Ligacao({ para, children, ...resto }) {
  function aoClicar(evento) {
    if (evento.metaKey || evento.ctrlKey || evento.shiftKey || evento.altKey || evento.button !== 0) return;
    evento.preventDefault();
    ir(para);
  }
  return createElement("a", { href: para, onClick: aoClicar, ...resto }, children);
}

export function tokenDaRota(caminho) {
  const encontrado= caminho.match(/^\/a\/([A-Za-z0-9_-]+)\/?$/);
  return encontrado ? encontrado[1] : null;
}
