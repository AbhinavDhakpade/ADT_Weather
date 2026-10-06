import { Line, Scatter } from "react-chartjs-2";
import "../../utils/chartSetup";
import { chartOpts } from "../../utils/chartSetup";
import { riskTag } from "../../utils/helpers";

export function GddHistoryChart({ history }) {
  // history should already be sorted ascending by date and include the 30-day lookback window
  const labels = history.map((_, i) => `Day ${i + 1}`);
  const data = {
    labels,
    datasets: [
      {
        label: "Cum. GDD (Base 18°C)",
        data: history.map((h) => h.gdd_cumulative),
        borderColor: "#f5a623",
        backgroundColor: "#f5a62320",
        tension: 0.3,
        fill: true,
        pointRadius: 0,
      },
    ],
  };
  return <Line data={data} options={chartOpts(true)} />;
}

export function GddDiseaseScatterChart({ diseases }) {
  const datasets = diseases.map((d) => {
    const minGdd = parseInt(d.gdd_range?.split(/[–-]/)[0]?.replace(/\D/g, ""), 10) || 500;
    const r = riskTag(d.risk_score);
    return {
      label: d.name,
      data: [{ x: minGdd, y: d.risk_score }],
      backgroundColor: r.color + "aa",
      pointRadius: 6,
    };
  });

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { title: { display: true, text: "Min GDD" }, ticks: { color: "#8aaa97" } },
      y: { title: { display: true, text: "Risk %" }, ticks: { color: "#8aaa97" } },
    },
  };

  return <Scatter data={{ datasets }} options={options} />;
}
