import { useNavigate } from "react-router-dom";
import { useAppSettings } from "../../context/AppSettingsContext";

const TYPE_CLASS = {
  critical: "alert-critical",
  warning: "alert-warning",
  info: "alert-info",
  ok: "alert-ok",
};

export default function AlertStrip({ alerts, limit = 2 }) {
  const navigate = useNavigate();
  const { t } = useAppSettings();
  if (!alerts?.length) return null;

  const visible = alerts.slice(0, limit);
  const remaining = alerts.length - visible.length;

  return (
    <div className="alert-strip">
      {visible.map((a) => (
        <div
          key={a.id}
          className={`alert-strip-card ${TYPE_CLASS[a.severity]}`}
          onClick={() => navigate("/alerts")}
        >
          <span className="alert-strip-icon">{a.icon}</span>
          <div>
            <div className="alert-strip-title">
              {a.title}
              {a.source === "weather_rule" && (
                <span className="live-tag">{t("alerts.liveTag")}</span>
              )}
            </div>
            <div className="alert-strip-desc">{a.description}</div>
          </div>
        </div>
      ))}
      {remaining > 0 && (
        <div className="alert-strip-more" onClick={() => navigate("/alerts")}>
          +{remaining} {t(remaining > 1 ? "alerts.moreAlertsPlural" : "alerts.moreAlerts").replace("{n}", remaining).replace("+{n}", "").trim()} →
        </div>
      )}
    </div>
  );
}
