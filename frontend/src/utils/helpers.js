export function riskTag(pct) {
  if (pct >= 70) return { cls: "tag-very-high", labelKey: "disease.veryHigh", color: "#b80000" };
  if (pct >= 50) return { cls: "tag-high", labelKey: "disease.high", color: "#b85000" };
  if (pct >= 30) return { cls: "tag-moderate", labelKey: "disease.moderate", color: "#8a6200" };
  return { cls: "tag-low", labelKey: "disease.low", color: "#1a7a3e" };
}

export function decisionColor(decision) {
  const map = {
    High: "var(--red)",
    Medium: "var(--amber)",
    "Very Low": "var(--green-mid)",
    Low: "var(--sky)",
  };
  return map[decision] || "var(--text)";
}

export function formatDateLabel(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function formatDayName(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  return d.toLocaleDateString("en-US", { weekday: "short" });
}

export function formatDateLabelFull(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

export function capitalize(str) {
  if (!str) return "";
  return str.charAt(0).toUpperCase() + str.slice(1);
}

export function formatRelativeTime(isoString) {
  if (!isoString) return "";
  const then = new Date(isoString);
  const now = new Date();
  const diffMs = now - then;
  const diffMin = Math.round(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin === 1) return "1 minute ago";
  if (diffMin < 60) return `${diffMin} minutes ago`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr === 1) return "1 hour ago";
  if (diffHr < 24) return `${diffHr} hours ago`;
  const diffDay = Math.round(diffHr / 24);
  return diffDay === 1 ? "1 day ago" : `${diffDay} days ago`;
}

export function formatTime12h(timeStr) {
  if (!timeStr) return "";
  const [h, m] = timeStr.split(":").map(Number);
  const period = h >= 12 ? "PM" : "AM";
  const h12 = h % 12 === 0 ? 12 : h % 12;
  return `${h12}:${String(m).padStart(2, "0")} ${period}`;
}

export function uvLevel(uv) {
  if (uv === null || uv === undefined) return null;
  if (uv >= 11) return { label: "Extreme", color: "#7e22ce" };
  if (uv >= 8) return { label: "Very High", color: "#d63230" };
  if (uv >= 6) return { label: "High", color: "#e07b00" };
  if (uv >= 3) return { label: "Moderate", color: "#f5a623" };
  return { label: "Low", color: "#4caf78" };
}

export function windArrowRotation(degrees) {
  if (degrees === null || degrees === undefined) return 0;
  return (degrees + 180) % 360;
}

// ===================== UNIT CONVERSIONS =====================
// AgriAura displays area in ACRES (Indian farmers measure land in acres, not hectares).
// Yield is shown in tonnes per acre.
// Conversion: 1 hectare = 2.47105 acres | 1 t/ha = 0.40469 t/acre

export const HA_TO_ACRES = 2.47105;
export const THA_TO_TACRE = 0.40469;

/** Convert hectares to acres, 2 decimal places */
export function haToAcres(ha) {
  if (ha === null || ha === undefined || isNaN(ha)) return null;
  return Math.round(parseFloat(ha) * HA_TO_ACRES * 100) / 100;
}

/** Convert t/ha to t/acre, 1 decimal place */
export function tHaToTAcre(tHa) {
  if (tHa === null || tHa === undefined || isNaN(tHa)) return null;
  return Math.round(parseFloat(tHa) * THA_TO_TACRE * 10) / 10;
}

/** Format area with "Acres" label */
export function formatArea(areaHectares) {
  const acres = haToAcres(areaHectares);
  if (acres === null) return "—";
  return `${acres} Acres`;
}

/** Format yield — converts t/ha number or range string (e.g. "78–85") → t/acre */
export function formatYieldAcres(value) {
  if (!value) return "—";
  const s = String(value);
  const rangeMatch = s.match(/^([\d.]+)[–\-]([\d.]+)$/);
  if (rangeMatch) {
    const lo = tHaToTAcre(rangeMatch[1]);
    const hi = tHaToTAcre(rangeMatch[2]);
    return `${lo}–${hi} t/acre`;
  }
  const num = parseFloat(s);
  if (!isNaN(num)) return `${tHaToTAcre(num)} t/acre`;
  return s;
}
