import { useState } from "react";
import AddFarmerModal from "../modals/AddFarmerModal";
import { useLocation } from "react-router-dom";
import { useAppSettings } from "../../context/AppSettingsContext";
import { useAppData } from "../../context/DataContext";
import { useAuth } from "../../context/AuthContext";

const PAGE_KEY_BY_PATH = {
  "/": "dashboard",
  "/weather": "weather",
  "/disease": "disease",
  "/irrigation": "irrigation",
  "/forecast": "forecast",
  "/alerts": "alerts",
  "/gdd": "gdd",
  "/farm": "farm",
  "/history": "history",
};

const LANGUAGES = [
  { code: "en", label: "EN" },
  { code: "mr", label: "MR" },
  { code: "hi", label: "HI" },
];

export default function Topbar() {
  const { toggleSidebar, lang, setLang, dark, toggleDark, t } = useAppSettings();
  const { refresh, loading, farms, farmId, selectFarm, reloadFarms } = useAppData();
  const location = useLocation();
  const { user, logout } = useAuth();
  const [addFarmerOpen, setAddFarmerOpen] = useState(false);

  const pageKey = PAGE_KEY_BY_PATH[location.pathname] || "dashboard";

  return (
    <div className="topbar">
      <button className="topbar-toggle" onClick={toggleSidebar} title="Toggle sidebar" aria-label="Toggle sidebar">
        ☰
      </button>
      <div className="topbar-title">{t(`pageTitles.${pageKey}`)}</div>
      <div className="topbar-chips">
        {LANGUAGES.map((l) => (
          <div
            key={l.code}
            className={`chip${lang === l.code ? " active" : ""}`}
            onClick={() => setLang(l.code)}
          >
            {l.label}
          </div>
        ))}
      </div>
      <div className="topbar-actions">
                {user?.is_staff && (
          <>
            <button
              className="btn-primary"
              onClick={() => setAddFarmerOpen(true)}
              style={{ whiteSpace: "nowrap" }}
            >
              ➕ Add farmer
            </button>
            <AddFarmerModal
              open={addFarmerOpen}
              onClose={() => setAddFarmerOpen(false)}
              onAdded={() => { reloadFarms(); }}
            />
          </>
        )}
                {user?.is_staff && farms.length > 1 && (
          <select
            value={farmId}
            onChange={(e) => selectFarm(e.target.value)}
            aria-label="Select farm"
            title="Select farm"
            style={{
              maxWidth: 200, padding: "6px 8px", borderRadius: 8,
              border: "1px solid var(--border)", background: "var(--surface)", color: "inherit",
            }}
          >
            {farms.map((f) => (
              <option key={f.id} value={f.id}>
                 #{f.id} · {user?.is_staff ? f.farmer_name : f.farm_name}
              </option>
            ))}
          </select>
        )}
        <button className="icon-btn" onClick={toggleDark} title="Dark Mode" aria-label="Toggle dark mode">
          🌙
        </button>
        <button
          className="icon-btn"
          onClick={refresh}
          title="Refresh"
          aria-label="Refresh data"
          style={{
            transform: loading ? "rotate(360deg)" : "none",
            transition: "transform 0.6s",
          }}
        >
          🔄
        </button>
                <button className="icon-btn" onClick={logout} title={`Log out (${user?.username})`} aria-label="Log out">
          🚪
        </button>
      </div>
    </div>
  );
}
