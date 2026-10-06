import { useEffect, useState, useCallback } from "react";
import { useAppSettings } from "../../context/AppSettingsContext";
import { fetchSchedulerStatus, runSchedulerNow } from "../../api/client";

const STATUS_BADGE = {
  success: "badge-green",
  partial: "badge-gold",
  failure: "badge-red",
};

function timeAgo(iso, locale) {
  if (!iso) return "—";
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return locale === "just now" ? "just now" : "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  return `${hrs}h ago`;
}

function timeUntil(iso) {
  if (!iso) return "—";
  const diffMs = new Date(iso).getTime() - Date.now();
  if (diffMs <= 0) return "due now";
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "<1m";
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  const rem = mins % 60;
  return `${hrs}h ${rem}m`;
}

/**
 * Scheduler Monitoring panel — shows whether the automatic hourly weather
 * sync (advisory/scheduler.py, APScheduler) is alive in this backend process,
 * when it last ran and with what result, and when it'll run next. Includes a
 * manual "Run now" trigger for admins who don't want to wait for the next tick.
 */
export default function SchedulerStatusCard({ onClick }) {
  const { t } = useAppSettings();
  const [status, setStatus] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    fetchSchedulerStatus()
      .then((data) => {
        setStatus(data);
        setError(false);
      })
      .catch(() => setError(true));
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 60000); // refresh once a minute
    return () => clearInterval(interval);
  }, [load]);

  const handleRunNow = async (e) => {
    e.stopPropagation();
    setRunning(true);
    try {
      await runSchedulerNow();
    } finally {
      setRunning(false);
      load();
    }
  };

  const lastRun = status?.last_run;
  const badgeClass = lastRun ? STATUS_BADGE[lastRun.status] || "badge-gold" : "badge-gold";

  return (
    <div className="card static" onClick={onClick}>
      <div className="card-header">
        <span className="card-title">⏱ {t("scheduler.title")}</span>
        <span className={`tag ${status?.running ? "badge-green" : "badge-red"}`}>
          {status?.running ? t("scheduler.live") : t("scheduler.stopped")}
        </span>
      </div>

      {error && <div className="text-sm text-muted">{t("scheduler.unreachable")}</div>}

      {!error && status && (
        <>
          <div className="soil-row">
            <span className="soil-label">{t("scheduler.interval")}</span>
            <span className="soil-val">{t("scheduler.everyN").replace("{n}", status.interval_minutes)}</span>
          </div>
          <div className="soil-row">
            <span className="soil-label">{t("scheduler.nextRun")}</span>
            <span className="soil-val">{timeUntil(status.next_run_at)}</span>
          </div>
          <div className="soil-row">
            <span className="soil-label">{t("scheduler.lastRun")}</span>
            <span className="soil-val">
              {lastRun ? timeAgo(lastRun.started_at) : t("scheduler.never")}
            </span>
          </div>

          {lastRun && (
            <div className="mt-8" style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
              <span className={`tag ${badgeClass}`}>{t(`scheduler.status.${lastRun.status}`)}</span>
              <span className="text-sm text-muted">
                {t("scheduler.recordsSummary")
                  .replace("{fetched}", lastRun.records_fetched)
                  .replace("{farms}", lastRun.farms_processed)}
              </span>
              {lastRun.duplicates_removed > 0 && (
                <span className="text-sm text-muted">
                  · {t("scheduler.duplicatesSkipped").replace("{n}", lastRun.duplicates_removed)}
                </span>
              )}
              {lastRun.retry_attempts > 0 && (
                <span className="text-sm text-muted">
                  · {t("scheduler.retries").replace("{n}", lastRun.retry_attempts)}
                </span>
              )}
            </div>
          )}

          {lastRun?.status === "failure" && (
            <div className="card-badge badge-red mt-8">
              ⚠ {lastRun.history_status === "failed" && "Open-Meteo history "}
              {lastRun.open_meteo_status === "failed" && "Open-Meteo forecast "}
              {t("scheduler.apiUnreachable")}
            </div>
          )}

          <button
            className="see-all mt-8"
            onClick={handleRunNow}
            disabled={running}
            style={{ background: "none", border: "none", cursor: running ? "wait" : "pointer" }}
          >
            {running ? t("scheduler.running") : t("scheduler.runNow")}
          </button>
        </>
      )}
    </div>
  );
}
