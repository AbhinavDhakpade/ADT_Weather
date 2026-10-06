import AnimatedWeatherIcon from "./AnimatedWeatherIcon";
import { formatDayName, formatDateLabel } from "../../utils/helpers";
import { useAppSettings } from "../../context/AppSettingsContext";

// Compare a date string from the API ("2026-07-01") against the browser's
// actual current date — this is the only reliable source of truth for "today"
// in the frontend, since the DB row dates depend on when sync_weather last ran.
function isToday(dateStr) {
  if (!dateStr) return false;
  const now = new Date();
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  return dateStr === today;
}

export default function WeatherTimelineStrip({ days, activeIndex, onSelect }) {
  const { t } = useAppSettings();

  // Marathi day names
  const mrDays = {
    Sun: "रवि", Mon: "सोम", Tue: "मंगळ", Wed: "बुध",
    Thu: "गुरु", Fri: "शुक्र", Sat: "शनि",
  };
  const hiDays = {
    Sun: "रवि", Mon: "सोम", Tue: "मंगल", Wed: "बुध",
    Thu: "गुरु", Fri: "शुक्र", Sat: "शनि",
  };
  const lang = t("appName") === "अ‍ॅग्रीऑरा" ? "mr" : t("appName") === "एग्रीऑरा" ? "hi" : "en";

  function getDayLabel(dateStr) {
    const eng = formatDayName(dateStr); // e.g. "Tue"
    if (lang === "mr") return mrDays[eng] || eng;
    if (lang === "hi") return hiDays[eng] || eng;
    return eng;
  }

  const todayLabel = lang === "mr" ? "आज" : lang === "hi" ? "आज" : "Today";

  return (
    <div className="wx-timeline">
      {days.map((d, i) => {
        const dayIsToday = isToday(d.date);
        return (
          <button
            key={d.date}
            className={`wx-timeline-item${i === activeIndex ? " active" : ""}${dayIsToday ? " wx-today" : ""}`}
            onClick={() => onSelect?.(i)}
          >
            <div className="wx-timeline-day">
              {dayIsToday ? todayLabel : getDayLabel(d.date)}
            </div>
            <div className="wx-timeline-date">{formatDateLabel(d.date)}</div>
            <AnimatedWeatherIcon code={d.weather_code} size={36} />
            <div className="wx-timeline-temp">
              <span className="wx-timeline-hi">{Math.round(d.temp_max_c)}°</span>
              <span className="wx-timeline-lo">{Math.round(d.temp_min_c)}°</span>
            </div>
            {d.precipitation_probability_pct > 20 && (
              <div className="wx-timeline-rain">💧{Math.round(d.precipitation_probability_pct)}%</div>
            )}
          </button>
        );
      })}
    </div>
  );
}
