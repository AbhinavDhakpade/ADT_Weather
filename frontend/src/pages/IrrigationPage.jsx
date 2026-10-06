import { useAppSettings } from "../context/AppSettingsContext";
import { useAppData } from "../context/DataContext";
import { LoadingScreen, ErrorScreen } from "../components/common/StatusScreens";
import IrrigationTable from "../components/irrigation/IrrigationTable";
import { WaterBalanceChart, EtcRainfallChart } from "../components/irrigation/IrrigationCharts";

export default function IrrigationPage() {
  const { t, mode } = useAppSettings();
  const { dashboard, irrigationRules, loading, error, refresh } = useAppData();

  if (loading && !dashboard) return <LoadingScreen />;
  if (error) return <ErrorScreen onRetry={refresh} />;
  if (!dashboard) return null;

  const { today_weather, weather_history, irrigation_snapshot, farm, current_stage, irrigation_ml_prediction, ml_models_available } = dashboard;
  const etc = today_weather?.et0_mm ?? 0;
  const rainfallWeek = weather_history.reduce((sum, h) => sum + h.rainfall_mm, 0);
  const effRainfall = rainfallWeek * 0.9;
  const deficit = Math.max(0, etc * 7 - effRainfall);
  const notRequired = effRainfall >= etc * 7;
  const isExpert = mode === "expert";

  const nextCheckDays = notRequired ? Math.max(1, Math.round(deficit > 0 ? 2 : 4)) : 1;

  return (
    <>
      <div className="section-h">
        <h2>💧 {t("pageTitles.irrigation")}</h2>
      </div>

      {/* BIG FARMER-FRIENDLY VERDICT */}
      <div className={`irrigation-hero ${notRequired ? "hero-no" : "hero-yes"}`}>
        <div className="irrigation-hero-icon">{notRequired ? "✅" : "💧"}</div>
        <div className="irrigation-hero-text">
          <div className="irrigation-hero-title">
            {notRequired ? t("irrigation.bigVerdictNo") : t("irrigation.bigVerdictYes")}
          </div>
          <div className="irrigation-hero-sub">
            {notRequired ? t("irrigation.bigVerdictWhyNo") : t("irrigation.bigVerdictWhyYes")}
          </div>
        </div>
      </div>

      {/* SIMPLE FACTS ROW — always visible, farmer-readable */}
      <div className="grid-3 mt-16">
        <div className="card static simple-fact-card">
          <div className="simple-fact-icon">🌱</div>
          <div className="card-title">{t("irrigation.yourCropStage")}</div>
          <div className="simple-fact-val">{current_stage}</div>
        </div>
        <div className="card static simple-fact-card">
          <div className="simple-fact-icon">🟤</div>
          <div className="card-title">{t("irrigation.yourSoil")}</div>
          <div className="simple-fact-val">{farm.soil_type}</div>
        </div>
        <div className="card static simple-fact-card">
          <div className="simple-fact-icon">🌧️</div>
          <div className="card-title">{t("irrigation.rainThisWeek")}</div>
          <div className="simple-fact-val">{rainfallWeek.toFixed(0)} mm</div>
        </div>
      </div>

      {/* HOW MUCH + WHEN — farmer friendly */}
      <div className="grid-2 mt-16">
        <div className="card static">
          <div className="card-title">💧 {t("irrigation.howMuch")}</div>
          <div className="big-number-row">
            <span className="big-number">{irrigation_snapshot ? irrigation_snapshot.requirement_l_plant : "—"}</span>
            <span className="big-number-unit">L {t("irrigation.perPlant")}</span>
          </div>
          <div className="card-sub mt-8">{irrigation_snapshot?.remark}</div>
        </div>
        <div className="card static">
          <div className="card-title">📅 {t("irrigation.whenNext")}</div>
          <div className="big-number-row">
            <span className="big-number">{nextCheckDays}</span>
            <span className="big-number-unit">{nextCheckDays === 1 ? "day" : "days"}</span>
          </div>
          <div className="card-sub mt-8">
            {nextCheckDays === 1 ? t("irrigation.checkTomorrow") : t("irrigation.checkInDays").replace("{n}", nextCheckDays)}
          </div>
        </div>
      </div>

      {/* EXPERT-ONLY: technical breakdown, full table, charts */}
      {isExpert ? (
        <>
          <div className="section-h mt-16">
            <h2 className="flex align-center gap-8">
              🔬 {t("irrigation.technicalDetails")}
              {ml_models_available?.irrigation && <span className="ml-badge">🌲 ML Powered</span>}
            </h2>
          </div>
          <div className="grid-3">
            <div className="card static">
              <div className="card-title">{t("irrigation.waterRequirement")}</div>
              <div className="stat-row mt-8" style={{ flexDirection: "column" }}>
                <div className="info-item" style={{ marginBottom: 8 }}>
                  <div className="info-item-label">{t("irrigation.etcDay")}</div>
                  <div className="info-item-val">{etc} mm</div>
                </div>
                <div className="info-item" style={{ marginBottom: 8 }}>
                  <div className="info-item-label">{t("irrigation.effRainfall")}</div>
                  <div className="info-item-val">{effRainfall.toFixed(0)} mm/week</div>
                </div>
                <div className="info-item">
                  <div className="info-item-label">{t("irrigation.netRequirement")}</div>
                  <div className="info-item-val">
                    {irrigation_snapshot ? irrigation_snapshot.requirement_l_plant : "—"} L/plant
                  </div>
                </div>
              </div>
            </div>

            <div className="card static col-span-2">
              <div className="card-title">{t("irrigation.soilWaterBalance")}</div>
              <div className="chart-box short">
                <WaterBalanceChart etcDemand={etc * 7} effRainfall={effRainfall} deficit={deficit} />
              </div>
            </div>
          </div>

          {irrigation_ml_prediction && (
            <div className="card static mt-16">
              <div className="card-title">🌲 ML Second Opinion vs. Reference Table</div>
              <div className="ml-compare-row mt-8">
                <div className="ml-compare-card">
                  <div className="ml-compare-label">📋 Reference Table (Deterministic)</div>
                  <div className="ml-compare-val" style={{ color: "var(--sky)" }}>
                    {irrigation_snapshot ? irrigation_snapshot.requirement_l_plant : "—"}
                  </div>
                  <div className="ml-compare-sub">L/plant · soil + stage lookup</div>
                </div>
                <div className="ml-compare-card">
                  <div className="ml-compare-label">🌲 RandomForest Prediction</div>
                  <div className="ml-compare-val" style={{ color: "var(--green-mid)" }}>
                    {irrigation_ml_prediction.requirement_l_plant}
                  </div>
                  <div className="ml-compare-sub">
                    L/plant · ±{irrigation_ml_prediction.uncertainty_l_plant} uncertainty
                  </div>
                </div>
              </div>
              <div className="text-xs text-muted mt-8">
                Trained on ETc, rainfall, temperature, humidity, VPD, soil type, and crop stage. Uncertainty
                is the standard deviation across the forest's individual trees — a wider spread means the
                trees disagree more, signaling lower confidence.
              </div>
            </div>
          )}

          <div className="section-h mt-16">
            <h2>📊 {t("irrigation.referenceTable")}</h2>
          </div>
          <div className="card static scroll-x">
            <IrrigationTable rules={irrigationRules} />
          </div>

          <div className="card mt-16 static">
            <div className="card-title">{t("irrigation.etcVsRainfall")}</div>
            <div className="chart-box tall">
              <EtcRainfallChart history={weather_history} />
            </div>
          </div>
        </>
      ) : (
        <div className="card static mt-16 expert-hint-card">
          <div style={{ fontSize: 28 }}>🔬</div>
          <div className="text-sm text-muted mt-8">{t("irrigation.showTechnical")}</div>
        </div>
      )}
    </>
  );
}

