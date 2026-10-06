import Modal from "../common/Modal";
import { useAppSettings } from "../../context/AppSettingsContext";

export default function HealthModal({ open, onClose, dashboard }) {
  const { t } = useAppSettings();
  if (!dashboard) return null;
  const { health_score, farm, current_stage, current_gdd, mini_diseases, today_weather } = dashboard;
  const topDisease = mini_diseases?.[0];

  return (
    <Modal open={open} onClose={onClose}>
      <div className="modal-header">
        <div>
          <h2>{t("modals.cropHealthAnalysis")}</h2>
          <div className="modal-badge badge-green mt-8">
            {t("modals.score")}: {health_score} / 100 · {t("cards.goodCondition")}
          </div>
        </div>
        <button className="modal-close" onClick={onClose}>
          ✕
        </button>
      </div>

      <div className="info-grid">
        <div className="info-item">
          <div className="info-item-label">{t("farm.variety")}</div>
          <div className="info-item-val">{farm.variety}</div>
        </div>
        <div className="info-item">
          <div className="info-item-label">{t("farm.cropStage")}</div>
          <div className="info-item-val">{current_stage}</div>
        </div>
        <div className="info-item">
          <div className="info-item-label">{t("farm.gddAccumulated")}</div>
          <div className="info-item-val">
            {Math.round(current_gdd).toLocaleString()} ({t("cards.baseTemp")} {farm.base_temp_c}°C)
          </div>
        </div>
        <div className="info-item">
          <div className="info-item-label">{t("farm.expectedHarvest")}</div>
          <div className="info-item-val">{farm.expected_harvest}</div>
        </div>
      </div>

      <div className="section-title">{t("modals.aiExplanation")}</div>
      <p className="text-sm text-muted">
        Your crop health score is {health_score}/100 based on current weather conditions, disease risk
        profile, GDD accumulation, and soil moisture. The score is reduced from 100 primarily due to
        elevated humidity ({today_weather?.humidity_pct}%) increasing {topDisease?.name} risk, and recent
        rainfall patterns. Your GDD of {Math.round(current_gdd).toLocaleString()} indicates healthy growth
        progress for the {current_stage} stage.
      </p>

      <div className="section-title">{t("modals.currentIssues")}</div>
      <div className="steps">
        {mini_diseases?.slice(0, 2).map((d, i) => (
          <div className="step" key={d.id}>
            <div className="step-num">{i + 1}</div>
            <div className="step-text">
              <strong>{d.name} risk elevated</strong> – {d.risk_label} risk ({d.risk_score}%) under current
              humidity and crop stage conditions ({d.crop_stage})
            </div>
          </div>
        ))}
        <div className="step">
          <div className="step-num">3</div>
          <div className="step-text">
            <strong>Drainage advisory</strong> – {today_weather?.rainfall_mm}mm rainfall today, drainage
            check recommended to prevent waterlogging on {farm.soil_type} soil
          </div>
        </div>
      </div>

      <div className="section-title">{t("modals.suggestedActions")}</div>
      <div className="steps">
        <div className="step">
          <div className="step-num">1</div>
          <div className="step-text">Inspect field for early disease symptoms (leaf twisting, stunting)</div>
        </div>
        <div className="step">
          <div className="step-num">2</div>
          <div className="step-text">
            Check drainage channels – avoid waterlogging in {farm.soil_type} soil
          </div>
        </div>
        <div className="step">
          <div className="step-num">3</div>
          <div className="step-text">
            Apply preventive fungicide after rainfall if humidity stays above 80%
          </div>
        </div>
      </div>
    </Modal>
  );
}
