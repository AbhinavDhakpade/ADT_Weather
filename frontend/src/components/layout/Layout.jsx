import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";
import Topbar from "./Topbar";
import VoiceFab from "./VoiceFab";
import { useAppSettings } from "../../context/AppSettingsContext";

export default function Layout() {
  const { sidebarCollapsed, mode } = useAppSettings();

  return (
    <div className="app" data-mode={mode}>
      <Sidebar />
      <div className={`main${sidebarCollapsed ? " collapsed-margin" : ""}`}>
        <Topbar />
        <div className="page-content">
          <Outlet />
        </div>
      </div>
      <VoiceFab />
    </div>
  );
}
