import { riskTag } from "../../utils/helpers";
import { useAppSettings } from "../../context/AppSettingsContext";

export default function DiseaseCardGrid({ diseases, onSelect, limit }) {
  const { t } = useAppSettings();
  const sorted = [...diseases].sort((a, b) => b.risk_score - a.risk_score);
  const list = limit ? sorted.slice(0, limit) : sorted;

  return (
    <div className="grid-3">
      {list.map((d) => {
        const r = riskTag(d.risk_score);
        return (
          <div className="card" key={d.id} onClick={() => onSelect(d.id)}>
            <div className="card-header">
              <span className="card-title">{d.name}</span>
              <span className={`disease-tag ${r.cls}`}>{t(r.labelKey)}</span>
            </div>
            <div className="card-value" style={{ fontSize: 36 }}>
              {d.risk_score}
              <span style={{ fontSize: 16, fontWeight: 400, color: "var(--text-2)" }}>%</span>
            </div>
            <div className="disease-bar-wrap mt-8">
              <div className="disease-bar" style={{ width: `${d.risk_score}%`, background: r.color }} />
            </div>
            {d.ml_risk_pct !== null && d.ml_risk_pct !== undefined && (
              <div className="text-xs mt-8" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span className="ml-badge">🌲 ML: {d.ml_risk_pct}%</span>
              </div>
            )}
            <div className="card-sub mt-8">📍 {d.crop_stage}</div>
            <div className="text-xs text-muted mt-4">
              RH: {d.relative_humidity_pct}% · Temp: {d.avg_temp_c}°C
            </div>
            <div className="text-xs text-muted">GDD: {d.gdd_range}</div>
          </div>
        );
      })}
    </div>
  );
}
