import { useEffect, useState } from "react";
import Modal from "../common/Modal";
import { useAppSettings } from "../../context/AppSettingsContext";
import { fetchDiseaseDetail } from "../../api/client";
import { riskTag, capitalize } from "../../utils/helpers";
import { useAppData } from "../../context/DataContext";

export default function DiseaseDetailModal({ diseaseId, onClose }) {
  const { t } = useAppSettings();
  const { farmId } = useAppData();
  const [disease, setDisease] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!diseaseId) return;
    setLoading(true);
        fetchDiseaseDetail(diseaseId, farmId)
      .then(setDisease)
      .finally(() => setLoading(false));
  }, [diseaseId, farmId]);
  const open = !!diseaseId;
  const r = disease ? riskTag(disease.risk_score) : null;

  return (
    <Modal open={open} onClose={onClose}>
      {loading || !disease ? (
        <div style={{ padding: 40, textAlign: "center" }} className="text-muted">
          {t("common.loading")}
        </div>
      ) : (
        <>
          <div className="modal-header">
            <div>
              <h2>{disease.name}</h2>
              <div className={`modal-badge mt-8 ${r.cls}`}>
                {t(r.labelKey)} Risk · {disease.risk_score}% · {disease.organism}
              </div>
            </div>
            <button className="modal-close" onClick={onClose}>
              ✕
            </button>
          </div>

          <div className="info-grid">
            <div className="info-item">
              <div className="info-item-label">{t("disease.cropStage")}</div>
              <div className="info-item-val">{disease.crop_stage}</div>
            </div>
            <div className="info-item">
              <div className="info-item-label">{t("disease.type")}</div>
              <div className="info-item-val">{capitalize(disease.disease_type)}</div>
            </div>
            <div className="info-item">
              <div className="info-item-label">{t("disease.tempRange")}</div>
              <div className="info-item-val">{disease.avg_temp_c}°C</div>
            </div>
            <div className="info-item">
              <div className="info-item-label">{t("disease.humidityLabel")}</div>
              <div className="info-item-val">{disease.relative_humidity_pct}%</div>
            </div>
            <div className="info-item">
              <div className="info-item-label">{t("disease.vpd")}</div>
              <div className="info-item-val">{disease.vpd_kpa} kPa</div>
            </div>
            <div className="info-item">
              <div className="info-item-label">{t("disease.leafWetness")}</div>
              <div className="info-item-val">{disease.leaf_wetness_hrs} hrs</div>
            </div>
            <div className="info-item">
              <div className="info-item-label">{t("disease.rainfallWeek")}</div>
              <div className="info-item-val">{disease.rainfall_mm_week}</div>
            </div>
            <div className="info-item">
              <div className="info-item-label">{t("disease.gddRange")}</div>
              <div className="info-item-val">{disease.gdd_range}</div>
            </div>
          </div>

          <div className="section-title">{t("disease.aiRiskAnalysis")}</div>
          {disease.ml_prediction ? (
            <div className="ml-compare-row">
              <div className="ml-compare-card">
                <div className="ml-compare-label">📐 Rule-Based (Deterministic)</div>
                <div className="ml-compare-val" style={{ color: r.color }}>
                  {disease.risk_score}%
                </div>
                <div className="ml-compare-sub">From Excel reference ranges</div>
              </div>
              <div className="ml-compare-card">
                <div className="ml-compare-label">🌲 ML Second Opinion</div>
                <div className="ml-compare-val" style={{ color: riskTag(disease.ml_prediction.risk_pct).color }}>
                  {disease.ml_prediction.risk_pct}%
                </div>
                <div className="ml-compare-sub">
                  RandomForest · {Math.round(disease.ml_prediction.confidence * 100)}% confidence
                </div>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted">
              ML second-opinion model not yet trained on this server. Run{" "}
              <code>python manage.py train_ml_models</code> in the backend to enable it.
            </p>
          )}
          <p className="text-sm text-muted mt-8">
            Current field conditions are evaluated against <strong>{disease.name}</strong>'s known favorable
            range (temperature, humidity, VPD, leaf wetness) using both a deterministic rule engine and a
            RandomForest classifier trained on the same agronomic relationships, using live weather data
            from Open-Meteo.
          </p>

          {disease.treatment && (
            <>
              <div className="section-title">{t("disease.biologicalControl")}</div>
              <p className="text-sm text-muted">{disease.treatment.biological}</p>

              <div className="section-title">{t("disease.chemicalControl")}</div>
              <p className="text-sm text-muted">
                <strong>{t("disease.products")}:</strong> {disease.treatment.chemical}
              </p>
              <p className="text-sm text-muted mt-4">
                <strong>{t("disease.timing")}:</strong> {disease.treatment.timing}
              </p>

              <div className="section-title">{t("disease.safety")}</div>
              <p className="text-sm text-muted">{disease.treatment.safety}</p>

              <div className="section-title">{t("disease.recovery")}</div>
              <p className="text-sm text-muted">{disease.treatment.recovery}</p>
            </>
          )}
        </>
      )}
    </Modal>
  );
}
