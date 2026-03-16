import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { FluentProvider, webLightTheme, webDarkTheme } from "@fluentui/react-components";

import { AuthProvider } from "./auth/AuthProvider";
import { TeamsProvider, useTeams } from "./context/TeamsProvider";
import App from "./App";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
});

function ThemedApp() {
  const { theme } = useTeams();
  return (
    <FluentProvider theme={theme === "dark" ? webDarkTheme : webLightTheme}>
      <App />
    </FluentProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        <TeamsProvider>
          <AuthProvider>
            <ThemedApp />
          </AuthProvider>
        </TeamsProvider>
      </QueryClientProvider>
    </BrowserRouter>
  </React.StrictMode>
);
