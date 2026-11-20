import "@fontsource-variable/atkinson-hyperlegible-next";
import "leaflet/dist/leaflet.css";
import "./styles.css";
import "./layout.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import Raiz from "./Raiz.jsx";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <Raiz />
  </StrictMode>,
);
