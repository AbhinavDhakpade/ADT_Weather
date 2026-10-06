import { Bar } from "react-chartjs-2";
import "../../utils/chartSetup";
import { chartOpts } from "../../utils/chartSetup";
import { formatDateLabel } from "../../utils/helpers";

export default function RainfallEtChart({ history }) {
  const labels = history.map((h) => formatDateLabel(h.date));
  const data = {
    labels,
    datasets: [
      {
        label: "Rainfall (mm)",
        data: history.map((h) => h.rainfall_mm),
        backgroundColor: "#1e8bc388",
        borderRadius: 6,
      },
      {
        label: "ET₀ (mm)",
        data: history.map((h) => h.et0_mm),
        backgroundColor: "#f5a62388",
        borderRadius: 6,
      },
    ],
  };

  return <Bar data={data} options={chartOpts(true)} />;
}
