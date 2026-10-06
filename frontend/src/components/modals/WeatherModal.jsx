import Modal from "../common/Modal";
import { useAppSettings } from "../../context/AppSettingsContext";

export default function WeatherModal({ open, onClose, dashboard }) {
  const { t } = useAppSettings();
  if (!dashboard) return null;
  const { today_weather: w, farm } = dashboard;
  if (!w) return null;

  return (
    <Modal open={open} onClose={onClose}>
      <div className="modal-header">
        <div>
          <h2>{t("modals.weatherImpact")}</h2>
          <div className="modal-badge badge-sky mt-8">Today · {farm.village}</div>
        </div>
        <button className="modal-close" onClick={onClose}>
          ✕
        </button>
      </div>

      <div className="info-grid">
        <div className="info-item">
          <div className="info-item-label">{t("cards.temperature")}</div>
          <div className="info-item-val">{w.temp_max_c}°C</div>
        </div>
        <div className="info-item">
          <div className="info-item-label">{t("cards.humidity")}</div>
          <div className="info-item-val">{w.humidity_pct}%</div>
        </div>
        <div className="info-item">
          <div className="info-item-label">{t("disease.vpd")}</div>
          <div className="info-item-val">{w.vpd_kpa} kPa</div>
        </div>
        <div className="info-item">
          <div className="info-item-label">{t("modals.vapourPressure")}</div>
          <div className="info-item-val">{(w.vpd_kpa * 6).toFixed(1)} kPa</div>
        </div>
        <div className="info-item">
          <div className="info-item-label">{t("disease.leafWetness")}</div>
          <div className="info-item-val">{Math.round(w.humidity_pct / 5)} hrs</div>
        </div>
        <div className="info-item">
          <div className="info-item-label">{t("modals.et0Today")}</div>
          <div className="info-item-val">{w.et0_mm} mm</div>
        </div>
      </div>

      <div className="section-title">{t("modals.effectOnSugarcane")}</div>
      <div className="steps">
        <div className="step">
          <div className="step-num">1</div>
          <div className="step-text">
            <strong>Temperature {w.temp_max_c}°C</strong> – Within optimal range (25–35°C) for crop growth.
            GDD contribution today: +{w.gdd_daily}
          </div>
        </div>
        <div className="step">
          <div className="step-num">2</div>
          <div className="step-text">
            <strong>Humidity {w.humidity_pct}%</strong> – {w.humidity_pct >= 80 ? "High" : "Moderate"}.
            {w.humidity_pct >= 80
              ? " Favorable conditions for fungal disease development."
              : " Within normal range."}
          </div>
        </div>
        <div className="step">
          <div className="step-num">3</div>
          <div className="step-text">
            <strong>VPD {w.vpd_kpa} kPa</strong> –{" "}
            {w.vpd_kpa < 0.8
              ? "Low VPD means stomata stay open longer, allowing more fungal entry."
              : "Healthy VPD range supporting normal transpiration."}
          </div>
        </div>
        <div className="step">
          <div className="step-num">4</div>
          <div className="step-text">
            <strong>Rainfall {w.rainfall_mm}mm</strong> – {w.rainfall_mm > 10 ? "Sufficient" : "Limited"} for{" "}
            {farm.soil_type} soil.
          </div>
        </div>
      </div>
    </Modal>
  );
}
