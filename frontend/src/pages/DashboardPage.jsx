import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAppSettings } from "../context/AppSettingsContext";
import { useAppData } from "../context/DataContext";
import { LoadingScreen, ErrorScreen } from "../components/common/StatusScreens";
import AlertStrip from "../components/dashboard/AlertStrip";
import HealthScoreCard from "../components/dashboard/HealthScoreCard";
import WeatherMetricCards from "../components/dashboard/WeatherMetricCards";
import DiseaseMiniList from "../components/dashboard/DiseaseMiniList";
import IrrigationStatusCard from "../components/dashboard/IrrigationStatusCard";
import WeatherMiniGrid from "../components/dashboard/WeatherMiniGrid";
import AdvisoryTimeline from "../components/dashboard/AdvisoryTimeline";
import GddMeter from "../components/dashboard/GddMeter";
import SchedulerStatusCard from "../components/dashboard/SchedulerStatusCard";
import TempHumidityChart from "../components/weather/TempHumidityChart";
import RainfallEtChart from "../components/weather/RainfallEtChart";
import { GddLineChart } from "../components/weather/MiscWeatherCharts";
import HealthModal from "../components/modals/HealthModal";
import WeatherModal from "../components/modals/WeatherModal";
import DiseaseDetailModal from "../components/modals/DiseaseDetailModal";
import { useAuth } from "../context/AuthContext";

export default function DashboardPage() {
  const { t, mode } = useAppSettings();
  const { dashboard, loading, error, refresh } = useAppData();
  const { user } = useAuth();
  const navigate = useNavigate();

  const [healthOpen, setHealthOpen] = useState(false);
  const [weatherOpen, setWeatherOpen] = useState(false);
  const [selectedDisease, setSelectedDisease] = useState(null);

  if (loading && !dashboard) return <LoadingScreen />;
  if (error) return <ErrorScreen onRetry={refresh} />;
  if (!dashboard) return null;

  const { farm, today_weather, weather_history, mini_diseases, alerts, timeline, growth_stages, health_score, current_gdd, current_stage, irrigation_snapshot } = dashboard;
  const isExpert = mode === "expert";

  return (
    <>
      {/* MODE BANNER — explains what farmer/expert mode actually changes */}
      <div className="mode-banner">
        <span className="mode-banner-icon">{isExpert ? "🔬" : "🌾"}</span>
                <span>{isExpert ? t("mode.expertDesc") : t("mode.farmerDesc")}</span>
      </div>

      {/* ALERTS — always first thing the farmer sees */}
      <AlertStrip alerts={alerts} limit={isExpert ? 4 : 2} />

      {/* ROW 1: KEY METRICS */}
      <div className="grid-4">
        <HealthScoreCard
          healthScore={health_score}
          variety={farm.variety}
          stage={current_stage}
          onClick={() => setHealthOpen(true)}
        />
        <WeatherMetricCards
          todayWeather={today_weather}
          baseTemp={farm.base_temp_c}
          onClick={() => setWeatherOpen(true)}
        />
      </div>

      {/* ROW 2: DISEASE + IRRIGATION */}
      <div className="grid-2 mt-16">
        <div className="card" onClick={() => navigate("/disease")}>
          <div className="card-header">
            <span className="card-title">🦠 {t("cards.diseaseRiskOverview")}</span>
            <span className="tag badge-red">⚠ {t("cards.highAlert")}</span>
          </div>
          <DiseaseMiniList diseases={mini_diseases} onSelect={setSelectedDisease} />
          <div className="mt-12 text-sm text-muted">{t("common.tapForFull")}</div>
        </div>

        <IrrigationStatusCard
          irrigationSnapshot={irrigation_snapshot}
          todayWeather={today_weather}
          onClick={() => navigate("/irrigation")}
        />
      </div>

      {/* ROW 3: WEATHER MINI */}
      <div className="section-h">
        <h2>☁️ {t("cards.todaysWeather")}</h2>
        <button className="see-all" onClick={() => navigate("/weather")}>
          {t("common.fullAnalysis")}
        </button>
      </div>
      <WeatherMiniGrid todayWeather={today_weather} onClick={() => setWeatherOpen(true)} />

      {/* ROW 4: CHARTS — expert mode only; farmer mode keeps the page lighter */}
      {isExpert && (
        <>
          <div className="section-h mt-16">
            <h2>📊 {t("cards.trends7day")}</h2>
            <button className="see-all" onClick={() => navigate("/forecast")}>
              {t("common.fullForecast")}
            </button>
          </div>
          <div className="grid-2">
            <div className="card static">
              <div className="card-header">
                <span className="card-title">{t("cards.tempHumTrend")}</span>
              </div>
              <div className="chart-box">
                <TempHumidityChart history={weather_history} />
              </div>
            </div>
            <div className="card static">
              <div className="card-header">
                <span className="card-title">{t("cards.rainEtTrend")}</span>
              </div>
              <div className="chart-box">
                <RainfallEtChart history={weather_history} />
              </div>
            </div>
          </div>
        </>
      )}

      {/* ROW 5: TIMELINE — what to do next, always shown (the most farmer-useful card) */}
      <div className="section-h mt-16">
        <h2>📋 {t("cards.aiTimeline")}</h2>
      </div>
      <div className="card static">
        <AdvisoryTimeline items={timeline} />
      </div>

      {/* ROW 6: GDD METER */}
      <div className="section-h mt-16">
        <h2>📈 {t("cards.gddGrowth")}</h2>
        <button className="see-all" onClick={() => navigate("/gdd")}>
          {t("common.details")}
        </button>
      </div>
      <div className="card static">
        {isExpert ? (
          <div className="grid-2">
            <div>
              <GddMeter
                currentGdd={current_gdd}
                baseTemp={farm.base_temp_c}
                currentStage={current_stage}
                growthStages={growth_stages}
              />
            </div>
            <div>
              <div className="chart-box">
                <GddLineChart history={weather_history} />
              </div>
            </div>
          </div>
        ) : (
          <GddMeter
            currentGdd={current_gdd}
            baseTemp={farm.base_temp_c}
            currentStage={current_stage}
            growthStages={growth_stages}
          />
        )}
      </div>

      {/* ROW 7: SCHEDULER MONITORING — ops visibility into the automatic hourly
          sync; expert mode only, farmers don't need to see this. */}
      {isExpert && user?.is_staff && (
        <>
          <div className="section-h mt-16">
            <h2>⏱ {t("scheduler.title")}</h2>
          </div>
          <SchedulerStatusCard />
        </>
      )}

      <HealthModal open={healthOpen} onClose={() => setHealthOpen(false)} dashboard={dashboard} />
      <WeatherModal open={weatherOpen} onClose={() => setWeatherOpen(false)} dashboard={dashboard} />
      <DiseaseDetailModal diseaseId={selectedDisease} onClose={() => setSelectedDisease(null)} />
    </>
  );
}
