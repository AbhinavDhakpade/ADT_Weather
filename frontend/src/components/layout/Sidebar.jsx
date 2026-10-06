import { NavLink } from "react-router-dom";
import { useAppSettings } from "../../context/AppSettingsContext";

const NAV_ITEMS = [
  { to: "/", icon: "🏠", key: "dashboard", end: true },
  { to: "/weather", icon: "☁️", key: "weather" },
  { to: "/disease", icon: "🦠", key: "disease" },
  { to: "/irrigation", icon: "💧", key: "irrigation" },
  { to: "/forecast", icon: "📅", key: "forecast" },
  { to: "/alerts", icon: "🔔", key: "alerts" },
  { to: "/gdd", icon: "📈", key: "gdd" },
  { to: "/farm", icon: "🗺️", key: "farm" },
  { to: "/history", icon: "🕘", key: "history" },
];

export default function Sidebar() {
  const { sidebarCollapsed, mode, toggleMode, t } = useAppSettings();

  return (
    <aside className={`sidebar${sidebarCollapsed ? " collapsed" : ""}`}>
      <div className="sidebar-logo">
        <div className="logo-icon">🌾</div>
        <div>
          <div className="logo-text">{t("appName")}</div>
          <div className="logo-sub">{t("appTagline")}</div>
        </div>
      </div>

      <nav className="nav">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.key}
            to={item.to}
            end={item.end}
            className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
          >
            <span className="nav-icon">{item.icon}</span>
            <span className="nav-label">{t(`nav.${item.key}`)}</span>
          </NavLink>
        ))}
      </nav>

      <div className="sidebar-footer">
        <button className="mode-badge" onClick={toggleMode} title="Toggle Farmer/Expert mode">
          <span className="mode-dot" />
          <span>{mode === "farmer" ? t("mode.farmer") : t("mode.expert")}</span>
        </button>
      </div>
    </aside>
  );
}
