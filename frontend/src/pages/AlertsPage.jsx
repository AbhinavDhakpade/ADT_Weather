import { useAppSettings } from "../context/AppSettingsContext";
import { useAppData } from "../context/DataContext";
import { LoadingScreen, ErrorScreen } from "../components/common/StatusScreens";
import AlertList from "../components/dashboard/AlertList";

export default function AlertsPage() {
  const { t } = useAppSettings();
  const { dashboard, loading, error, refresh } = useAppData();

  if (loading && !dashboard) return <LoadingScreen />;
  if (error) return <ErrorScreen onRetry={refresh} />;
  if (!dashboard) return null;

  const { alerts } = dashboard;

  return (
    <>
      <div className="section-h">
        <h2>🔔 {t("alerts.title")}</h2>
      </div>
      <div className="card static">
        {alerts.length > 0 ? (
          <AlertList alerts={alerts} />
        ) : (
          <div className="text-muted text-sm">{t("alerts.noActive")}</div>
        )}
      </div>
    </>
  );
}
