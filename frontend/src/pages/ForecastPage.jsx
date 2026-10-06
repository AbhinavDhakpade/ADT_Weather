import { useState } from "react";
import { Bar, Line } from "react-chartjs-2";
import "../utils/chartSetup";
import { chartOpts } from "../utils/chartSetup";
import { useAppSettings } from "../context/AppSettingsContext";
import { useAppData } from "../context/DataContext";
import { LoadingScreen, ErrorScreen } from "../components/common/StatusScreens";
import { formatDateLabel, formatDayName } from "../utils/helpers";

const METRIC_TABS = [
  { id: "temp", field: "temp_max_c", color: "#e07b00", labelKey: "forecast.tempC" },
  { id: "rain", field: "rainfall_mm", color: "#1e8bc3", labelKey: "forecast.rainMm" },
  { id: "hum", field: "humidity_pct", color: "#4caf78", labelKey: "forecast.humPct" },
  { id: "et0", field: "et0_mm", color: "#9c27b0", labelKey: "forecast.et0" },
  { id: "vpd", field: "vpd_kpa", color: "#f44336", labelKey: "forecast.vpdKpa" },
  { id: "gdd", field: "gdd_daily", color: "#ff9800", labelKey: "forecast.gddDaily" },
  { id: "wind", field: "wind_kmh", color: "#607d8b", labelKey: "forecast.windKmh" },
  { id: "solar", field: "solar_mj_m2", color: "#ffc107", labelKey: "forecast.solarMj" },
];

export default function ForecastPage() {
  const { t } = useAppSettings();
  const { dashboard, loading, error, refresh } = useAppData();
  const [activeTab, setActiveTab] = useState("temp");
  const [activeDay, setActiveDay] = useState(0);

  if (loading && !dashboard) return <LoadingScreen />;
  if (error) return <ErrorScreen onRetry={refresh} />;
  if (!dashboard) return null;

  const { weather_forecast } = dashboard;
  if (!weather_forecast?.length) return <LoadingScreen />;

  const tab = METRIC_TABS.find((m) => m.id === activeTab);
  const labels = weather_forecast.map((h) => formatDateLabel(h.date));

  const mainChartData = {
    labels,
    datasets: [
      {
        label: t(tab.labelKey),
        data: weather_forecast.map((h) => h[tab.field]),
        backgroundColor: tab.color + "88",
        borderColor: tab.color,
        borderWidth: 2,
        borderRadius: 8,
      },
    ],
  };

  // Simple deterministic disease-risk forecast trend derived from humidity + temp trend
  const diseaseForecast = weather_forecast.map((h) =>
    Math.min(95, Math.max(5, Math.round(h.humidity_pct * 0.7 + h.temp_max_c * 0.5 - 10)))
  );
  const diseaseFcData = {
    labels,
    datasets: [
      {
        label: "Disease Risk %",
        data: diseaseForecast,
        borderColor: "#d63230",
        backgroundColor: "#d6323020",
        tension: 0.4,
        fill: true,
        pointRadius: 4,
      },
    ],
  };

  const gddFcData = {
    labels,
    datasets: [
      {
        label: "Cum. GDD",
        data: weather_forecast.map((h) => h.gdd_cumulative),
        borderColor: "#f5a623",
        backgroundColor: "#f5a62320",
        tension: 0.4,
        fill: true,
        pointRadius: 4,
      },
    ],
  };

  return (
    <>
      <div className="section-h">
        <h2>📅 {t("forecast.title")}</h2>
      </div>

      <div className="forecast-days">
        {weather_forecast.map((h, i) => (
          <div
            key={h.date}
            className={`fday${i === activeDay ? " active" : ""}`}
            onClick={() => setActiveDay(i)}
          >
            <div className="fday-name">{formatDayName(h.date)}</div>
            <div className="fday-icon">{h.weather_icon}</div>
            <div className="fday-hi">{h.temp_max_c}°</div>
            <div className="fday-lo">{h.temp_min_c}°</div>
          </div>
        ))}
      </div>

      <div className="tab-row">
        {METRIC_TABS.map((m) => (
          <div
            key={m.id}
            className={`tab${activeTab === m.id ? " active" : ""}`}
            onClick={() => setActiveTab(m.id)}
          >
            {t(m.labelKey)}
          </div>
        ))}
      </div>
      <div className="card static">
        <div className="chart-box tall">
          <Bar data={mainChartData} options={chartOpts(false)} />
        </div>
      </div>

      <div className="grid-2 mt-16">
        <div className="card static">
          <div className="card-title">{t("forecast.diseaseRiskForecast")}</div>
          <div className="chart-box">
            <Line data={diseaseFcData} options={chartOpts(false)} />
          </div>
        </div>
        <div className="card static">
          <div className="card-title">{t("forecast.gddForecast")}</div>
          <div className="chart-box">
            <Line data={gddFcData} options={chartOpts(false)} />
          </div>
        </div>
      </div>
    </>
  );
}
