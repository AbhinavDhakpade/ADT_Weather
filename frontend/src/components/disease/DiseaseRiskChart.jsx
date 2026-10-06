import { Bar } from "react-chartjs-2";
import "../../utils/chartSetup";
import { riskTag } from "../../utils/helpers";

export default function DiseaseRiskChart({ diseases }) {
  const sorted = [...diseases].sort((a, b) => b.risk_score - a.risk_score);
  const data = {
    labels: sorted.map((d) => d.name),
    datasets: [
      {
        label: "Risk %",
        data: sorted.map((d) => d.risk_score),
        backgroundColor: sorted.map((d) => riskTag(d.risk_score).color + "cc"),
        borderColor: sorted.map((d) => riskTag(d.risk_score).color),
        borderWidth: 1,
        borderRadius: 4,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    indexAxis: "y",
    plugins: { legend: { display: false } },
    scales: {
      x: { grid: { color: "rgba(0,0,0,.06)" }, ticks: { color: "#8aaa97", font: { size: 9 } }, max: 100 },
      y: { grid: { display: false }, ticks: { color: "#4a6358", font: { size: 9 } } },
    },
  };

  return <Bar data={data} options={options} />;
}
