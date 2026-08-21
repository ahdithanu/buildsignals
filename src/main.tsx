import { createRoot } from "react-dom/client";
import { Analytics } from "@vercel/analytics/react";
import App from "./App.tsx";
import "./index.css";
import { initSentry } from "./sentry";

// Init before anything else so we capture errors from module-level code
// in App / its imports. No-op when VITE_SENTRY_DSN is unset (dev, tests).
initSentry();

createRoot(document.getElementById("root")!).render(
  <>
    <App />
    <Analytics />
  </>,
);
