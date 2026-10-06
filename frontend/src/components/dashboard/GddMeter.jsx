import { useAppSettings } from "../../context/AppSettingsContext";

export default function GddMeter({ currentGdd, baseTemp, currentStage, growthStages }) {
  const { t } = useAppSettings();
  const maxGdd = growthStages?.length ? growthStages[growthStages.length - 1].gdd_threshold : 5000;
  const pct = Math.min(100, (currentGdd / maxGdd) * 100);

  return (
    <div className="gdd-meter">
      <div className="flex align-center gap-8" style={{ marginBottom: 6 }}>
        <span style={{ fontSize: 13, fontWeight: 700 }}>{t("cards.accumulatedGdd")}</span>
        <span className="tag badge-green">
          {t("cards.baseTemp")} {baseTemp}°C
        </span>
      </div>
      <div className="gdd-track">
        <div className="gdd-fill" style={{ width: `${pct}%` }} />
        <div className="gdd-marker" style={{ left: `${pct}%` }} />
      </div>
      <div className="gdd-labels">
        {growthStages?.map((s) => (
          <span key={s.stage_name}>
            {s.stage_name}
            <br />
            {s.gdd_threshold}
          </span>
        ))}
      </div>
      <div className="mt-8 text-sm">
        <strong>
          {t("cards.currentGdd")}: {Math.round(currentGdd).toLocaleString()}
        </strong>{" "}
        · {t("cards.stage")}: <span className="tag badge-gold">{currentStage}</span>
      </div>
    </div>
  );
}
