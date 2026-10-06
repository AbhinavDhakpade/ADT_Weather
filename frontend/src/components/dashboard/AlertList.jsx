import { useAppSettings } from "../../context/AppSettingsContext";

const TYPE_CLASS = {
  critical: "alert-critical",
  warning: "alert-warning",
  info: "alert-info",
  ok: "alert-ok",
};

export default function AlertList({ alerts, limit }) {
  const { t } = useAppSettings();
  const items = limit ? alerts.slice(0, limit) : alerts;
  return (
    <div className="alert-list">
      {items.map((a) => (
        <div key={a.id} className={`alert-card ${TYPE_CLASS[a.severity]}`}>
          <div className="alert-icon">{a.icon}</div>
          <div>
            <div className="alert-title">
              {a.title}
              {a.source === "weather_rule" && (
                <span className="live-tag">{t("alerts.liveTag")}</span>
              )}
            </div>
            <div className="alert-desc">{a.description}</div>
          </div>
        </div>
      ))}
    </div>
  );
}
