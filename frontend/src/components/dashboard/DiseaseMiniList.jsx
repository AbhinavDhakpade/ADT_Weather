import { useAppSettings } from "../../context/AppSettingsContext";
import { riskTag } from "../../utils/helpers";

export default function DiseaseMiniList({ diseases, onSelect }) {
  const { t } = useAppSettings();

  return (
    <div className="disease-list">
      {diseases.map((d) => {
        const r = riskTag(d.risk_score);
        return (
          <button key={d.id} className="disease-row" onClick={() => onSelect(d.id)}>
            <span className="disease-name">{d.name}</span>
            <div className="disease-bar-wrap">
              <div
                className="disease-bar"
                style={{ width: `${d.risk_score}%`, background: r.color }}
              />
            </div>
            <span className="disease-pct" style={{ color: r.color }}>
              {d.risk_score}%
            </span>
            <span className={`disease-tag ${r.cls}`}>{t(r.labelKey)}</span>
          </button>
        );
      })}
    </div>
  );
}
