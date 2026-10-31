import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";
import { applyBrand } from "./branding";
import { ClientScopeProvider } from "./clientScope";

applyBrand();

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 5_000 } } });

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ClientScopeProvider value={null}>
          <App />
        </ClientScopeProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
