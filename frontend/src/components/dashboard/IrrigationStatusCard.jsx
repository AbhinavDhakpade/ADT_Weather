import { Doughnut } from "react-chartjs-2";
import { useAppSettings } from "../../context/AppSettingsContext";

export default function IrrigationStatusCard({ irrigationSnapshot, todayWeather, onClick }) {
  const { t } = useAppSettings();

  const moisture = 65;
  const availableWater = 48;
  const etcToday = todayWeather?.et0_mm ?? 4.2;

  const data = {
    datasets: [
      {
        data: [moisture, 100 - moisture],
        backgroundColor: ["#4caf78", "#e8f5ee"],
        borderWidth: 0,
        circumference: 220,
        rotation: 250,
      },
    ],
  };

  const options = {
    cutout: "75%",
    plugins: { legend: { display: false }, tooltip: { enabled: false } },
    responsive: false,
  };

  return (
    <div className="card" onClick={onClick}>
      <div className="card-header">
        <span className="card-title">💧 {t("cards.irrigationStatus")}</span>
        <span className="tag badge-gold">{t("cards.review")}</span>
      </div>
      <div className="soil-gauge-wrap">
        <div style={{ width: 100, height: 100 }}>
          <Doughnut data={data} options={options} width={100} height={100} />
        </div>
        <div className="soil-bars">
          <div className="soil-row">
            <span className="soil-label">{t("cards.soilMoisture")}</span>
            <div className="soil-track">
              <div className="soil-fill" style={{ width: "65%", background: "var(--green-soft)" }} />
            </div>
            <span className="soil-val" style={{ color: "var(--green-mid)" }}>
              65%
            </span>
          </div>
          <div className="soil-row">
            <span className="soil-label">{t("cards.availableWater")}</span>
            <div className="soil-track">
              <div className="soil-fill" style={{ width: "48%", background: "var(--sky)" }} />
            </div>
            <span className="soil-val" style={{ color: "var(--sky)" }}>
              48%
            </span>
          </div>
          <div className="soil-row">
            <span className="soil-label">{t("cards.etcToday")}</span>
            <div className="soil-track">
              <div className="soil-fill" style={{ width: "70%", background: "var(--gold)" }} />
            </div>
            <span className="soil-val" style={{ color: "var(--amber)" }}>
              {etcToday}mm
            </span>
          </div>
        </div>
      </div>
      <div className="card-badge badge-gold mt-8">
        💧 {irrigationSnapshot?.remark || "Check irrigation reference table"}
      </div>
    </div>
  );
}
