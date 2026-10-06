import { useAppSettings } from "../../context/AppSettingsContext";

export default function WeatherMiniGrid({ todayWeather, onClick }) {
  const { t } = useAppSettings();
  if (!todayWeather) return null;

  const items = [
    { icon: "🌡️", val: `${todayWeather.temp_max_c}°C`, lbl: t("weatherLabels.temperature") },
    { icon: "💧", val: `${todayWeather.humidity_pct}%`, lbl: t("weatherLabels.humidity") },
    { icon: "🌧️", val: `${todayWeather.rainfall_mm} mm`, lbl: t("weatherLabels.rainfallToday") },
    { icon: "💨", val: `${todayWeather.wind_kmh} km/h`, lbl: t("weatherLabels.windSpeed") },
    { icon: "☀️", val: `${todayWeather.solar_mj_m2} MJ`, lbl: t("weatherLabels.solarRad") },
    { icon: "☁️", val: todayWeather.weather_icon, lbl: t("weatherLabels.cloudCover") },
  ];

  return (
    <div className="weather-mini">
      {items.map((d, i) => (
        <div className="wcard" key={i} onClick={onClick}>
          <div className="wcard-icon">{d.icon}</div>
          <div className="wcard-val">{d.val}</div>
          <div className="wcard-label">{d.lbl}</div>
        </div>
      ))}
    </div>
  );
}
