import { useAppSettings } from "../../context/AppSettingsContext";

export function LoadingScreen() {
  const { t } = useAppSettings();
  return (
    <div className="center-page">
      <div style={{ fontSize: 40 }}>🌾</div>
      <div className="text-muted">{t("common.loading")}</div>
    </div>
  );
}

export function ErrorScreen({ onRetry }) {
  const { t } = useAppSettings();
  return (
    <div className="center-page">
      <div style={{ fontSize: 40 }}>⚠️</div>
      <div className="text-muted" style={{ maxWidth: 420 }}>
        {t("common.error")}
      </div>
      <button className="btn-primary" onClick={onRetry}>
        {t("common.retry")}
      </button>
    </div>
  );
}
