import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Client, Provider, cacheExchange, fetchExchange } from "urql";
import { App } from "./App";

// `?api=fork` points the app at the preview-branch server (see README).
const api = new URLSearchParams(location.search).get("api") === "fork" ? "fork" : "main";
const client = new Client({ url: `/api/${api}/graphql`, exchanges: [cacheExchange, fetchExchange] });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Provider value={client}>
      <App withTags={api === "fork"} />
    </Provider>
  </StrictMode>,
);
