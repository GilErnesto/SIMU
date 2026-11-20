function Icone({ tamanho= 20, children }) {
  return (
    <svg
      className="icone"
      viewBox="0 0 24 24"
      width={tamanho}
      height={tamanho}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

export function IconeFiltro(props) {
  return (
    <Icone {...props}>
      <path d="M4 5h16l-6.2 7.4V19l-3.6-1.8v-4.8z" />
    </Icone>
  );
}

export function IconeSetaEsquerda(props) {
  return (
    <Icone {...props}>
      <path d="M14.5 6.5 9 12l5.5 5.5" />
    </Icone>
  );
}

export function IconeSetaDireita(props) {
  return (
    <Icone {...props}>
      <path d="M9.5 6.5 15 12l-5.5 5.5" />
    </Icone>
  );
}

export function IconeSetaBaixo(props) {
  return (
    <Icone {...props}>
      <path d="M6.5 9.5 12 15l5.5-5.5" />
    </Icone>
  );
}

export function IconeAviso(props) {
  return (
    <Icone {...props}>
      <path d="M12 4.5 3.8 18.5h16.4z" />
      <path d="M12 10.2v3.9M12 16.9v.1" />
    </Icone>
  );
}

export function IconeExportar(props) {
  return (
    <Icone {...props}>
      <path d="M12 4v10M8 10.5l4 4 4-4M5 19h14" />
    </Icone>
  );
}

export function IconeLista(props) {
  return (
    <Icone {...props}>
      <path d="M8.5 7h11M8.5 12h11M8.5 17h11M4.5 7v.1M4.5 12v.1M4.5 17v.1" />
    </Icone>
  );
}

export function IconeDuplicados(props) {
  return (
    <Icone {...props}>
      <rect x="8.5" y="8.5" width="11" height="11" rx="2.2" />
      <path d="M15.5 8.5V6.7a2.2 2.2 0 0 0-2.2-2.2H6.7a2.2 2.2 0 0 0-2.2 2.2v6.6a2.2 2.2 0 0 0 2.2 2.2h1.8" />
    </Icone>
  );
}

export function IconeFechar(props) {
  return (
    <Icone {...props}>
      <path d="M6.5 6.5l11 11M17.5 6.5l-11 11" />
    </Icone>
  );
}

export function IconeAmpliar(props) {
  return (
    <Icone {...props}>
      <path d="M14 5h5v5M10 19H5v-5M19 5l-6 6M5 19l6-6" />
    </Icone>
  );
}
