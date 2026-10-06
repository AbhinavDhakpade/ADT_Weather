import { useState } from "react";
import AnimatedWeatherIcon from "./AnimatedWeatherIcon";
import { formatRelativeTime, formatTime12h, uvLevel } from "../../utils/helpers";
import { refreshWeatherNow } from "../../api/client";
import { useAppSettings } from "../../context/AppSettingsContext";

export default function WeatherHeroStrip({ todayWeather, farm, onRefreshed }) {
  const { t } = useAppSettings();
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);

  if (!todayWeather) return null;

  const uv = uvLevel(todayWeather.uv_index_max);
  const sourceLabel = {
    open_meteo: "Open-Meteo forecast",
    open_meteo_archive: "Open-Meteo (ERA5)",
    open_meteo_recent: "Open-Meteo (recent)",
    seed: "sample data",
  }[todayWeather.data_source] || todayWeather.data_source;

  const handleRefresh = async () => {
    setRefreshing(true);
    setError(null);
    try {
      await refreshWeatherNow(farm?.id || 1);
      onRefreshed?.();
    } catch (e) {
      setError(t("weatherLabels.refreshNow") + " — " + e.message);
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="wx-hero">
      <div className="wx-hero-main">
        <AnimatedWeatherIcon code={todayWeather.weather_code} size={72} />
        <div>
          <div className="wx-hero-temp">{Math.round(todayWeather.temp_max_c)}°C</div>
          <div className="wx-hero-condition">{todayWeather.condition_text || t("common.loading")}</div>
          <div className="wx-hero-feels">{t("weatherLabels.feelsLike")} {Math.round(todayWeather.feels_like_c)}°C</div>
        </div>
      </div>

      <div className="wx-hero-strip">
        {todayWeather.sunrise && (
          <div className="wx-hero-chip">
            <span>🌅</span>
            <div>
              <div className="wx-hero-chip-val">{formatTime12h(todayWeather.sunrise)}</div>
              <div className="wx-hero-chip-lbl">{t("weatherLabels.sunrise")}</div>
            </div>
          </div>
        )}
        {todayWeather.sunset && (
          <div className="wx-hero-chip">
            <span>🌇</span>
            <div>
              <div className="wx-hero-chip-val">{formatTime12h(todayWeather.sunset)}</div>
              <div className="wx-hero-chip-lbl">{t("weatherLabels.sunset")}</div>
            </div>
          </div>
        )}
        {uv && (
          <div className="wx-hero-chip">
            <span>☀️</span>
            <div>
              <div className="wx-hero-chip-val" style={{ color: uv.color }}>
                {Math.round(todayWeather.uv_index_max)} {uv.label}
              </div>
              <div className="wx-hero-chip-lbl">{t("weatherLabels.uvIndex")}</div>
            </div>
          </div>
        )}
        {todayWeather.precipitation_probability_pct !== null && todayWeather.precipitation_probability_pct !== undefined && (
          <div className="wx-hero-chip">
            <span>🌧️</span>
            <div>
              <div className="wx-hero-chip-val">{Math.round(todayWeather.precipitation_probability_pct)}%</div>
              <div className="wx-hero-chip-lbl">{t("weatherLabels.rainChance")}</div>
            </div>
          </div>
        )}
      </div>

      <div className="wx-hero-footer">
        <span className="text-xs" style={{ color: "rgba(255,255,255,.75)" }}>
          📡 {sourceLabel} · {t("weatherLabels.updatedAgo")} {formatRelativeTime(todayWeather.fetched_at) || "—"}
        </span>
        <button className="wx-refresh-btn" onClick={handleRefresh} disabled={refreshing}>
          {refreshing ? t("weatherLabels.refreshing") : t("weatherLabels.refreshNow")}
        </button>
      </div>
      {error && <div className="text-xs mt-4" style={{ color: "#ffd6d6" }}>{error}</div>}
    </div>
  );
}
