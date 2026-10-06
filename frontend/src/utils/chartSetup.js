import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from "chart.js";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

export const chartOpts = (legend = false) => ({
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: legend, labels: { color: "#4a6358", font: { size: 11 } } },
  },
  scales: {
    x: { grid: { display: false }, ticks: { color: "#8aaa97", font: { size: 10 } } },
    y: { grid: { color: "rgba(0,0,0,.06)" }, ticks: { color: "#8aaa97", font: { size: 10 } } },
  },
});
