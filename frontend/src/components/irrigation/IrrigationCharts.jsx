import { Doughnut, Line } from "react-chartjs-2";
import "../../utils/chartSetup";
import { chartOpts } from "../../utils/chartSetup";
import { formatDateLabel } from "../../utils/helpers";

export function WaterBalanceChart({ etcDemand, effRainfall, deficit }) {
  const data = {
    labels: ["ETc Demand", "Effective Rainfall", "Deficit"],
    datasets: [
      {
        data: [etcDemand, effRainfall, deficit],
        backgroundColor: ["#e07b00", "#1e8bc3", "#d63230"],
        borderWidth: 0,
      },
    ],
  };
  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: true, position: "bottom", labels: { color: "#4a6358", font: { size: 9 } } } },
    cutout: "60%",
  };
  return <Doughnut data={data} options={options} />;
}

export function EtcRainfallChart({ history }) {
  const labels = history.map((h) => formatDateLabel(h.date));
  const data = {
    labels,
    datasets: [
      {
        label: "ETc (mm)",
        data: history.map((h) => h.et0_mm),
        borderColor: "#e07b00",
        tension: 0.4,
        fill: false,
        pointRadius: 4,
      },
      {
        label: "Rainfall (mm/7d)",
        data: history.map((h) => h.rainfall_mm / 7),
        borderColor: "#1e8bc3",
        tension: 0.4,
        fill: false,
        pointRadius: 4,
        borderDash: [5, 3],
      },
    ],
  };
  return <Line data={data} options={chartOpts(true)} />;
}
