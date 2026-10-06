import { useState } from "react";
import Modal from "../common/Modal";
import { addFarmerManual, addFarmersFromKml } from "../../api/client";

const SOIL_OPTIONS = ["Black Cotton", "Loamy", "Sandy", "Clay", "Red Soil", "Laterite", "Alluvial"];
const IRRIGATION_OPTIONS = ["Drip", "Sprinkler", "Flood", "Furrow", "Rainfed"];

const FIELDS = [
  { key: "farmer_name", label: "Farmer name *", type: "text" },
  { key: "phone", label: "Phone", type: "text" },
  { key: "village", label: "Village *", type: "text" },
  { key: "farm_name", label: "Farm name (optional)", type: "text" },
  { key: "latitude", label: "Latitude *", type: "number" },
  { key: "longitude", label: "Longitude *", type: "number" },
  { key: "area_hectares", label: "Area (hectares) *", type: "number" },
  { key: "crop_name", label: "Crop", type: "text" },
  { key: "variety", label: "Variety", type: "text" },
  { key: "planting_date", label: "Planting date *", type: "date" },
  { key: "soil_type", label: "Soil type", type: "select", options: SOIL_OPTIONS },
  { key: "irrigation_method", label: "Irrigation method", type: "select", options: IRRIGATION_OPTIONS },
  { key: "pump_hp", label: "Pump HP", type: "number" },
  { key: "pump_discharge_l_s", label: "Pump discharge (L/s)", type: "number" },
];

const REQUIRED = ["farmer_name", "village", "latitude", "longitude", "area_hectares", "planting_date"];
const NUMBER_KEYS = ["latitude", "longitude", "area_hectares", "pump_hp", "pump_discharge_l_s"];

const emptyForm = () => ({
  farmer_name: "", phone: "", village: "", farm_name: "",
  latitude: "", longitude: "", area_hectares: "",
  crop_name: "Sugarcane", variety: "Co 86032",
  planting_date: new Date().toISOString().slice(0, 10),
  soil_type: "Black Cotton", irrigation_method: "Drip",
  pump_hp: "5", pump_discharge_l_s: "5",
});

const STATUS_LABEL = {
  created: { text: "New farmer", color: "#2e7d32" },
  added: { text: "New farm", color: "#2e7d32" },
  exists: { text: "Already present", color: "#b26a00" },
  error: { text: "Error", color: "#c62828" },
};

const inputStyle = {
  width: "100%", padding: "8px 10px", borderRadius: 8, fontSize: 14,
  border: "1px solid var(--border)", background: "var(--bg)", color: "inherit",
};
const errorStyle = { color: "#c62828", fontSize: 12, marginTop: 4 };

// Read the server's error reply: per-field messages, or one general message.
function readErrors(err) {
  const d = err.response?.data;
  if (d && typeof d === "object" && !d.detail) return { fields: d, general: "" };
  return { fields: {}, general: d?.detail || "Could not reach the server. Please try again." };
}

const csvCell = (v) => {
  const s = String(v ?? "");
  const safe = /^[=+\-@]/.test(s) ? `'${s}` : s; // stop spreadsheet formula tricks
  return `"${safe.replace(/"/g, '""')}"`;
};

function downloadCredentials(rows) {
  const lines = [
    ["Farmer", "Username", "Password", "Farm id"],
    ...rows.map((r) => [r.farmer_name, r.username, r.password, r.farm_id]),
  ];
  const csv = lines.map((l) => l.map(csvCell).join(",")).join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "agriaura-new-logins.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export default function AddFarmerModal({ open, onClose, onAdded }) {
  // view: "choose" | "kml" | "kmlResult" | "manual" | "manualResult"
  const [view, setView] = useState("choose");
  const [files, setFiles] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [busy, setBusy] = useState(false);
  const [general, setGeneral] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [kmlData, setKmlData] = useState(null);
  const [manualData, setManualData] = useState(null);
  const [changed, setChanged] = useState(false);

  const clearMessages = () => { setGeneral(""); setFieldErrors({}); };

  const goTo = (next) => { clearMessages(); setView(next); };

  const handleClose = () => {
    if (changed) onAdded?.();
    // Wipe everything (including one-time passwords) from memory.
    setView("choose"); setFiles([]); setForm(emptyForm()); setKmlData(null);
    setManualData(null); setChanged(false); clearMessages();
    onClose();
  };

  const submitKml = async () => {
    if (files.length === 0) { setGeneral("Please choose at least one .kml file."); return; }
    setBusy(true); clearMessages();
    try {
      const data = await addFarmersFromKml(files);
      setKmlData(data);
      if (data.counts.created + data.counts.added > 0) setChanged(true);
      setView("kmlResult");
    } catch (err) {
      setGeneral(readErrors(err).general || "Upload failed. Please check the files and try again.");
    } finally {
      setBusy(false);
    }
  };

  const submitManual = async (e) => {
    e.preventDefault();
    const problems = {};
    REQUIRED.forEach((k) => {
      if (String(form[k]).trim() === "") problems[k] = "This field is required.";
    });
    NUMBER_KEYS.forEach((k) => {
      if (String(form[k]).trim() !== "" && Number.isNaN(Number(form[k]))) problems[k] = "Enter a number.";
    });
    if (Object.keys(problems).length) { setFieldErrors(problems); setGeneral(""); return; }

    const payload = { ...form };
    NUMBER_KEYS.forEach((k) => { payload[k] = Number(form[k]); });

    setBusy(true); clearMessages();
    try {
      const data = await addFarmerManual(payload);
      setManualData(data);
      setChanged(true);
      setView("manualResult");
    } catch (err) {
      const { fields, general: g } = readErrors(err);
      setFieldErrors(fields);
      setGeneral(g || "Please correct the highlighted fields.");
    } finally {
      setBusy(false);
    }
  };

  const backButton = (
    <button className="btn-cancel" type="button" onClick={() => goTo("choose")} style={{ padding: "8px 16px" }}>
      ← Back
    </button>
  );

  const credentials = (kmlData?.results || []).filter((r) => r.password);

  return (
    <Modal open={open} onClose={handleClose}>
      <div className="modal-header">
        <h2>➕ Add farmer</h2>
        <button className="modal-close" onClick={handleClose} aria-label="Close">✕</button>
      </div>

      {general && <p style={{ ...errorStyle, fontSize: 14, marginBottom: 12 }}>{general}</p>}

      {/* ---------- 1. choose ---------- */}
      {view === "choose" && (
        <div>
          <p style={{ marginBottom: 16 }}>How do you want to add the farmer?</p>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
            {[
              { id: "kml", icon: "📁", title: "Add KML files", text: "Upload one or more field boundary files. Farmers and logins are created automatically." },
              { id: "manual", icon: "✍️", title: "Add manually", text: "Type in the farmer's details and create a login for them." },
            ].map((o) => (
              <button
                key={o.id}
                type="button"
                onClick={() => goTo(o.id)}
                style={{
                  flex: "1 1 240px", textAlign: "left", padding: 20, borderRadius: 12, cursor: "pointer",
                  border: "1px solid var(--border)", background: "var(--bg)", color: "inherit",
                }}
              >
                <div style={{ fontSize: 28 }}>{o.icon}</div>
                <div style={{ fontWeight: 800, margin: "8px 0 4px" }}>{o.title}</div>
                <div style={{ fontSize: 13, opacity: 0.75 }}>{o.text}</div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ---------- 2a. KML upload ---------- */}
      {view === "kml" && (
        <div>
          <p style={{ marginBottom: 12 }}>
            Choose one or more KML files (one field boundary per file, exported from Google Earth Pro).
          </p>
          <input
            type="file"
            accept=".kml"
            multiple
            onChange={(e) => setFiles(Array.from(e.target.files || []))}
          />
          {files.length > 0 && (
            <p style={{ marginTop: 8, fontSize: 13, opacity: 0.8 }}>{files.length} file(s) selected</p>
          )}
          <div style={{ display: "flex", gap: 10, marginTop: 20 }}>
            {backButton}
            <button className="btn-save" type="button" disabled={busy} onClick={submitKml} style={{ padding: "8px 18px" }}>
              {busy ? "Importing…" : "Import"}
            </button>
          </div>
        </div>
      )}

      {/* ---------- 2b. KML result ---------- */}
      {view === "kmlResult" && kmlData && (
        <div>
          <p style={{ marginBottom: 12 }}>
            <strong>{kmlData.counts.created}</strong> new farmer(s),{" "}
            <strong>{kmlData.counts.added}</strong> extra farm(s) for existing farmers,{" "}
            <strong>{kmlData.counts.exists}</strong> already present,{" "}
            <strong>{kmlData.counts.error}</strong> error(s).
          </p>

          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ textAlign: "left" }}><th>File</th><th>Result</th><th>Details</th></tr>
              </thead>
              <tbody>
                {kmlData.results.map((r, i) => {
                  const s = STATUS_LABEL[r.status] || STATUS_LABEL.error;
                  return (
                    <tr key={i} style={{ borderTop: "1px solid var(--border)" }}>
                      <td style={{ padding: "6px 8px 6px 0" }}>{r.filename}</td>
                      <td style={{ padding: "6px 8px", color: s.color, fontWeight: 700, whiteSpace: "nowrap" }}>{s.text}</td>
                      <td style={{ padding: "6px 0 6px 8px" }}>{r.message}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {credentials.length > 0 && (
            <div style={{ marginTop: 20 }}>
              <h3 style={{ marginBottom: 4 }}>New logins (shown only once)</h3>
              <p style={{ fontSize: 13, opacity: 0.8, marginBottom: 8 }}>
                Passwords are stored hashed and cannot be shown again. Download or copy them now.
              </p>
              <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ textAlign: "left" }}><th>Farmer</th><th>Username</th><th>Password</th></tr>
                </thead>
                <tbody>
                  {credentials.map((r, i) => (
                    <tr key={i} style={{ borderTop: "1px solid var(--border)" }}>
                      <td style={{ padding: "6px 8px 6px 0" }}>{r.farmer_name}</td>
                      <td><code>{r.username}</code></td>
                      <td><code>{r.password}</code></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <button
                className="btn-primary"
                type="button"
                style={{ marginTop: 12 }}
                onClick={() => downloadCredentials(credentials)}
              >
                Download credentials (CSV)
              </button>
            </div>
          )}

          <div style={{ display: "flex", gap: 10, marginTop: 24 }}>
            <button className="btn-cancel" type="button" style={{ padding: "8px 16px" }}
              onClick={() => { setFiles([]); setKmlData(null); goTo("kml"); }}>
              Import more files
            </button>
            <button className="btn-save" type="button" style={{ padding: "8px 18px" }} onClick={handleClose}>
              Done
            </button>
          </div>
        </div>
      )}

      {/* ---------- 3a. manual form ---------- */}
      {view === "manual" && (
        <form onSubmit={submitManual} noValidate>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: 12 }}>
            {FIELDS.map((f) => (
              <div key={f.key}>
                <label style={{ display: "block", fontSize: 12, fontWeight: 700, marginBottom: 4 }}>
                  {f.label}
                </label>
                {f.type === "select" ? (
                  <select
                    style={inputStyle}
                    value={form[f.key]}
                    onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
                  >
                    {f.options.map((o) => <option key={o} value={o}>{o}</option>)}
                  </select>
                ) : (
                  <input
                    style={inputStyle}
                    type={f.type}
                    step={f.type === "number" ? "any" : undefined}
                    value={form[f.key]}
                    onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
                  />
                )}
                {fieldErrors[f.key] && (
                  <div style={errorStyle}>
                    {Array.isArray(fieldErrors[f.key]) ? fieldErrors[f.key].join(" ") : String(fieldErrors[f.key])}
                  </div>
                )}
              </div>
            ))}
          </div>
          <div style={{ display: "flex", gap: 10, marginTop: 20 }}>
            {backButton}
            <button className="btn-save" type="submit" disabled={busy} style={{ padding: "8px 18px" }}>
              {busy ? "Saving…" : "Add farmer"}
            </button>
          </div>
        </form>
      )}

      {/* ---------- 3b. manual result ---------- */}
      {view === "manualResult" && manualData && (
        <div>
          <p style={{ marginBottom: 12 }}>
            <strong>Farmer added.</strong> {manualData.farm.farmer_name} now has farm #{manualData.farm.id}.
          </p>
          <h3 style={{ marginBottom: 4 }}>Login (shown only once)</h3>
          <p style={{ fontSize: 13, opacity: 0.8, marginBottom: 8 }}>
            The password is stored hashed and cannot be shown again. Copy it now.
          </p>
          <table style={{ fontSize: 14 }}>
            <tbody>
              <tr><td style={{ paddingRight: 16 }}>Username</td><td><code>{manualData.login.username}</code></td></tr>
              <tr><td style={{ paddingRight: 16 }}>Password</td><td><code>{manualData.login.password}</code></td></tr>
            </tbody>
          </table>
          <div style={{ display: "flex", gap: 10, marginTop: 20, flexWrap: "wrap" }}>
            <button
              className="btn-primary"
              type="button"
              onClick={() =>
                navigator.clipboard?.writeText(
                  `Username: ${manualData.login.username}\nPassword: ${manualData.login.password}`
                )
              }
            >
              Copy login
            </button>
            <button className="btn-cancel" type="button" style={{ padding: "8px 16px" }}
              onClick={() => { setForm(emptyForm()); setManualData(null); goTo("manual"); }}>
              Add another farmer
            </button>
            <button className="btn-save" type="button" style={{ padding: "8px 18px" }} onClick={handleClose}>
              Done
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}