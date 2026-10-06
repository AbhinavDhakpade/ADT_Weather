import { useEffect, useState } from "react";
import { useAppSettings } from "../context/AppSettingsContext";
import { useAppData } from "../context/DataContext";
import { downloadHistory, fetchHistory } from "../api/client";

const RANGES = [
  { key: "last20", label: "Last 20 readings" },
  { key: "7d", label: "Last 7 days" },
  { key: "30d", label: "Last 30 days" },
];

// [field in the API response, column heading]
const FARMER_COLUMNS = [
  ["date", "Date"],
  ["condition_text", "Weather"],
  ["temp_max_c", "Max °C"],
  ["temp_min_c", "Min °C"],
  ["rainfall_mm", "Rain mm"],
  ["humidity_pct", "Humidity %"],
  ["wind_kmh", "Wind km/h"],
];
const EXPERT_COLUMNS = [
  ["et0_mm", "ET₀ mm"],
  ["vpd_kpa", "VPD kPa"],
  ["solar_mj_m2", "Solar MJ/m²"],
  ["gdd_daily", "GDD"],
  ["gdd_cumulative", "GDD total"],
];

function formatCell(key, value) {
  if (value === null || value === undefined || value === "") return "–";
  if (key === "date") {
    return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  }
  if (key === "condition_text") return value;
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(1) : String(value);
}

export default function HistoryPage() {
  const { mode } = useAppSettings();
  const { farmId, dashboard } = useAppData();

  const [range, setRange] = useState("last20");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [downloading, setDownloading] = useState("");
  const [downloadError, setDownloadError] = useState(false);

  useEffect(() => {
    let ignore = false; // drop answers that arrive after the person switched tab/farm
    setLoading(true);
    setError(false);
    fetchHistory(range, farmId)
      .then((res) => {
        if (!ignore) setData(res);
      })
      .catch(() => {
        if (!ignore) setError(true);
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });
    return () => {
      ignore = true;
    };
  }, [range, farmId, reloadKey]);

  const onDownload = async (file) => {
    setDownloading(file);
    setDownloadError(false);
    try {
      await downloadHistory(range, file, farmId);
    } catch {
      setDownloadError(true);
    } finally {
      setDownloading("");
    }
  };

  const columns = mode === "expert" ? [...FARMER_COLUMNS, ...EXPERT_COLUMNS] : FARMER_COLUMNS;
  const rows = data?.results ?? [];
  const farmerName = data?.farm?.farmer_name ?? dashboard?.farm?.farmer_name;

  return (
    <>
      <div className="section-h">
        <h2>🕘 Weather History{farmerName ? ` – ${farmerName}` : ""}</h2>
      </div>

      <div className="card static" style={{ marginBottom: 20 }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: 12,
            marginBottom: 14,
          }}
        >
          <div className="tab-row" style={{ marginBottom: 0 }}>
            {RANGES.map((r) => (
              <button
                key={r.key}
                className={`tab${range === r.key ? " active" : ""}`}
                onClick={() => setRange(r.key)}
              >
                {r.label}
              </button>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              className="btn-primary"
              disabled={rows.length === 0 || downloading !== ""}
              onClick={() => onDownload("csv")}
            >
              {downloading === "csv" ? "Preparing…" : "⬇ CSV"}
            </button>
            <button
              className="btn-primary"
              disabled={rows.length === 0 || downloading !== ""}
              onClick={() => onDownload("xlsx")}
            >
              {downloading === "xlsx" ? "Preparing…" : "⬇ Excel"}
            </button>
          </div>
        </div>

        {downloadError && (
          <div role="alert" style={{ color: "#c0392b", fontSize: 13, marginBottom: 10 }}>
            Could not download the file. Please try again.
          </div>
        )}

        {error ? (
          <div className="text-muted">
            Could not load the history.{" "}
            <button className="btn-primary" onClick={() => setReloadKey((k) => k + 1)}>
              Retry
            </button>
          </div>
        ) : loading && !data ? (
          <div className="text-muted">Loading…</div>
        ) : rows.length === 0 ? (
          <div className="text-muted">No weather readings are stored for this farm yet.</div>
        ) : (
          <div className="scroll-x" style={{ opacity: loading ? 0.6 : 1 }}>
            <table className="data-table">
              <thead>
                <tr>
                  {columns.map(([key, label]) => (
                    <th key={key}>{label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.date}>
                    {columns.map(([key]) => (
                      <td key={key}>{formatCell(key, row[key])}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="card-sub" style={{ marginTop: 12 }}>
          {rows.length > 0 && `${rows.length} reading${rows.length === 1 ? "" : "s"}, newest first. `}
          Observed weather is published about 2 days late, so the newest row is usually 2–3 days old.
          Downloads always include every column.
        </div>
      </div>
    </>
  );
}
