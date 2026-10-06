import { Doughnut } from "react-chartjs-2";
import { useAppSettings } from "../../context/AppSettingsContext";

export default function HealthScoreCard({ healthScore, variety, stage, onClick }) {
  const { t } = useAppSettings();

  const data = {
    datasets: [
      {
        data: [healthScore, 100 - healthScore],
        backgroundColor: ["#4caf78", "rgba(255,255,255,.2)"],
        borderWidth: 0,
        circumference: 180,
        rotation: 270,
      },
    ],
  };

  const options = {
    cutout: "72%",
    plugins: { legend: { display: false }, tooltip: { enabled: false } },
    responsive: false,
  };

  return (
    <div className="card health-card" onClick={onClick}>
      <div className="card-title" style={{ color: "rgba(255,255,255,.7)" }}>
        🌿 {t("cards.cropHealth")}
      </div>
      <div style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 14 }}>
        <div style={{ width: 90, height: 56 }}>
          <Doughnut data={data} options={options} width={90} height={56} />
        </div>
        <div>
          <div className="card-value" style={{ color: "#fff", fontSize: 40 }}>
            {healthScore}
          </div>
          <div style={{ color: "rgba(255,255,255,.75)", fontSize: 13, marginTop: 4 }}>
            ✅ {t("cards.goodCondition")}
          </div>
          <div style={{ color: "rgba(255,255,255,.55)", fontSize: 11, marginTop: 4 }}>
            {variety} · {stage}
          </div>
        </div>
      </div>
    </div>
  );
}
