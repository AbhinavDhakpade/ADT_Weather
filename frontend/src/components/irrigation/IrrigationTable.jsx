import { decisionColor } from "../../utils/helpers";
import { useAppSettings } from "../../context/AppSettingsContext";

export default function IrrigationTable({ rules }) {
  const { t } = useAppSettings();
  const th = t("irrigation.tableHeaders");

  const columns = [
    th.sr, th.soilType, th.stage, th.moisture,
    th.rainfall, th.temp, th.rh, th.vpd,
    th.etc, th.req, th.decision, th.remarks,
  ];

  return (
    <table className="data-table">
      <thead>
        <tr>
          {columns.map((c) => (
            <th key={c}>{c}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rules.map((r) => (
          <tr key={r.id}>
            <td>{r.sr_no}</td>
            <td style={{ fontWeight: 600 }}>{r.soil_type}</td>
            <td>{r.crop_stage}</td>
            <td>{r.moisture_pct}</td>
            <td>{r.rainfall_mm_week}</td>
            <td>{r.temp_c}</td>
            <td>{r.relative_humidity_pct}</td>
            <td>{r.vpd_kpa}</td>
            <td>{r.etc_mm_day}</td>
            <td>{r.requirement_l_plant}</td>
            <td style={{ fontWeight: 700, color: decisionColor(r.decision) }}>{r.decision}</td>
            <td className="text-muted">{r.remark}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
