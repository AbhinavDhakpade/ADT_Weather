import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { fetchDashboard, fetchDiseases, fetchFarms, fetchIrrigationRules } from "../api/client";
import { useAuth } from "./AuthContext";

const DataContext = createContext(null);

// How often the frontend silently re-fetches in the background so the UI
// reflects the backend's automatic hourly sync (advisory/scheduler.py)
// without anyone clicking "Refresh" or reloading the page. Shorter than the
// sync interval itself so a fresh sync shows up within a few minutes, not
// up to an hour late.
const AUTO_REFRESH_MS = 5 * 60 * 1000; // 5 minutes
const FARM_KEY = "agriaura_selected_farm";

export function DataProvider({ children }) {
  const { user } = useAuth();

  // The list of farms this person may look at: the server returns every farm
  // for admins, and only their own farms for farmers.
  const [farms, setFarms] = useState(() => user?.farms ?? []);
  const [selectedFarmId, setSelectedFarmId] = useState(() => {
    const saved = Number(localStorage.getItem(FARM_KEY)) || 0;
    if (user?.is_staff) return saved || 1;
    const ownIds = (user?.farms ?? []).map((f) => f.id);
    return ownIds.includes(saved) ? saved : ownIds[0] ?? user?.farm?.id ?? 1;
  });
  const farmId = selectedFarmId;

  const [dashboard, setDashboard] = useState(null);
  const [diseases, setDiseases] = useState([]);
  const [irrigationRules, setIrrigationRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const reloadFarms = useCallback(() => {
    return fetchFarms()
      .then((res) => {
        const list = res.results ?? res;
        setFarms(list);
        // If the remembered farm is not in the list, fall back to the first one.
        setSelectedFarmId((current) =>
          list.length === 0 || list.some((f) => f.id === current) ? current : list[0].id
        );
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    reloadFarms();
  }, [reloadFarms]);

  const selectFarm = useCallback((id) => {
    localStorage.setItem(FARM_KEY, String(id));
    setSelectedFarmId(Number(id));
  }, []);

  const loadAll = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setLoading(true);
    if (!silent) setError(null);
    try {
      const [dash, diseaseRes, irrigRes] = await Promise.all([
        fetchDashboard(farmId),
        fetchDiseases({ ordering: "-risk_score", farm: farmId }),
        fetchIrrigationRules(),
      ]);
      setDashboard(dash);
      setDiseases(diseaseRes.results ?? diseaseRes);
      setIrrigationRules(irrigRes.results ?? irrigRes);
      if (silent) setError(null); // a later successful silent refresh clears a prior error too
    } catch (err) {
      // A silent background refresh failing (e.g. a momentary network blip)
      // shouldn't yank the user to a full-page error screen — only an
      // explicit/initial load surfaces the error state.
      if (!silent) setError(err);
    } finally {
      if (!silent) setLoading(false);
    }
  }, [farmId]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    const interval = setInterval(() => loadAll({ silent: true }), AUTO_REFRESH_MS);
    // Also refresh the moment the tab regains focus/visibility — the common
    // case of "I switched away and came back" shouldn't need a manual click.
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") loadAll({ silent: true });
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [loadAll]);

  const value = useMemo(
    () => ({
      farmId,
      farms,
      reloadFarms,
      selectFarm,
      dashboard,
      diseases,
      irrigationRules,
      loading,
      error,
      refresh: loadAll,
    }),
    [farmId, farms, reloadFarms, selectFarm, dashboard, diseases, irrigationRules, loading, error, loadAll]
  );

  return <DataContext.Provider value={value}>{children}</DataContext.Provider>;
}

export function useAppData() {
  const ctx = useContext(DataContext);
  if (!ctx) throw new Error("useAppData must be used within DataProvider");
  return ctx;
}