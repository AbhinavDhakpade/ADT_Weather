import { Line, Bar } from "react-chartjs-2";
import "../../utils/chartSetup";
import { chartOpts } from "../../utils/chartSetup";
import { formatDateLabel } from "../../utils/helpers";

export function VpdHumidityChart({ history }) {
  const labels = history.map((h) => formatDateLabel(h.date));
  const data = {
    labels,
    datasets: [
      {
        label: "Humidity%",
        data: history.map((h) => h.humidity_pct),
        borderColor: "#4caf78",
        tension: 0.4,
        fill: false,
        pointRadius: 4,
        yAxisID: "y",
      },
      {
        label: "VPD (kPa)",
        data: history.map((h) => h.vpd_kpa),
        borderColor: "#d63230",
        tension: 0.4,
        fill: false,
        pointRadius: 4,
        yAxisID: "y1",
      },
    ],
  };
  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: true, labels: { color: "#4a6358", font: { size: 11 } } } },
    scales: {
      x: { grid: { display: false }, ticks: { color: "#8aaa97", font: { size: 10 } } },
      y: { grid: { color: "rgba(0,0,0,.06)" }, ticks: { color: "#8aaa97", font: { size: 10 } } },
      y1: { position: "right", grid: { display: false }, ticks: { color: "#d63230", font: { size: 10 } } },
    },
  };
  return <Line data={data} options={options} />;
}

export function RainfallBarChart({ history }) {
  const labels = history.map((h) => formatDateLabel(h.date));
  const data = {
    labels,
    datasets: [
      {
        label: "Rainfall (mm)",
        data: history.map((h) => h.rainfall_mm),
        backgroundColor: "#1e8bc388",
        borderRadius: 8,
        borderColor: "#1e8bc3",
        borderWidth: 1,
      },
    ],
  };
  return <Bar data={data} options={chartOpts(true)} />;
}

export function SolarWindChart({ history }) {
  const labels = history.map((h) => formatDateLabel(h.date));
  const data = {
    labels,
    datasets: [
      {
        label: "Solar (MJ/m²)",
        data: history.map((h) => h.solar_mj_m2),
        borderColor: "#f5a623",
        tension: 0.4,
        fill: true,
        backgroundColor: "#f5a62325",
        pointRadius: 4,
      },
      {
        label: "Wind (km/h)",
        data: history.map((h) => h.wind_kmh),
        borderColor: "#607d8b",
        tension: 0.4,
        fill: false,
        pointRadius: 4,
        yAxisID: "y1",
      },
    ],
  };
  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: true, labels: { color: "#4a6358", font: { size: 11 } } } },
    scales: {
      x: { grid: { display: false }, ticks: { color: "#8aaa97", font: { size: 10 } } },
      y: { grid: { color: "rgba(0,0,0,.06)" }, ticks: { color: "#8aaa97", font: { size: 10 } } },
      y1: { position: "right", grid: { display: false }, ticks: { color: "#607d8b", font: { size: 10 } } },
    },
  };
  return <Line data={data} options={options} />;
}

export function GddLineChart({ history }) {
  const labels = history.map((h) => formatDateLabel(h.date));
  const data = {
    labels,
    datasets: [
      {
        label: "Cum. GDD",
        data: history.map((h) => h.gdd_cumulative),
        borderColor: "#f5a623",
        backgroundColor: "#f5a62320",
        tension: 0.4,
        fill: true,
        pointRadius: 3,
      },
    ],
  };
  return <Line data={data} options={chartOpts(false)} />;
}
