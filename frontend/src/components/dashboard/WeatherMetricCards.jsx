import { useAppSettings } from "../../context/AppSettingsContext";

export default function WeatherMetricCards({ todayWeather, baseTemp, onClick }) {
  const { t } = useAppSettings();
  if (!todayWeather) return null;

  const tempAboveAvg = (todayWeather.temp_max_c - 27).toFixed(0);
  const gddToday = (todayWeather.temp_max_c + todayWeather.temp_min_c) / 2 - baseTemp;

  return (
    <>
      <div className="card" onClick={onClick}>
        <div className="card-header">
          <span className="card-title">🌡️ {t("cards.temperature")}</span>
          <div className="card-icon gold-icon">🌡️</div>
        </div>
        <div className="card-value">
          {todayWeather.temp_max_c}
          <span className="card-unit">°C</span>
        </div>
        <div className="card-badge badge-gold">
          {tempAboveAvg >= 0 ? "+" : ""}
          {tempAboveAvg}°C above avg
        </div>
        <div className="card-sub mt-8">
          Base temp {baseTemp}°C · GDD today: +{gddToday.toFixed(0)}
        </div>
      </div>

      <div className="card" onClick={onClick}>
        <div className="card-header">
          <span className="card-title">💧 {t("cards.humidity")}</span>
          <div className="card-icon sky-icon">💧</div>
        </div>
        <div className="card-value">
          {todayWeather.humidity_pct}
          <span className="card-unit">%</span>
        </div>
        <div className="card-badge badge-sky">High · Disease Risk ↑</div>
        <div className="card-sub mt-8">VPD: {todayWeather.vpd_kpa} kPa</div>
      </div>

      <div className="card" onClick={onClick}>
        <div className="card-header">
          <span className="card-title">🌧️ {t("cards.rainfall")}</span>
          <div className="card-icon sky-icon">🌧️</div>
        </div>
        <div className="card-value">
          {todayWeather.rainfall_mm}
          <span className="card-unit">mm</span>
        </div>
        <div className="card-badge badge-sky">{t("cards.thisWeek")}</div>
        <div className="card-sub mt-8">{todayWeather.weather_icon} Today's forecast</div>
      </div>
    </>
  );
}
