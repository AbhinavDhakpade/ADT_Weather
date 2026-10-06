"""Write validation results as CSV, JSON, Markdown and a self-contained HTML report."""

from __future__ import annotations

import html
import json
from pathlib import Path

import pandas as pd

from .engine import VARIABLES

METRIC_COLS = ["n", "bias", "mae", "rmse", "r", "r2", "mean_model", "mean_station"]


def _f(v, nd=2):
    return "-" if v is None or (isinstance(v, float) and v != v) else f"{v:.{nd}f}"


def summary_rows(result) -> list[dict]:
    """Flatten the nested metrics into rows: scope, variable, metrics..."""
    rows = []
    for source, per_var in result.actual.items():
        for var, m in per_var.items():
            rows.append({"scope": f"actual:{source}", "variable": var, **m})
    for lead in sorted(result.forecast_by_lead):
        for var, m in result.forecast_by_lead[lead].items():
            rows.append({"scope": f"forecast:lead_{lead}d", "variable": var, **m})
    return rows


def _scope_order(rows):
    seen = []
    for r in rows:
        if r["scope"] not in seen:
            seen.append(r["scope"])
    return seen


def to_markdown(result, context) -> str:
    rows = summary_rows(result)
    out = [f"# Weather validation: {context['farm']} vs station '{context['station']}'", ""]
    out.append(f"- Period: {context['start'] or 'all data'} to {context['end'] or 'all data'}")
    out.append(f"- Usable station days: {context['valid_station_days']} (min daily coverage {context['min_coverage']:.0%})")
    if context.get("station_to_farm_km") is not None:
        out.append(f"- Station is {context['station_to_farm_km']} km from the farm point"
                   + (f", {context['elevation_diff_m']:+} m in elevation" if context.get("elevation_diff_m") is not None else ""))
    out.append("- Error = model minus station (positive bias: the fetched data reads higher than the station)")
    out.append("")
    for scope in _scope_order(rows):
        out += [f"## {scope}", "", "| Variable | n | Bias | MAE | RMSE | r | Mean model | Mean station |",
                "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for r in (x for x in rows if x["scope"] == scope):
            label, unit = VARIABLES.get(r["variable"], (r["variable"], ""))
            out.append(f"| {label} ({unit}) | {r['n']} | {_f(r['bias'])} | {_f(r['mae'])} | {_f(r['rmse'])} | "
                       f"{_f(r['r'])} | {_f(r['mean_model'])} | {_f(r['mean_station'])} |")
        out.append("")
    rain_blocks = [(f"actual:{k}", v) for k, v in result.actual_rain_events.items()] + \
                  [(f"forecast:lead_{k}d", v) for k, v in sorted(result.forecast_rain_events.items())]
    if rain_blocks:
        out += [f"## Rain / no-rain skill (threshold {context['rain_threshold_mm']} mm)", "",
                "| Scope | Days | Hits | Misses | False alarms | POD | FAR | CSI | Accuracy |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for scope, m in rain_blocks:
            out.append(f"| {scope} | {m['n']} | {m['hits']} | {m['misses']} | {m['false_alarms']} | "
                       f"{_f(m['pod'])} | {_f(m['far'])} | {_f(m['csi'])} | {_f(m['accuracy'])} |")
        out.append("")
    if result.notes:
        out += ["## Notes", ""] + [f"- {n}" for n in result.notes] + [""]
    return "\n".join(out)


def svg_scatter(model, station, title, unit, size=240) -> str:
    """Tiny dependency-free scatter plot (model vs station) with a 1:1 line."""
    pts = [(float(s), float(m)) for m, s in zip(model, station) if pd.notna(m) and pd.notna(s)]
    if not pts:
        return ""
    lo = min(min(p) for p in pts)
    hi = max(max(p) for p in pts)
    if hi - lo < 1e-9:
        hi = lo + 1.0
    pad = 34
    span = size - 2 * pad

    def sx(v):
        return pad + (v - lo) / (hi - lo) * span

    def sy(v):
        return size - pad - (v - lo) / (hi - lo) * span

    dots = "".join(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="2.6" fill="#2e7d32" fill-opacity="0.65"/>' for x, y in pts)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="{size}" height="{size}" role="img" '
        f'aria-label="{html.escape(title)}">'
        f'<rect x="{pad}" y="{pad}" width="{span}" height="{span}" fill="none" stroke="#bbb"/>'
        f'<line x1="{sx(lo):.1f}" y1="{sy(lo):.1f}" x2="{sx(hi):.1f}" y2="{sy(hi):.1f}" stroke="#c62828" stroke-dasharray="4 3"/>'
        f'{dots}'
        f'<text x="{size/2}" y="14" font-size="11" text-anchor="middle" fill="#222">{html.escape(title)}</text>'
        f'<text x="{size/2}" y="{size-6}" font-size="10" text-anchor="middle" fill="#555">station ({html.escape(unit)})</text>'
        f'<text x="10" y="{size/2}" font-size="10" text-anchor="middle" fill="#555" transform="rotate(-90 10 {size/2})">model ({html.escape(unit)})</text>'
        f'<text x="{pad}" y="{size-pad+12}" font-size="9" fill="#777">{lo:.1f}</text>'
        f'<text x="{size-pad}" y="{size-pad+12}" font-size="9" text-anchor="end" fill="#777">{hi:.1f}</text>'
        f'</svg>'
    )


def to_html(result, context) -> str:
    md_rows = summary_rows(result)
    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        f"<title>Weather validation - {html.escape(context['farm'])}</title>",
        "<style>body{font:14px/1.5 system-ui,sans-serif;max-width:980px;margin:2rem auto;padding:0 1rem;color:#1b1b1b}"
        "table{border-collapse:collapse;margin:.5rem 0 1.5rem;width:100%}th,td{border:1px solid #ddd;padding:4px 8px;text-align:right}"
        "th:first-child,td:first-child{text-align:left}th{background:#f3f6f3}.plots{display:flex;flex-wrap:wrap;gap:12px}"
        ".note{background:#fff8e1;border-left:4px solid #f9a825;padding:.5rem .8rem;margin:.4rem 0}</style></head><body>",
        f"<h1>Weather validation: {html.escape(context['farm'])}</h1>",
        f"<p>Station <b>{html.escape(context['station'])}</b> &middot; {context['valid_station_days']} usable station days "
        f"&middot; generated {html.escape(context['generated_at'])}</p>",
        "<p>Error = model &minus; station. A positive bias means the fetched weather reads higher than the station.</p>",
    ]
    for scope in _scope_order(md_rows):
        parts.append(f"<h2>{html.escape(scope)}</h2><table><tr><th>Variable</th><th>n</th><th>Bias</th><th>MAE</th>"
                     "<th>RMSE</th><th>r</th><th>Mean model</th><th>Mean station</th></tr>")
        for r in (x for x in md_rows if x["scope"] == scope):
            label, unit = VARIABLES.get(r["variable"], (r["variable"], ""))
            parts.append(f"<tr><td>{html.escape(label)} ({html.escape(unit)})</td><td>{r['n']}</td><td>{_f(r['bias'])}</td>"
                         f"<td>{_f(r['mae'])}</td><td>{_f(r['rmse'])}</td><td>{_f(r['r'])}</td>"
                         f"<td>{_f(r['mean_model'])}</td><td>{_f(r['mean_station'])}</td></tr>")
        parts.append("</table>")

    pa = result.pairs_actual
    if len(pa):
        for source, grp in pa.groupby("source"):
            parts.append(f"<h2>Model vs station scatter: actual / {html.escape(str(source))}</h2><div class='plots'>")
            for var in ("temp_max_c", "temp_min_c", "humidity_pct", "rainfall_mm", "solar_mj_m2", "et0_mm"):
                g = grp[grp["variable"] == var]
                label, unit = VARIABLES[var]
                parts.append(svg_scatter(g["model"], g["station"], label, unit))
            parts.append("</div>")

    rain_blocks = [(f"actual:{k}", v) for k, v in result.actual_rain_events.items()] + \
                  [(f"forecast:lead_{k}d", v) for k, v in sorted(result.forecast_rain_events.items())]
    if rain_blocks:
        parts.append(f"<h2>Rain / no-rain skill (&ge; {context['rain_threshold_mm']} mm)</h2><table><tr><th>Scope</th><th>Days</th>"
                     "<th>Hits</th><th>Misses</th><th>False alarms</th><th>POD</th><th>FAR</th><th>CSI</th><th>Accuracy</th></tr>")
        for scope, m in rain_blocks:
            parts.append(f"<tr><td>{html.escape(scope)}</td><td>{m['n']}</td><td>{m['hits']}</td><td>{m['misses']}</td>"
                         f"<td>{m['false_alarms']}</td><td>{_f(m['pod'])}</td><td>{_f(m['far'])}</td><td>{_f(m['csi'])}</td>"
                         f"<td>{_f(m['accuracy'])}</td></tr>")
        parts.append("</table>")
    for n in result.notes:
        parts.append(f"<div class='note'>{html.escape(n)}</div>")
    parts.append("</body></html>")
    return "".join(parts)


def write_reports(result, daily: pd.DataFrame, context: dict, out_dir, formats=("csv", "json", "md", "html")) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []

    def put(name, text):
        p = out / name
        p.write_text(text, encoding="utf-8")
        written.append(p)

    if "csv" in formats:
        pd.DataFrame(summary_rows(result)).to_csv(out / "summary.csv", index=False)
        written.append(out / "summary.csv")
        pairs = pd.concat([
            result.pairs_actual.assign(scope="actual"),
            result.pairs_forecast.assign(scope="forecast"),
        ], ignore_index=True)
        pairs.to_csv(out / "daily_pairs.csv", index=False)
        written.append(out / "daily_pairs.csv")
        daily.to_csv(out / "station_daily.csv")
        written.append(out / "station_daily.csv")
    if "json" in formats:
        put("report.json", json.dumps({"context": context, **result.to_dict()}, indent=2, default=str))
    if "md" in formats:
        put("report.md", to_markdown(result, context))
    if "html" in formats:
        put("report.html", to_html(result, context))
    return written
