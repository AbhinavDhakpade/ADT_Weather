import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { getTranslation } from "../i18n/translations";

const AppSettingsContext = createContext(null);

export function AppSettingsProvider({ children }) {
  const [lang, setLang] = useState(() => localStorage.getItem("agriaura_lang") || "en");
  const [dark, setDark] = useState(() => localStorage.getItem("agriaura_dark") === "true");
  const [mode, setMode] = useState(() => localStorage.getItem("agriaura_mode") || "farmer");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  useEffect(() => {
    localStorage.setItem("agriaura_lang", lang);
  }, [lang]);

  useEffect(() => {
    localStorage.setItem("agriaura_dark", String(dark));
    if (dark) {
      document.documentElement.setAttribute("data-dark", "");
    } else {
      document.documentElement.removeAttribute("data-dark");
    }
  }, [dark]);

  useEffect(() => {
    localStorage.setItem("agriaura_mode", mode);
  }, [mode]);

  const t = useMemo(() => (path) => getTranslation(lang, path), [lang]);

  const value = useMemo(
    () => ({
      lang,
      setLang,
      dark,
      toggleDark: () => setDark((d) => !d),
      mode,
      toggleMode: () => setMode((m) => (m === "farmer" ? "expert" : "farmer")),
      sidebarCollapsed,
      toggleSidebar: () => setSidebarCollapsed((c) => !c),
      t,
    }),
    [lang, dark, mode, sidebarCollapsed, t]
  );

  return <AppSettingsContext.Provider value={value}>{children}</AppSettingsContext.Provider>;
}

export function useAppSettings() {
  const ctx = useContext(AppSettingsContext);
  if (!ctx) throw new Error("useAppSettings must be used within AppSettingsProvider");
  return ctx;
}
