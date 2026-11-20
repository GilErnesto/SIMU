import "@fontsource-variable/atkinson-hyperlegible-next";
import "leaflet/dist/leaflet.css";
import "./styles.css";
import "./layout.css";
import "./reportes.css";
import "./tema.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Toaster } from "sonner";

import Raiz from "./Raiz.jsx";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <Raiz />
    <Toaster position="top-center" richColors closeButton toastOptions={{ style: { fontFamily: "var(--fonte)" } }} />
  </StrictMode>,
);
