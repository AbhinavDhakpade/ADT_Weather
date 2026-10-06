import { Line } from "react-chartjs-2";
import "../../utils/chartSetup";
import { formatDateLabel } from "../../utils/helpers";

export default function TempHumidityChart({ history, onPointClick }) {
  const labels = history.map((h) => formatDateLabel(h.date));
  const data = {
    labels,
    datasets: [
      {
        label: "Max Temp",
        data: history.map((h) => h.temp_max_c),
        borderColor: "#e07b00",
        backgroundColor: "#e07b0018",
        tension: 0.4,
        fill: true,
        pointRadius: 3,
        pointHoverRadius: 6,
      },
      {
        label: "Min Temp",
        data: history.map((h) => h.temp_min_c),
        borderColor: "#1e8bc3",
        backgroundColor: "#1e8bc318",
        tension: 0.4,
        fill: true,
        pointRadius: 3,
        pointHoverRadius: 6,
      },
      {
        label: "Humidity%",
        data: history.map((h) => h.humidity_pct),
        borderColor: "#4caf78",
        backgroundColor: "transparent",
        tension: 0.4,
        yAxisID: "y1",
        pointRadius: 3,
        pointHoverRadius: 6,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    onClick: (evt, elements) => {
      if (elements.length > 0 && onPointClick) {
        onPointClick(history[elements[0].index]);
      }
    },
    onHover: (evt, elements) => {
      if (evt.native?.target) evt.native.target.style.cursor = elements.length ? "pointer" : "default";
    },
    plugins: { legend: { display: true, labels: { color: "#4a6358", font: { size: 11 } } } },
    scales: {
      x: { grid: { display: false }, ticks: { color: "#8aaa97", font: { size: 10 } } },
      y: { grid: { color: "rgba(0,0,0,.06)" }, ticks: { color: "#8aaa97", font: { size: 10 } } },
      y1: { position: "right", grid: { display: false }, ticks: { color: "#4caf78", font: { size: 10 } } },
    },
  };

  return <Line data={data} options={options} />;
}
