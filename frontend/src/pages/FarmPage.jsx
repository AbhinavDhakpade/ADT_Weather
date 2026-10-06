import { useState, useCallback } from "react";
import { useAppSettings } from "../context/AppSettingsContext";
import { useAppData } from "../context/DataContext";
import { LoadingScreen, ErrorScreen } from "../components/common/StatusScreens";
import FarmMap from "../components/dashboard/FarmMap";
import { patchFarm } from "../api/client";
import { haToAcres, formatArea, formatYieldAcres, tHaToTAcre } from "../utils/helpers";

const SOIL_OPTIONS = [
  "Black Cotton", "Loamy", "Sandy", "Clay", "Red Soil", "Laterite", "Alluvial",
];
const IRRIGATION_OPTIONS = [
  "Drip", "Sprinkler", "Flood", "Furrow", "Rainfed",
];

export default function FarmPage() {
  const { t } = useAppSettings();
  const { dashboard, loading, error, refresh } = useAppData();

  // ALL hooks must be declared unconditionally before any early returns
  const [editMode, setEditMode] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [fieldErrors, setFieldErrors] = useState({});
  const [draft, setDraft] = useState(null);

  // useCallback must also be before early returns
  const handleMapClick = useCallback((lat, lng) => {
    setDraft((prev) => ({ ...prev, latitude: lat, longitude: lng }));
    setFieldErrors((prev) => ({ ...prev, latitude: null, longitude: null }));
  }, []);

  if (loading && !dashboard) return <LoadingScreen />;
  if (error) return <ErrorScreen onRetry={refresh} />;
  if (!dashboard) return null;

  const { farm, current_gdd, current_stage, yield_ml_prediction, ml_models_available } = dashboard;

  // ------ Open edit mode: copy live farm data into a mutable draft ------
  const openEdit = () => {
    setDraft({
      farm_name: farm.farm_name,
      farmer_name: farm.farmer_name,
      phone: farm.phone || "",
      village: farm.village,
      latitude: farm.latitude,
      longitude: farm.longitude,
      crop_name: farm.crop_name || "Sugarcane",
      variety: farm.variety,
      planting_date: farm.planting_date,
      soil_type: farm.soil_type,
      irrigation_method: farm.irrigation_method,
      area_hectares: farm.area_hectares,
      expected_harvest: farm.expected_harvest,
      expected_yield_t_ha: farm.expected_yield_t_ha,
      revenue_estimate: farm.revenue_estimate,
    });
    setFieldErrors({});
    setSaveSuccess(false);
    setEditMode(true);
  };

  const closeEdit = () => {
    setEditMode(false);
    setDraft(null);
    setFieldErrors({});
  };

  // ------ Handle map click: update lat/lng in draft ------
  // Note: handleMapClick is defined above the early returns to satisfy Rules of Hooks

  // ------ Validate ------
  const validate = (d) => {
    const errs = {};
    if (!d.farm_name?.trim()) errs.farm_name = t("farm.validFarmName");
    if (!d.farmer_name?.trim()) errs.farmer_name = t("farm.validFarmerName");
    if (!d.crop_name?.trim()) errs.crop_name = t("farm.validCropName");
    if (!d.village?.trim()) errs.village = t("farm.validVillage");
    const lat = parseFloat(d.latitude);
    const lng = parseFloat(d.longitude);
    if (isNaN(lat) || lat < -90 || lat > 90) errs.latitude = "Must be between -90 and 90";
    if (isNaN(lng) || lng < -180 || lng > 180) errs.longitude = "Must be between -180 and 180";
    const area = parseFloat(d.area_hectares);
    if (isNaN(area) || area <= 0) errs.area_hectares = "Must be greater than 0";
    return errs;
  };

  // ------ Save ------
  const handleSave = async () => {
    const errs = validate(draft);
    if (Object.keys(errs).length) {
      setFieldErrors(errs);
      return;
    }
    setSaving(true);
    setFieldErrors({});
    try {
      await patchFarm(farm.id, {
        ...draft,
        latitude: parseFloat(draft.latitude),
        longitude: parseFloat(draft.longitude),
        area_hectares: parseFloat(draft.area_hectares),
      });
      await refresh();      // reload dashboard data from API
      setSaveSuccess(true);
      setTimeout(() => {
        setEditMode(false);
        setSaveSuccess(false);
        setDraft(null);
      }, 1500);
    } catch (e) {
      const apiErrors = e.response?.data;
      if (apiErrors && typeof apiErrors === "object") {
        setFieldErrors(apiErrors);
      } else {
        setFieldErrors({ general: t("farm.saveError") });
      }
    } finally {
      setSaving(false);
    }
  };

  // ------ Field change helper ------
  const set = (field) => (e) => {
    setDraft((prev) => ({ ...prev, [field]: e.target.value }));
    if (fieldErrors[field]) setFieldErrors((prev) => ({ ...prev, [field]: null }));
  };

  // ------ View rows ------
  const rows = [
    [t("farm.farmName"), farm.farm_name],
    [t("farm.farmer"), farm.farmer_name],
    [t("farm.phone"), farm.phone || "—"],
    [t("farm.village"), farm.village],
    [t("farm.gps"), `${farm.latitude.toFixed(5)}°N, ${farm.longitude.toFixed(5)}°E`],
    [t("farm.crop"), `${farm.crop_name || "Sugarcane"} (${farm.variety})`],
    [t("farm.plantingDate"), farm.planting_date],
    [t("farm.cropStage"), current_stage],
    [t("farm.soilType"), farm.soil_type],
    [t("farm.irrigationMethod"), farm.irrigation_method],
    [t("farm.farmArea"), formatArea(farm.area_hectares)],
    [t("farm.gddAccumulated"), `${Math.round(current_gdd).toLocaleString()} (Base ${farm.base_temp_c}°C)`],
    [t("farm.expectedHarvest"), farm.expected_harvest],
  ];

  return (
    <>
      <div className="section-h">
        <h2>🗺️ {t("pageTitles.farm")}</h2>
        {!editMode && (
          <button className="btn-save" style={{ padding: "8px 18px", fontSize: 13 }} onClick={openEdit}>
            ✏️ Edit Farm Info
          </button>
        )}
      </div>

      {/* ===== VIEW MODE ===== */}
      {!editMode && (
        <>
          <div className="grid-2">
            <div className="card static">
              <div className="card-title">{t("farm.details")}</div>
              <div className="farm-grid mt-12">
                {rows.map(([key, val]) => (
                  <div className="farm-row" key={key}>
                    <span className="farm-key">{key}</span>
                    <span className="farm-val">{val}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="card static">
              <div className="card-title">{t("farm.farmMap")}</div>
              <div className="mt-12">
                <FarmMap farm={farm} />
              </div>
              <div className="card-badge badge-green mt-8">
                📍 {haToAcres(farm.area_hectares)} Acres · {farm.crop_name || "Sugarcane"} ({farm.variety}) · {t("farm.clickExplore")}
              </div>
            </div>
          </div>

          {/* Yield prediction card */}
          <div className="card mt-16 static">
            <div className="card-header">
              <span className="card-title">{t("farm.yieldPrediction")}</span>
              {ml_models_available?.yield && <span className="ml-badge">🌲 ML Powered</span>}
            </div>
            <div className="grid-3 mt-12">
              <div className="info-item">
                <div className="info-item-label">Expected Yield (Baseline)</div>
                <div className="info-item-val">{formatYieldAcres(farm.expected_yield_t_ha)}</div>
              </div>
              <div className="info-item">
                <div className="info-item-label">ML Predicted Yield</div>
                <div className="info-item-val" style={{ color: "var(--green-mid)" }}>
                  {yield_ml_prediction ? formatYieldAcres(yield_ml_prediction.yield_t_ha) : "—"}
                </div>
              </div>
              <div className="info-item">
                <div className="info-item-label">Revenue Estimate</div>
                <div className="info-item-val">{farm.revenue_estimate}</div>
              </div>
            </div>
            {yield_ml_prediction && (
              <div className="text-xs text-muted mt-12">
                Predicted using a GradientBoosting regressor trained on GDD progress, average disease
                pressure, irrigation adequacy, and soil type — a second opinion alongside the baseline.
              </div>
            )}
          </div>
        </>
      )}

      {/* ===== EDIT MODE ===== */}
      {editMode && draft && (
        <div className="card static">
          <div className="card-header">
            <span className="card-title" style={{ fontSize: 17 }}>✏️ Edit Farm Information</span>
            <button className="btn-cancel" onClick={closeEdit}>✕ Cancel</button>
          </div>

          {saveSuccess && (
            <div className="farm-edit-success">✅ Farm information saved successfully!</div>
          )}
          {fieldErrors.general && (
            <div className="farm-edit-error" style={{ marginBottom: 12 }}>⚠️ {fieldErrors.general}</div>
          )}

          {/* Live map — full width, with click-to-place-marker */}
          <div style={{ marginBottom: 20 }}>
            <div className="farm-edit-label mb-4">
              📍 Farm Location on Map — click to set coordinates
            </div>
            <FarmMap
              farm={farm}
              editMode
              editLat={parseFloat(draft.latitude)}
              editLng={parseFloat(draft.longitude)}
              editArea={parseFloat(draft.area_hectares) || 1}
              onMapClick={handleMapClick}
            />
            <div className="farm-edit-coord-hint mt-6">
              Orange dashed circle shows the farm area sized to {draft.area_hectares ? `${draft.area_hectares} ha (${haToAcres(draft.area_hectares)} Acres)` : "—"}.
              Click anywhere to reposition the marker.
            </div>
          </div>

          <div className="farm-edit-grid">

            {/* === FARMER DETAILS === */}
            <div className="farm-edit-group">
              <label className="farm-edit-label">Farm Name *</label>
              <input className={`farm-edit-input ${fieldErrors.farm_name ? "error" : ""}`} value={draft.farm_name} onChange={set("farm_name")} placeholder="e.g. Dhakpade Farm" />
              {fieldErrors.farm_name && <span className="farm-edit-error">{fieldErrors.farm_name}</span>}
            </div>

            <div className="farm-edit-group">
              <label className="farm-edit-label">Farmer Name *</label>
              <input className={`farm-edit-input ${fieldErrors.farmer_name ? "error" : ""}`} value={draft.farmer_name} onChange={set("farmer_name")} placeholder="e.g. Abhinav R. Dhakpade" />
              {fieldErrors.farmer_name && <span className="farm-edit-error">{fieldErrors.farmer_name}</span>}
            </div>

            <div className="farm-edit-group">
              <label className="farm-edit-label">Phone Number</label>
              <input className="farm-edit-input" value={draft.phone} onChange={set("phone")} placeholder="+91 98765 43210" type="tel" />
            </div>

            <div className="farm-edit-group">
              <label className="farm-edit-label">Village / Location *</label>
              <input className={`farm-edit-input ${fieldErrors.village ? "error" : ""}`} value={draft.village} onChange={set("village")} placeholder="e.g. Baramati, Pune" />
              {fieldErrors.village && <span className="farm-edit-error">{fieldErrors.village}</span>}
            </div>

            {/* === COORDINATES === */}
            <div className="farm-edit-group full">
              <label className="farm-edit-label">GPS Coordinates * (or click map above)</label>
              <div className="farm-edit-coord-row">
                <div>
                  <input
                    className={`farm-edit-input ${fieldErrors.latitude ? "error" : ""}`}
                    value={draft.latitude}
                    onChange={set("latitude")}
                    placeholder="Latitude (e.g. 18.1514)"
                    type="number"
                    step="0.0001"
                  />
                  {fieldErrors.latitude && <span className="farm-edit-error">{fieldErrors.latitude}</span>}
                </div>
                <div>
                  <input
                    className={`farm-edit-input ${fieldErrors.longitude ? "error" : ""}`}
                    value={draft.longitude}
                    onChange={set("longitude")}
                    placeholder="Longitude (e.g. 74.5815)"
                    type="number"
                    step="0.0001"
                  />
                  {fieldErrors.longitude && <span className="farm-edit-error">{fieldErrors.longitude}</span>}
                </div>
                <div>
                  <input
                    className={`farm-edit-input ${fieldErrors.area_hectares ? "error" : ""}`}
                    value={draft.area_hectares}
                    onChange={set("area_hectares")}
                    placeholder="Area in hectares (e.g. 2.4 = 5.93 Acres)"
                    type="number"
                    step="0.1"
                    min="0.1"
                  />
                  {fieldErrors.area_hectares && <span className="farm-edit-error">{fieldErrors.area_hectares}</span>}
                </div>
              </div>
              <div className="farm-edit-coord-hint">
                Tip: you can also click anywhere on the map above to auto-fill latitude and longitude.
              </div>
            </div>

            {/* === CROP DETAILS === */}
            <div className="farm-edit-group">
              <label className="farm-edit-label">Crop Name *</label>
              <input
                className={`farm-edit-input ${fieldErrors.crop_name ? "error" : ""}`}
                value={draft.crop_name}
                onChange={set("crop_name")}
                placeholder="e.g. Sugarcane, Wheat, Rice"
              />
              {fieldErrors.crop_name && <span className="farm-edit-error">{fieldErrors.crop_name}</span>}
            </div>

            <div className="farm-edit-group">
              <label className="farm-edit-label">Variety / Cultivar</label>
              <input
                className="farm-edit-input"
                value={draft.variety}
                onChange={set("variety")}
                placeholder="e.g. Co 86032"
              />
            </div>

            <div className="farm-edit-group">
              <label className="farm-edit-label">Planting Date</label>
              <input
                className="farm-edit-input"
                value={draft.planting_date}
                onChange={set("planting_date")}
                type="date"
              />
            </div>

            <div className="farm-edit-group">
              <label className="farm-edit-label">Expected Harvest</label>
              <input
                className="farm-edit-input"
                value={draft.expected_harvest}
                onChange={set("expected_harvest")}
                placeholder="e.g. Dec 2025"
              />
            </div>

            {/* === SOIL & IRRIGATION === */}
            <div className="farm-edit-group">
              <label className="farm-edit-label">Soil Type</label>
              <select className="farm-edit-input farm-edit-select" value={draft.soil_type} onChange={set("soil_type")}>
                {SOIL_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>

            <div className="farm-edit-group">
              <label className="farm-edit-label">Irrigation Method</label>
              <select className="farm-edit-input farm-edit-select" value={draft.irrigation_method} onChange={set("irrigation_method")}>
                {IRRIGATION_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>

            {/* === YIELD ESTIMATES === */}
            <div className="farm-edit-group">
              <label className="farm-edit-label">Expected Yield (t/acre)</label>
              <input
                className="farm-edit-input"
                value={draft.expected_yield_t_ha}
                onChange={set("expected_yield_t_ha")}
                placeholder="e.g. 31–34 (t/acre)"
              />
            </div>

            <div className="farm-edit-group">
              <label className="farm-edit-label">Revenue Estimate</label>
              <input
                className="farm-edit-input"
                value={draft.revenue_estimate}
                onChange={set("revenue_estimate")}
                placeholder="e.g. ₹3.5–3.8 L"
              />
            </div>
          </div>

          <div className="farm-edit-actions">
            <button className="btn-cancel" onClick={closeEdit} disabled={saving}>
              Cancel
            </button>
            <button className="btn-save" onClick={handleSave} disabled={saving}>
              {saving ? t("farm.savingBtn") : t("farm.saveBtn")}
            </button>
          </div>
        </div>
      )}
    </>
  );
}
