import { useState } from "react";
import { useAppSettings } from "../context/AppSettingsContext";
import { useAppData } from "../context/DataContext";
import { LoadingScreen, ErrorScreen } from "../components/common/StatusScreens";
import DiseaseRiskChart from "../components/disease/DiseaseRiskChart";
import DiseaseCardGrid from "../components/disease/DiseaseCardGrid";
import DiseaseDetailModal from "../components/modals/DiseaseDetailModal";

export default function DiseasePage() {
  const { t, mode } = useAppSettings();
  const { diseases, loading, error, refresh } = useAppData();
  const [selectedDisease, setSelectedDisease] = useState(null);
  const isExpert = mode === "expert";

  if (loading && diseases.length === 0) return <LoadingScreen />;
  if (error) return <ErrorScreen onRetry={refresh} />;

  return (
    <>
      <div className="section-h">
        <h2>🦠 {t("pageTitles.disease")}</h2>
        <span className="tag badge-red">⚠ {t("cards.highAlert")} Active</span>
      </div>

      {isExpert && (
        <div className="card static" style={{ marginBottom: 20 }}>
          <div className="card-title mb-12">{t("disease.allConditions")}</div>
          <div className="chart-box tall" style={{ height: 380 }}>
            <DiseaseRiskChart diseases={diseases} />
          </div>
        </div>
      )}

      <DiseaseCardGrid diseases={diseases} onSelect={setSelectedDisease} limit={isExpert ? 30 : 6} />

      <DiseaseDetailModal diseaseId={selectedDisease} onClose={() => setSelectedDisease(null)} />
    </>
  );
}
