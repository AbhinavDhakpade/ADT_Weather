import { useState } from "react";
import { useAppSettings } from "../context/AppSettingsContext";
import { useAppData } from "../context/DataContext";
import { LoadingScreen, ErrorScreen } from "../components/common/StatusScreens";
import WeatherHeroStrip from "../components/weather/WeatherHeroStrip";
import WeatherTimelineStrip from "../components/weather/WeatherTimelineStrip";
import DayDetailPopover from "../components/weather/DayDetailPopover";
import WeatherMiniGrid from "../components/dashboard/WeatherMiniGrid";
import TempHumidityChart from "../components/weather/TempHumidityChart";
import { VpdHumidityChart, RainfallBarChart, SolarWindChart } from "../components/weather/MiscWeatherCharts";
import WeatherModal from "../components/modals/WeatherModal";
import { windArrowRotation } from "../utils/helpers";

export default function WeatherPage() {
  const { t, mode } = useAppSettings();
  const { dashboard, loading, error, refresh } = useAppData();
  const [weatherOpen, setWeatherOpen] = useState(false);
  const [activeDay, setActiveDay] = useState(0);
  const [popoverDay, setPopoverDay] = useState(null);
  const isExpert = mode === "expert";

  if (loading && !dashboard) return <LoadingScreen />;
  if (error) return <ErrorScreen onRetry={refresh} />;
  if (!dashboard) return null;

  const { today_weather, weather_history, weather_forecast, farm } = dashboard;

  // Build the 7-day outlook: today first, then forecast days (already exclude today from backend)
  // Guard against today_weather being null or a past date (if sync hasn't run today)
  const timelineDays = [
    today_weather,
    ...weather_forecast.filter((d) => d.date !== today_weather?.date),
  ].filter(Boolean);

  return (
    <>
      <div className="section-h">
        <h2>☁️ {t("pageTitles.weather")} – {farm.village}</h2>
      </div>

      <WeatherHeroStrip todayWeather={today_weather} farm={farm} onRefreshed={refresh} />

      <div className="card static mb-16" style={{ marginBottom: 20 }}>
        <div className="card-title mb-12">7-Day Outlook</div>
        <WeatherTimelineStrip days={timelineDays} activeIndex={activeDay} onSelect={setActiveDay} />
      </div>

      <WeatherMiniGrid todayWeather={today_weather} onClick={() => setWeatherOpen(true)} />

      {today_weather?.wind_direction_deg !== null && today_weather?.wind_direction_deg !== undefined && (
        <div className="card static mt-16">
          <div className="card-title">💨 Wind</div>
          <div className="flex align-center gap-12 mt-8">
            <div
              style={{
                fontSize: 28,
                transform: `rotate(${windArrowRotation(today_weather.wind_direction_deg)}deg)`,
                transition: "transform 0.4s",
              }}
            >
              ↑
            </div>
            <div>
              <div style={{ fontWeight: 700 }}>
                {Math.round(today_weather.wind_kmh)} km/h
                {today_weather.wind_gusts_kmh ? ` (gusts to ${Math.round(today_weather.wind_gusts_kmh)})` : ""}
              </div>
              <div className="text-xs text-muted">
                {today_weather.wind_gusts_kmh >= 30
                  ? "Avoid spraying today — drift risk is high"
                  : "Safe conditions for spraying"}
              </div>
            </div>
          </div>
        </div>
      )}

      {isExpert ? (
        <div className="grid-2 mt-16">
          <div className="card static">
            <div className="card-title mb-3">Temperature Trend (°C) — click a point for details</div>
            <div className="chart-box tall">
              <TempHumidityChart history={weather_history} onPointClick={setPopoverDay} />
            </div>
          </div>
          <div className="card static">
            <div className="card-title mb-3">Humidity & VPD</div>
            <div className="chart-box tall">
              <VpdHumidityChart history={weather_history} />
            </div>
          </div>
          <div className="card static">
            <div className="card-title mb-3">Rainfall (mm/week)</div>
            <div className="chart-box tall">
              <RainfallBarChart history={weather_history} />
            </div>
          </div>
          <div className="card static">
            <div className="card-title mb-3">Solar Radiation & Wind</div>
            <div className="chart-box tall">
              <SolarWindChart history={weather_history} />
            </div>
          </div>
        </div>
      ) : (
        <div className="card static mt-16">
          <div className="card-title mb-12">{t("cards.trends7day")}</div>
          <div className="chart-box tall">
            <TempHumidityChart history={weather_history} onPointClick={setPopoverDay} />
          </div>
          <div className="text-xs text-muted mt-8">Tap any point on the chart to see that day's full details.</div>
        </div>
      )}

      {isExpert && (
        <div className="card mt-16 static">
          <div className="card-header">
            <span className="card-title">Expert View · Weather Parameters</span>
          </div>
          <div className="stat-row">
            <div className="stat-pill">
              <div className="stat-pill-val">{today_weather?.vpd_kpa}</div>
              <div className="stat-pill-lbl">VPD (kPa)</div>
            </div>
            <div className="stat-pill">
              <div className="stat-pill-val">{(today_weather?.vpd_kpa * 6).toFixed(1)}</div>
              <div className="stat-pill-lbl">Vap. Press (kPa)</div>
            </div>
            <div className="stat-pill">
              <div className="stat-pill-val">{today_weather?.et0_mm}</div>
              <div className="stat-pill-lbl">ET₀ (mm/d)</div>
            </div>
            <div className="stat-pill">
              <div className="stat-pill-val">{Math.round(today_weather?.humidity_pct / 5)}</div>
              <div className="stat-pill-lbl">Leaf Wet (hrs)</div>
            </div>
            <div className="stat-pill">
              <div className="stat-pill-val">{today_weather?.solar_mj_m2}</div>
              <div className="stat-pill-lbl">Solar MJ/m²</div>
            </div>
            <div className="stat-pill">
              <div className="stat-pill-val">+{today_weather?.gdd_daily}</div>
              <div className="stat-pill-lbl">GDD Today</div>
            </div>
          </div>
        </div>
      )}

      <WeatherModal open={weatherOpen} onClose={() => setWeatherOpen(false)} dashboard={dashboard} />
      <DayDetailPopover day={popoverDay} onClose={() => setPopoverDay(null)} />
    </>
  );
}
