import { useEffect, useState } from "react";
import { useAppSettings } from "../context/AppSettingsContext";
import { useAppData } from "../context/DataContext";
import { LoadingScreen, ErrorScreen } from "../components/common/StatusScreens";
import GddMeter from "../components/dashboard/GddMeter";
import { GddLineChart } from "../components/weather/MiscWeatherCharts";
import { GddHistoryChart, GddDiseaseScatterChart } from "../components/dashboard/GddCharts";
import { fetchActualWeather } from "../api/client";

export default function GddPage() {
  const { t, mode } = useAppSettings();
  const { dashboard, diseases, loading, error, refresh, farmId } = useAppData();
  const [history30, setHistory30] = useState([]);

  useEffect(() => {
    fetchActualWeather(farmId).then((data) => {
      const results = data.results ?? data;
      const sorted = [...results].sort((a, b) => new Date(a.date) - new Date(b.date));
      setHistory30(sorted);
    });
  }, [farmId]);

  if (loading && !dashboard) return <LoadingScreen />;
  if (error) return <ErrorScreen onRetry={refresh} />;
  if (!dashboard) return null;

  const { farm, current_gdd, current_stage, growth_stages, weather_history } = dashboard;

  const stageProgress = (stage, idx) => {
    if (current_gdd >= stage.gdd_threshold) {
      const next = growth_stages[idx + 1];
      if (!next || current_gdd >= next.gdd_threshold) return 100;
      return Math.round(((current_gdd - stage.gdd_threshold) / (next.gdd_threshold - stage.gdd_threshold)) * 100);
    }
    return 0;
  };

  return (
    <>
      <div className="section-h">
        <h2>📈 {t("pageTitles.gdd")}</h2>
      </div>

      <div className="grid-2">
        <div className="card static">
          <GddMeter
            currentGdd={current_gdd}
            baseTemp={farm.base_temp_c}
            currentStage={current_stage}
            growthStages={growth_stages}
          />
          <div className="disease-list mt-8">
            {growth_stages.map((s, i) => {
              const pct = stageProgress(s, i);
              return (
                <div className="disease-row" key={s.stage_name} style={{ cursor: "default" }}>
                  <span className="disease-name">{s.stage_name}</span>
                  <div className="disease-bar-wrap">
                    <div
                      className="disease-bar"
                      style={{
                        width: `${pct}%`,
                        background: pct === 100 ? "var(--green-soft)" : pct > 0 ? "var(--gold)" : "var(--text-3)",
                      }}
                    />
                  </div>
                  <span
                    className="disease-pct"
                    style={{ color: pct === 100 ? "var(--green-mid)" : pct > 0 ? "var(--amber)" : "var(--text-3)" }}
                  >
                    {pct === 100 ? t("gdd.done") : `${pct}%`}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
        <div className="card static">
          <div className="chart-box tall">
            <GddLineChart history={weather_history} />
          </div>
        </div>
      </div>

      <div className="card mt-16 static">
        <div className="card-title">{t("gdd.growthStages")}</div>
        <div className="chart-box tall">
          {history30.length > 0 ? <GddHistoryChart history={history30} /> : <LoadingScreen />}
        </div>
      </div>

      {mode === "expert" && (
        <div className="card mt-16 static">
          <div className="card-title">{t("gdd.correlation")}</div>
          <div className="chart-box tall">
            <GddDiseaseScatterChart diseases={diseases} />
          </div>
        </div>
      )}
    </>
  );
}
