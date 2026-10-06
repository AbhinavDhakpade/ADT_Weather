import axios from "axios";

// In development: VITE_API_BASE_URL is "/api" and Vite's proxy forwards it to
// Django on port 8000 — no CORS required.
// In production: point this to your server's /api path or a reverse proxy URL.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api";

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
});

// Append ?_t=<timestamp> to every GET request so the browser never
// serves a cached (stale) response for dashboard / weather / disease data.
const TOKEN_KEY = "agriaura_token";
export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (token) => localStorage.setItem(TOKEN_KEY, token);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Token ${token}`;
  if (!config.method || config.method === "get") {
    config.params = { ...config.params, _t: Date.now() };
  }
  return config;
});

// If the server says our token is no longer valid, forget it and tell the app.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && getToken()) {
      clearToken();
      window.dispatchEvent(new Event("agriaura:unauthorized"));
    }
    return Promise.reject(error);
  }
);

/* ===================== AUTH ===================== */
export const loginRequest = (username, password) =>
  api.post("/auth/login/", { username, password }).then((r) => r.data.token);
export const fetchMe = () => api.get("/auth/me/").then((r) => r.data);

/* ===================== DASHBOARD ===================== */
export const fetchDashboard = (farmId = 1) =>
  api.get("/dashboard/", { params: { farm: farmId } }).then((r) => r.data);

/* ===================== DISEASES ===================== */
export const fetchDiseases = (params = {}) =>
  api.get("/diseases/", { params: { ordering: "-risk_score", farm: 1, ...params } }).then((r) => r.data);

export const fetchDiseaseDetail = (id, farmId) =>
  api.get(`/diseases/${id}/`, { params: farmId ? { farm: farmId } : {} }).then((r) => r.data);

/* ===================== ML ===================== */
export const fetchMlStatus = () => api.get("/ml/status/").then((r) => r.data);
export const fetchIrrigationMlPrediction = (params) =>
  api.get("/ml/irrigation/", { params }).then((r) => r.data);
export const fetchYieldMlPrediction = (params) =>
  api.get("/ml/yield/", { params }).then((r) => r.data);

/* ===================== IRRIGATION ===================== */
export const fetchIrrigationRules = (params = {}) =>
  api.get("/irrigation-rules/", { params }).then((r) => r.data);

/* ===================== WEATHER ===================== */
export const fetchActualWeather = (farmId = 1, params = {}) =>
  api.get("/weather/actual/", { params: { farm: farmId, ...params } }).then((r) => r.data);

export const fetchForecastWeather = (farmId = 1, params = {}) =>
  api.get("/weather/forecast/", { params: { farm: farmId, ...params } }).then((r) => r.data);

export const refreshWeatherNow = (farmId = 1) =>
  api.post("/weather/refresh/", null, { params: { farm: farmId }, timeout: 30000 }).then((r) => r.data);

/* ===================== SCHEDULER ===================== */
export const fetchSchedulerStatus = () => api.get("/scheduler/status/").then((r) => r.data);
export const fetchSchedulerLogs = (limit = 10) =>
  api.get("/scheduler/logs/", { params: { limit } }).then((r) => r.data);
export const runSchedulerNow = () =>
  api.post("/scheduler/run-now/", null, { timeout: 30000 }).then((r) => r.data);

/* ===================== ALERTS ===================== */
export const fetchAlerts = (farmId = 1) =>
  api.get("/alerts/", { params: { farm: farmId } }).then((r) => r.data);

/* ===================== TIMELINE ===================== */
export const fetchTimeline = (farmId = 1) =>
  api.get("/timeline/", { params: { farm: farmId } }).then((r) => r.data);

/* ===================== FARM ===================== */
export const fetchFarms = () => api.get("/farms/").then((r) => r.data);
export const fetchFarm = (id) => api.get(`/farms/${id}/`).then((r) => r.data);
export const patchFarm = (id, data) => api.patch(`/farms/${id}/`, data).then((r) => r.data);


/* ===================== ADD FARMER (admin only) ===================== */
// Typed-in details -> creates the farm and a login. Returns { farm, login }.
export const addFarmerManual = (data) =>
  api.post("/farmers/add-manual/", data).then((r) => r.data);

// One or more KML files -> returns { counts, results }.
// Pass the browser's File objects; axios sets the multipart header itself.
export const addFarmersFromKml = (files) => {
  const form = new FormData();
  files.forEach((file) => form.append("kml_files", file));
  return api
    .post("/farmers/import-kml/", form, { timeout: 60000 })
    .then((r) => r.data);
};


/* ===================== HISTORY ===================== */
// range: "last20" | "7d" | "30d". farmId is optional: farmers always get their own farm.
export const fetchHistory = (range = "last20", farmId) =>
  api
    .get("/history/", { params: { range, ...(farmId ? { farm: farmId } : {}) } })
    .then((r) => r.data);

// A plain <a href> can't send the login token, so fetch the file with axios
// and hand the browser a temporary link to save it. file: "csv" | "xlsx".
export const downloadHistory = async (range, file, farmId) => {
  const res = await api.get("/history/export/", {
    params: { range, file, ...(farmId ? { farm: farmId } : {}) },
    responseType: "blob",
  });
  const match = /filename="?([^";]+)"?/.exec(res.headers["content-disposition"] || "");
  const filename = match ? match[1] : `agriaura-history.${file}`;
  const url = URL.createObjectURL(res.data);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
};
