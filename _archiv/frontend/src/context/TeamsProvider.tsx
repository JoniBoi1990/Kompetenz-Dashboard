import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import * as microsoftTeams from "@microsoft/teams-js";

interface TeamsContextValue {
  inTeams: boolean;
  theme: "default" | "dark" | "contrast";
}

const TeamsContext = createContext<TeamsContextValue>({ inTeams: false, theme: "default" });

export function TeamsProvider({ children }: { children: ReactNode }) {
  const [inTeams, setInTeams] = useState(false);
  const [theme, setTheme] = useState<"default" | "dark" | "contrast">("default");

  useEffect(() => {
    microsoftTeams.app
      .initialize()
      .then(() => {
        setInTeams(true);
        return microsoftTeams.app.getContext();
      })
      .then((ctx) => {
        const t = ctx.app?.theme;
        if (t === "dark" || t === "contrast") setTheme(t);
      })
      .catch(() => {
        // Not running in Teams — fall back to browser mode
        setInTeams(false);
      });
  }, []);

  return <TeamsContext.Provider value={{ inTeams, theme }}>{children}</TeamsContext.Provider>;
}

export function useTeams() {
  return useContext(TeamsContext);
}
