import { Routes, Route } from "react-router-dom";
import Layout from "./components/layout/Layout";
import DashboardPage from "./pages/DashboardPage";
import WeatherPage from "./pages/WeatherPage";
import DiseasePage from "./pages/DiseasePage";
import IrrigationPage from "./pages/IrrigationPage";
import ForecastPage from "./pages/ForecastPage";
import AlertsPage from "./pages/AlertsPage";
import GddPage from "./pages/GddPage";
import FarmPage from "./pages/FarmPage";
import HistoryPage from "./pages/HistoryPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/weather" element={<WeatherPage />} />
        <Route path="/disease" element={<DiseasePage />} />
        <Route path="/irrigation" element={<IrrigationPage />} />
        <Route path="/forecast" element={<ForecastPage />} />
        <Route path="/alerts" element={<AlertsPage />} />
        <Route path="/gdd" element={<GddPage />} />
        <Route path="/farm" element={<FarmPage />} />
        <Route path="/history" element={<HistoryPage />} />
      </Route>
    </Routes>
  );
}
