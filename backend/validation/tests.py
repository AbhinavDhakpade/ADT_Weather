import datetime
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from advisory import sync_service
from advisory.models import ActualWeatherReading, FarmProfile, ForecastWeatherReading
from advisory.weather_service import RawDailyWeather

from . import engine
from .models import ForecastSnapshot, StationReading, WeatherStation
from .snapshots import record_forecast_snapshots
from .station_import import StationFileError, detect_columns, parse_station_file

IST = "Asia/Kolkata"


def make_readings(days=3, start="2026-09-01", step_min=10, tz=IST, temp_fn=None, rain_per_day=None,
                  solar_wm2=200.0, rh=60.0, wind_ms=2.0):
    """Synthetic station log in UTC with exactly known daily statistics."""
    idx = pd.date_range(f"{start} 00:00", periods=int(days * 24 * 60 / step_min), freq=f"{step_min}min", tz=tz)
    n = len(idx)
    hours = idx.hour + idx.minute / 60.0
    temp = temp_fn(hours) if temp_fn else 25 + 5 * np.sin((hours - 9) / 24 * 2 * np.pi)
    rain = np.zeros(n)
    if rain_per_day:
        for d, mm in rain_per_day.items():
            day_idx = np.where(idx.date == pd.Timestamp(d).date())[0]
            rain[day_idx] = mm / len(day_idx)
    return pd.DataFrame({
        "timestamp": idx.tz_convert("UTC"), "temp_c": temp, "humidity_pct": rh, "rain_mm": rain,
        "wind_ms": wind_ms, "solar_wm2": solar_wm2,
    })


class UnitHelperTests(SimpleTestCase):
    def test_wind_height_factor(self):
        self.assertAlmostEqual(engine.wind_height_factor(2, 2), 1.0)
        self.assertAlmostEqual(engine.wind_height_factor(2, 10), 1.337, places=2)
        self.assertAlmostEqual(engine.wind_height_factor(10, 2), 0.748, places=2)  # FAO-56 Eq. 47 factor

    def test_continuous_metrics_known_bias(self):
        station = [10.0, 20.0, 30.0, 40.0]
        model = [12.0, 22.0, 32.0, 42.0]
        m = engine.continuous_metrics(model, station)
        self.assertEqual(m["n"], 4)
        self.assertAlmostEqual(m["bias"], 2.0)
        self.assertAlmostEqual(m["mae"], 2.0)
        self.assertAlmostEqual(m["rmse"], 2.0)
        self.assertAlmostEqual(m["r"], 1.0)

    def test_continuous_metrics_skips_missing_and_handles_empty(self):
        m = engine.continuous_metrics([1.0, None, 3.0], [1.0, 2.0, np.nan])
        self.assertEqual(m["n"], 1)
        self.assertEqual(engine.continuous_metrics([], [])["n"], 0)

    def test_rain_event_metrics(self):
        station = [0, 5, 0, 10, 0.2]
        model = [0, 0, 3, 8, 0]
        m = engine.rain_event_metrics(model, station, threshold_mm=1.0)
        self.assertEqual((m["hits"], m["misses"], m["false_alarms"], m["correct_negatives"]), (1, 1, 1, 2))
        self.assertAlmostEqual(m["pod"], 0.5)
        self.assertAlmostEqual(m["far"], 0.5)
        self.assertAlmostEqual(m["csi"], 1 / 3, places=3)


class StationDailyTests(SimpleTestCase):
    def test_daily_aggregation_is_exact(self):
        df = make_readings(days=3, rain_per_day={"2026-09-02": 12.0})
        daily = engine.station_daily(df, tz=IST, wind_height_m=2.0)
        self.assertEqual(len(daily), 3)
        d2 = daily.loc[pd.Timestamp("2026-09-02")]
        self.assertAlmostEqual(d2["rainfall_mm"], 12.0, places=6)
        self.assertAlmostEqual(daily.loc[pd.Timestamp("2026-09-01"), "rainfall_mm"], 0.0)
        self.assertAlmostEqual(d2["solar_mj_m2"], 200 * 0.0864, places=6)       # 17.28 MJ/m2
        self.assertAlmostEqual(d2["humidity_pct"], 60.0)
        self.assertAlmostEqual(d2["wind_mean_2m_kmh"], 2.0 * 3.6, places=6)     # anemometer at 2 m
        self.assertAlmostEqual(d2["wind_max_10m_kmh"], 2.0 * 3.6 * engine.wind_height_factor(2, 10), places=4)
        self.assertAlmostEqual(d2["temp_max_c"], 30.0, places=1)
        self.assertAlmostEqual(d2["temp_min_c"], 20.0, places=1)

    def test_days_follow_the_local_calendar_not_utc(self):
        # IST midnight is 18:30 UTC of the previous day; a UTC grouping would split every day in two.
        df = make_readings(days=2)
        daily = engine.station_daily(df, tz=IST)
        self.assertEqual([d.date().isoformat() for d in daily.index], ["2026-09-01", "2026-09-02"])

    def test_incomplete_days_are_masked(self):
        df = make_readings(days=3)
        local = df["timestamp"].dt.tz_convert(IST)
        keep = ~((local.dt.date == datetime.date(2026, 9, 2)) & (local.dt.hour >= 6))  # day 2 stops at 06:00
        daily = engine.station_daily(df[keep], tz=IST, min_coverage=0.8)
        self.assertTrue(pd.isna(daily.loc[pd.Timestamp("2026-09-02"), "temp_max_c"]))
        self.assertFalse(pd.isna(daily.loc[pd.Timestamp("2026-09-01"), "temp_max_c"]))

    def test_empty_input(self):
        self.assertEqual(len(engine.station_daily(pd.DataFrame())), 0)


class ParseStationFileTests(SimpleTestCase):
    def _write(self, text, suffix=".csv"):
        f = tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False, encoding="utf-8")
        f.write(text)
        f.close()
        self.addCleanup(lambda: Path(f.name).unlink(missing_ok=True))
        return f.name

    def test_detects_common_column_names(self):
        found = detect_columns(["Date", "Time", "Outdoor Temperature (C)", "Humidity (%)", "Rain (mm)",
                                "Rain Rate (mm/h)", "Wind Speed (km/h)", "Wind Gust", "Solar Radiation (W/m2)", "Dew Point"])
        self.assertEqual(found["time"], ["Date", "Time"])
        self.assertEqual(found["temp_c"], "Outdoor Temperature (C)")
        self.assertEqual(found["humidity_pct"], "Humidity (%)")
        self.assertEqual(found["rain_mm"], "Rain (mm)")          # not the rate column
        self.assertEqual(found["wind_ms"], "Wind Speed (km/h)")  # not the gust column
        self.assertEqual(found["solar_wm2"], "Solar Radiation (W/m2)")

    def test_units_cumulative_rain_and_qc(self):
        path = self._write(
            "Date,Time,Temp,Hum,Rain,Wind,Solar\n"
            "01/09/2026,00:00,77.0,55,10.0,18,0\n"      # 25 C, 18 km/h = 5 m/s
            "01/09/2026,01:00,78.8,101.5,10.5,36,100\n"  # 26 C, RH 101.5 -> clipped to 100
            "01/09/2026,02:00,500,50,0.4,18,100\n"       # temp 500F is impossible -> rejected; counter reset
        )
        p = parse_station_file(path, temp_unit="f", wind_unit="kmh", rain_mode="cumulative")
        df = p.readings
        self.assertEqual(len(df), 3)
        self.assertAlmostEqual(df.loc[0, "temp_c"], 25.0)
        self.assertAlmostEqual(df.loc[1, "wind_ms"], 10.0)
        self.assertEqual(df.loc[1, "humidity_pct"], 100.0)
        self.assertTrue(pd.isna(df.loc[2, "temp_c"]))
        self.assertEqual(p.report["qc_rejected_values"]["temp_c"], 1)
        self.assertTrue(pd.isna(df.loc[0, "rain_mm"]))
        self.assertAlmostEqual(df.loc[1, "rain_mm"], 0.5)
        self.assertAlmostEqual(df.loc[2, "rain_mm"], 0.4)       # counter reset: value after the reset
        # DD/MM/YYYY in IST -> UTC
        self.assertEqual(df.loc[0, "timestamp"].isoformat(), "2026-08-31T18:30:00+00:00")

    def test_solar_energy_units_become_mean_power(self):
        path = self._write("Timestamp,Solar\n2026-09-01 12:00,0.36\n2026-09-01 13:00,0.36\n")
        p = parse_station_file(path, columns={"time": "Timestamp"}, solar_unit="kwh")
        self.assertAlmostEqual(p.readings.loc[0, "solar_wm2"], 360.0)  # 0.36 kWh/m2 in 1 h = 360 W/m2

    def test_clear_errors(self):
        with self.assertRaises(StationFileError):
            parse_station_file("/no/such/file.csv")
        path = self._write("a,b\n1,2\n")
        with self.assertRaises(StationFileError):
            parse_station_file(path)  # no time column
        path = self._write("Timestamp,foo\n2026-09-01 00:00,1\n")
        with self.assertRaises(StationFileError):
            parse_station_file(path)  # no weather columns


class SnapshotTests(TestCase):
    def setUp(self):
        self.farm = FarmProfile.objects.create(
            farm_name="F", farmer_name="X", planting_date=datetime.date(2026, 1, 1), latitude=18.5, longitude=73.8)
        self.day0 = datetime.date(2026, 9, 10)

    def _forecast(self, first_day, n=4, source="open_meteo", tmax=30.0):
        ForecastWeatherReading.objects.filter(farm=self.farm).delete()
        for i in range(n):
            ForecastWeatherReading.objects.create(
                farm=self.farm, date=first_day + datetime.timedelta(days=i), temp_max_c=tmax + i, temp_min_c=20,
                humidity_pct=60, rainfall_mm=i, et0_mm=4, vpd_kpa=1, solar_mj_m2=18, wind_kmh=10,
                gdd_daily=5, gdd_cumulative=100, data_source=source)

    def test_lead_times_are_counted_from_the_first_forecast_day(self):
        self._forecast(self.day0)
        self.assertEqual(record_forecast_snapshots(self.farm, datetime.datetime.now(datetime.timezone.utc)), 4)
        got = {(s.target_date, s.lead_days) for s in ForecastSnapshot.objects.filter(farm=self.farm)}
        self.assertIn((self.day0, 0), got)
        self.assertIn((self.day0 + datetime.timedelta(days=3), 3), got)

    def test_first_issue_of_a_lead_wins_and_repeat_syncs_add_nothing(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        self._forecast(self.day0, tmax=30.0)
        record_forecast_snapshots(self.farm, now)
        self._forecast(self.day0, tmax=99.0)  # same day, newer sync with different numbers
        self.assertEqual(record_forecast_snapshots(self.farm, now), 0)
        self.assertEqual(ForecastSnapshot.objects.get(farm=self.farm, target_date=self.day0, lead_days=0).temp_max_c, 30.0)
        # next day: forecast window slides, new target dates / leads appear
        self._forecast(self.day0 + datetime.timedelta(days=1))
        self.assertGreater(record_forecast_snapshots(self.farm, now), 0)
        self.assertEqual(ForecastSnapshot.objects.filter(farm=self.farm, target_date=self.day0 + datetime.timedelta(days=1)).count(), 2)

    def test_seed_rows_are_not_snapshotted(self):
        self._forecast(self.day0, source="seed")
        self.assertEqual(record_forecast_snapshots(self.farm, datetime.datetime.now(datetime.timezone.utc)), 0)

    def test_sync_farm_records_snapshots(self):
        today = datetime.date.today()
        forecast = [RawDailyWeather(date=today + datetime.timedelta(days=i), temp_max_c=31, temp_min_c=21,
                                    humidity_pct=60, rainfall_mm=0, solar_mj_m2=20, wind_kmh=10) for i in range(3)]
        with mock.patch.object(sync_service, "fetch_open_meteo_history", return_value=[]), \
             mock.patch.object(sync_service, "fetch_open_meteo_forecast", return_value=forecast):
            sync_service.sync_farm(self.farm, generate_alerts=False)
            sync_service.sync_farm(self.farm, generate_alerts=False)  # second sync must not duplicate
        self.assertEqual(ForecastSnapshot.objects.filter(farm=self.farm).count(), 3)


class EndToEndTests(TestCase):
    """Known bias is planted in 'fetched' data; the pipeline must recover it."""

    def setUp(self):
        self.farm = FarmProfile.objects.create(
            farm_name="Test Farm", farmer_name="X", planting_date=datetime.date(2026, 1, 1),
            latitude=18.15, longitude=74.58, elevation_m=560)
        self.station = WeatherStation.objects.create(
            name="Test AWS", farm=self.farm, timezone=IST, wind_height_m=2.0, latitude=18.16, longitude=74.58, elevation_m=565)
        self.readings = make_readings(days=10, rain_per_day={"2026-09-03": 20.0, "2026-09-07": 6.0})
        StationReading.objects.bulk_create([
            StationReading(station=self.station, timestamp=r.timestamp.to_pydatetime(), temp_c=r.temp_c,
                           humidity_pct=r.humidity_pct, rain_mm=r.rain_mm, wind_ms=r.wind_ms, solar_wm2=r.solar_wm2)
            for r in self.readings.itertuples()
        ])
        daily = engine.station_daily(self.readings, tz=IST)
        for date, row in daily.iterrows():
            is_demo = date.date() == datetime.date(2026, 9, 5)  # a demo row must never be validated
            ActualWeatherReading.objects.create(
                farm=self.farm, date=date.date(), data_source="seed" if is_demo else "open_meteo_archive",
                temp_max_c=99.0 if is_demo else row["temp_max_c"] + 1.5,    # planted bias: +1.5 / -0.5
                temp_min_c=row["temp_min_c"] - 0.5,
                humidity_pct=row["humidity_pct"], rainfall_mm=row["rainfall_mm"],
                solar_mj_m2=row["solar_mj_m2"], wind_kmh=row["wind_mean_2m_kmh"],
                et0_mm=4.0, vpd_kpa=1.0, gdd_daily=5, gdd_cumulative=50)
        for lead in (0, 1):
            for date, row in daily.iterrows():
                ForecastSnapshot.objects.create(
                    farm=self.farm, target_date=date.date(), lead_days=lead, issued_at=datetime.datetime.now(datetime.timezone.utc),
                    temp_max_c=row["temp_max_c"] + 2.0 * (lead + 1), temp_min_c=row["temp_min_c"],
                    rainfall_mm=row["rainfall_mm"], humidity_pct=row["humidity_pct"])

    def test_planted_bias_is_recovered(self):
        from .service import validate_station
        res, daily, ctx = validate_station(self.station)
        self.assertEqual(ctx["valid_station_days"], 10)
        self.assertEqual(ctx["elevation_diff_m"], 5.0)
        self.assertGreater(ctx["station_to_farm_km"], 0.5)
        hist = res.actual["open_meteo_archive"]
        self.assertAlmostEqual(hist["temp_max_c"]["bias"], 1.5, places=2)
        self.assertAlmostEqual(hist["temp_min_c"]["bias"], -0.5, places=2)
        self.assertAlmostEqual(hist["rainfall_mm"]["bias"], 0.0, places=3)
        self.assertAlmostEqual(hist["wind_kmh"]["bias"], 0.0, places=3)
        self.assertEqual(res.actual_rain_events["open_meteo_archive"]["pod"], 1.0)
        self.assertEqual(res.actual_rain_events["open_meteo_archive"]["far"], 0.0)
        # skill by lead time shows the planted growth of error with lead
        self.assertAlmostEqual(res.forecast_by_lead[0]["temp_max_c"]["bias"], 2.0, places=2)
        self.assertAlmostEqual(res.forecast_by_lead[1]["temp_max_c"]["bias"], 4.0, places=2)
        # station ET0 exists and is physically plausible for 25 C / RH 60 / 17 MJ
        self.assertTrue(2.0 < daily["et0_mm"].dropna().mean() < 8.0)
        self.assertEqual(res.actual["open_meteo_archive"]["et0_mm"]["n"], 9)
        self.assertNotIn("seed", res.actual)
        self.assertTrue(any("seeded demo" in n for n in res.notes))

    def test_date_window_limits_the_comparison(self):
        from .service import validate_station
        res, _d, ctx = validate_station(self.station, start=datetime.date(2026, 9, 3), end=datetime.date(2026, 9, 5))
        self.assertEqual(ctx["valid_station_days"], 3)
        self.assertEqual(res.actual["open_meteo_archive"]["temp_max_c"]["n"], 2)  # the 5th is a seed row

    def test_command_writes_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = StringIO()
            call_command("validate_weather", "--station", "Test AWS", "--out-dir", tmp, stdout=out)
            folder = Path(tmp) / "Test_AWS"
            for name in ("summary.csv", "daily_pairs.csv", "station_daily.csv", "report.json", "report.md", "report.html"):
                self.assertTrue((folder / name).exists(), name)
            self.assertIn("actual:open_meteo_archive", (folder / "report.md").read_text())
            self.assertIn("<svg", (folder / "report.html").read_text())
            summary = pd.read_csv(folder / "summary.csv")
            self.assertIn("forecast:lead_1d", set(summary["scope"]))

    def test_import_command_roundtrip_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv = Path(tmp) / "log.csv"
            body = ["Date,Time,Temp (C),Humidity (%),Rain (mm),Wind Speed (m/s),Solar (W/m2)"]
            for i in range(6):
                body.append(f"15/09/2026,{i:02d}:00,2{i},60,0.1,2.0,100")
            csv.write_text("\n".join(body))
            for _ in range(2):  # twice: must not duplicate
                call_command("import_station_data", str(csv), "--station", "New AWS", "--farm", str(self.farm.id),
                             "--wind-height", "10", stdout=StringIO())
            st = WeatherStation.objects.get(name="New AWS")
            self.assertEqual(st.readings.count(), 6)
            self.assertEqual(st.wind_height_m, 10.0)
            call_command("import_station_data", str(csv), "--station", "New AWS", "--dry-run", stdout=StringIO())
            self.assertEqual(st.readings.count(), 6)


class ApiTests(TestCase):
    def setUp(self):
        self.farm = FarmProfile.objects.create(farm_name="F", farmer_name="X", planting_date=datetime.date(2026, 1, 1))
        self.station = WeatherStation.objects.create(name="S", farm=self.farm)
        User = get_user_model()
        self.admin = User.objects.create_user("admin1", password="x", is_staff=True)
        self.farmer = User.objects.create_user("farmer1", password="x")

    def test_only_admins_can_read(self):
        c = APIClient()
        self.assertIn(c.get("/api/validation/stations/").status_code, (401, 403))
        c.force_authenticate(self.farmer)
        self.assertEqual(c.get("/api/validation/stations/").status_code, 403)
        c.force_authenticate(self.admin)
        r = c.get("/api/validation/stations/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()[0]["name"], "S")

    def test_summary_validates_input(self):
        c = APIClient()
        c.force_authenticate(self.admin)
        self.assertEqual(c.get("/api/validation/summary/").status_code, 404)
        self.assertEqual(c.get(f"/api/validation/summary/?station={self.station.id}&days=abc").status_code, 400)
        r = c.get(f"/api/validation/summary/?station={self.station.id}&days=30")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["context"]["valid_station_days"], 0)
