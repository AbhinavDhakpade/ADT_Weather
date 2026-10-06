import { formatDateLabel, formatTime12h, uvLevel } from "../../utils/helpers";
import AnimatedWeatherIcon from "./AnimatedWeatherIcon";

export default function DayDetailPopover({ day, onClose }) {
  if (!day) return null;
  const uv = uvLevel(day.uv_index_max);

  return (
    <div className="day-popover-bg" onClick={onClose}>
      <div className="day-popover" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose} style={{ float: "right" }}>
          ✕
        </button>
        <div className="flex align-center gap-12">
          <AnimatedWeatherIcon code={day.weather_code} size={48} />
          <div>
            <div style={{ fontWeight: 800, fontSize: 16 }}>{formatDateLabel(day.date)}</div>
            <div className="text-sm text-muted">{day.condition_text}</div>
          </div>
        </div>
        <div className="info-grid mt-12">
          <div className="info-item">
            <div className="info-item-label">Temp</div>
            <div className="info-item-val">
              {Math.round(day.temp_max_c)}° / {Math.round(day.temp_min_c)}°C
            </div>
          </div>
          <div className="info-item">
            <div className="info-item-label">Humidity</div>
            <div className="info-item-val">{Math.round(day.humidity_pct)}%</div>
          </div>
          <div className="info-item">
            <div className="info-item-label">Rainfall</div>
            <div className="info-item-val">{day.rainfall_mm} mm</div>
          </div>
          <div className="info-item">
            <div className="info-item-label">Wind</div>
            <div className="info-item-val">{Math.round(day.wind_kmh)} km/h</div>
          </div>
          <div className="info-item">
            <div className="info-item-label">VPD</div>
            <div className="info-item-val">{day.vpd_kpa} kPa</div>
          </div>
          <div className="info-item">
            <div className="info-item-label">ET₀</div>
            <div className="info-item-val">{day.et0_mm} mm</div>
          </div>
          {uv && (
            <div className="info-item">
              <div className="info-item-label">UV Index</div>
              <div className="info-item-val" style={{ color: uv.color }}>
                {Math.round(day.uv_index_max)} ({uv.label})
              </div>
            </div>
          )}
          {day.sunrise && (
            <div className="info-item">
              <div className="info-item-label">Sunrise / Sunset</div>
              <div className="info-item-val" style={{ fontSize: 13 }}>
                {formatTime12h(day.sunrise)} – {formatTime12h(day.sunset)}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
