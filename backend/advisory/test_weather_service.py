"""
Tests for the Open-Meteo weather client (weather_service) and how sync_service uses it.

No network: requests.get is replaced by a fake that answers like Open-Meteo does, so
these tests check request construction, response normalisation, unit conversion,
missing-value handling and error paths.
"""

import datetime
from unittest import mock

import requests
from django.test import SimpleTestCase, TestCase

from . import sync_service, weather_service
from .models import ActualWeatherReading, FarmProfile, ForecastWeatherReading
from .weather_service import (
    ARCHIVE_LAG_DAYS,
    OPEN_METEO_ARCHIVE_URL,
    OPEN_METEO_URL,
    WIND_10M_TO_2M,
    RawDailyWeather,
    WeatherServiceError,
    fetch_open_meteo_forecast,
    fetch_open_meteo_history,
)


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status

    def json(self):
        if self._payload is ValueError:
            raise ValueError("not json")
        return self._payload


def history_payload(first, last, tmax=33.0, tmin=21.0, rh=60.0, wind=20.0, precip=1.5, solar=19.0, overrides=None):
    """An Open-Meteo-shaped response (daily + hourly) covering first..last inclusive."""
    days = [(first + datetime.timedelta(days=i)) for i in range((last - first).days + 1)]
    daily = {
        "time": [d.isoformat() for d in days],
        "temperature_2m_max": [tmax] * len(days),
        "temperature_2m_min": [tmin] * len(days),
        "precipitation_sum": [precip] * len(days),
        "shortwave_radiation_sum": [solar] * len(days),
    }
    hourly = {"time": [], "relative_humidity_2m": [], "wind_speed_10m": []}
    for d in days:
        for h in range(24):
            hourly["time"].append(f"{d.isoformat()}T{h:02d}:00")
            hourly["relative_humidity_2m"].append(rh)
            hourly["wind_speed_10m"].append(wind)
    payload = {"daily": daily, "hourly": hourly}
    for path, value in (overrides or {}).items():
        section, key, idx = path
        payload[section][key][idx] = value
    return payload


class Router:
    """Fake requests.get: archive URL answers its start..end, forecast URL answers past_days."""

    def __init__(self, **payload_kwargs):
        self.calls = []
        self.kwargs = payload_kwargs
        self.archive_status = 200
        self.forecast_status = 200

    def __call__(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {}), timeout))
        today = datetime.date.today()
        if url == OPEN_METEO_ARCHIVE_URL:
            if self.archive_status != 200:
                return FakeResponse({"error": True, "reason": "archive down"}, self.archive_status)
            first = datetime.date.fromisoformat(params["start_date"])
            last = datetime.date.fromisoformat(params["end_date"])
            return FakeResponse(history_payload(first, last, **self.kwargs))
        if url == OPEN_METEO_URL:
            if self.forecast_status != 200:
                return FakeResponse({"error": True, "reason": "forecast down"}, self.forecast_status)
            first = today - datetime.timedelta(days=params["past_days"])
            last = today + datetime.timedelta(days=params["forecast_days"] - 1)
            return FakeResponse(history_payload(first, last, **self.kwargs))
        raise AssertionError(f"unexpected URL requested: {url}")


def patched(router):
    return mock.patch.object(weather_service.requests, "get", side_effect=router)


class HistoryRoutingTests(SimpleTestCase):
    def test_seven_days_splits_between_archive_and_recent(self):
        router = Router()
        with patched(router):
            rows = fetch_open_meteo_history(18.5, 73.8, days=7)

        today = datetime.date.today()
        self.assertEqual([r.date for r in rows], [today - datetime.timedelta(days=i) for i in range(7, 0, -1)])
        self.assertEqual(rows[-1].date, today - datetime.timedelta(days=1))  # ends yesterday, never today
        archive_cut = today - datetime.timedelta(days=ARCHIVE_LAG_DAYS)
        for r in rows:
            expected = "open_meteo_archive" if r.date <= archive_cut else "open_meteo_recent"
            self.assertEqual(r.source, expected, r.date)

        urls = [c[0] for c in router.calls]
        self.assertEqual(sorted(urls), sorted([OPEN_METEO_ARCHIVE_URL, OPEN_METEO_URL]))
        recent_params = next(c[1] for c in router.calls if c[0] == OPEN_METEO_URL)
        self.assertEqual(recent_params["past_days"], ARCHIVE_LAG_DAYS - 1)  # gap days only

    def test_one_day_uses_only_the_recent_window(self):
        router = Router()
        with patched(router):
            rows = fetch_open_meteo_history(18.5, 73.8, days=1)
        self.assertEqual(len(router.calls), 1)
        self.assertEqual(router.calls[0][0], OPEN_METEO_URL)
        self.assertEqual(router.calls[0][1]["past_days"], 1)
        self.assertEqual([r.source for r in rows], ["open_meteo_recent"])

    def test_old_window_uses_only_the_archive(self):
        router = Router()
        # days=30 reaches far back, but the newest days still need the recent window
        with patched(router):
            rows = fetch_open_meteo_history(18.5, 73.8, days=30)
        archive_call = next(c for c in router.calls if c[0] == OPEN_METEO_ARCHIVE_URL)
        today = datetime.date.today()
        self.assertEqual(archive_call[1]["start_date"], (today - datetime.timedelta(days=30)).isoformat())
        self.assertEqual(archive_call[1]["end_date"], (today - datetime.timedelta(days=ARCHIVE_LAG_DAYS)).isoformat())
        self.assertEqual(len(rows), 30)

    def test_requests_use_only_open_meteo_hosts_and_a_timeout(self):
        router = Router()
        with patched(router):
            fetch_open_meteo_history(18.5, 73.8, days=7)
        for url, params, timeout in router.calls:
            self.assertIn("open-meteo.com", url)
            self.assertIsNotNone(timeout)
            self.assertEqual(params["wind_speed_unit"], "kmh")
            self.assertEqual(params["timezone"], "auto")


class HistoryNormalisationTests(SimpleTestCase):
    def test_units_and_derived_values(self):
        router = Router(tmax=33.0, tmin=21.0, rh=60.0, wind=20.0, precip=1.5, solar=19.0)
        with patched(router):
            rows = fetch_open_meteo_history(18.5, 73.8, days=2)
        r = rows[-1]
        self.assertEqual((r.temp_max_c, r.temp_min_c), (33.0, 21.0))
        self.assertEqual(r.humidity_pct, 60.0)         # mean of the hourly values
        self.assertEqual(r.rainfall_mm, 1.5)
        self.assertEqual(r.solar_mj_m2, 19.0)
        self.assertAlmostEqual(r.wind_kmh, round(20.0 * WIND_10M_TO_2M, 1))  # 10 m mean -> 2 m
        self.assertAlmostEqual(WIND_10M_TO_2M, 0.748, places=3)

    def test_missing_values_follow_the_documented_rules(self):
        today = datetime.date.today()
        first = today - datetime.timedelta(days=3)
        payload = history_payload(first, today - datetime.timedelta(days=1))
        payload["daily"]["temperature_2m_max"][0] = None          # unusable day -> skipped
        payload["daily"]["precipitation_sum"][1] = None           # -> 0 mm
        payload["daily"]["shortwave_radiation_sum"][1] = None     # -> default solar
        for i, t in enumerate(payload["hourly"]["time"]):
            if t.startswith((first + datetime.timedelta(days=1)).isoformat()):
                payload["hourly"]["relative_humidity_2m"][i] = None   # whole day missing -> default
                payload["hourly"]["wind_speed_10m"][i] = None

        def fake(url, params=None, timeout=None):
            return FakeResponse(payload)

        with mock.patch.object(weather_service.requests, "get", side_effect=fake):
            rows = fetch_open_meteo_history(18.5, 73.8, days=3)
        self.assertEqual(len(rows), 2)
        self.assertNotIn(first, [r.date for r in rows])
        day2 = next(r for r in rows if r.date == first + datetime.timedelta(days=1))
        self.assertEqual(day2.rainfall_mm, 0.0)
        self.assertEqual(day2.solar_mj_m2, weather_service.DEFAULT_SOLAR_MJ_M2)
        self.assertEqual(day2.humidity_pct, weather_service.DEFAULT_HUMIDITY_PCT)
        self.assertEqual(day2.wind_kmh, weather_service.DEFAULT_WIND_KMH)

    def test_negative_precipitation_is_clamped(self):
        with patched(Router(precip=-0.2)):
            rows = fetch_open_meteo_history(18.5, 73.8, days=1)
        self.assertEqual(rows[0].rainfall_mm, 0.0)


class ErrorHandlingTests(SimpleTestCase):
    def test_invalid_coordinates_fail_before_any_request(self):
        with mock.patch.object(weather_service.requests, "get") as get:
            for lat, lon in ((91, 0), (-91, 0), (0, 181), (0, -181), (None, 5), ("abc", 5)):
                with self.assertRaises(WeatherServiceError):
                    fetch_open_meteo_history(lat, lon)
                with self.assertRaises(WeatherServiceError):
                    fetch_open_meteo_forecast(lat, lon)
            get.assert_not_called()

    def test_http_error_reports_open_meteos_reason(self):
        def fake(url, params=None, timeout=None):
            return FakeResponse({"error": True, "reason": "Latitude must be in range of -90 to 90"}, 400)

        with mock.patch.object(weather_service.requests, "get", side_effect=fake):
            with self.assertRaisesRegex(WeatherServiceError, "Latitude must be in range"):
                fetch_open_meteo_forecast(18.5, 73.8)

    def test_network_failure_and_timeout_become_weather_service_errors(self):
        for exc in (requests.ConnectionError("down"), requests.Timeout("slow")):
            with mock.patch.object(weather_service.requests, "get", side_effect=exc):
                with self.assertRaises(WeatherServiceError):
                    fetch_open_meteo_history(18.5, 73.8)

    def test_non_json_and_wrong_shape_responses(self):
        with mock.patch.object(weather_service.requests, "get", return_value=FakeResponse(ValueError)):
            with self.assertRaisesRegex(WeatherServiceError, "invalid JSON"):
                fetch_open_meteo_forecast(18.5, 73.8)
        with mock.patch.object(weather_service.requests, "get", return_value=FakeResponse({"unexpected": 1})):
            with self.assertRaisesRegex(WeatherServiceError, "Unexpected Open-Meteo response"):
                fetch_open_meteo_history(18.5, 73.8)

    def test_one_failing_segment_still_returns_the_other(self):
        router = Router()
        router.archive_status = 500
        with patched(router):
            rows = fetch_open_meteo_history(18.5, 73.8, days=7)
        self.assertTrue(rows)
        self.assertTrue(all(r.source == "open_meteo_recent" for r in rows))

    def test_all_segments_failing_raises(self):
        router = Router()
        router.archive_status = router.forecast_status = 500
        with patched(router):
            with self.assertRaises(WeatherServiceError):
                fetch_open_meteo_history(18.5, 73.8, days=7)


class ForecastTests(SimpleTestCase):
    def test_forecast_rows_are_tagged_and_normalised(self):
        today = datetime.date.today()
        payload = {"daily": {
            "time": [today.isoformat()],
            "temperature_2m_max": [34.0], "temperature_2m_min": [22.0],
            "relative_humidity_2m_mean": [55.0], "precipitation_sum": [0.0],
            "precipitation_probability_max": [10], "shortwave_radiation_sum": [21.0],
            "wind_speed_10m_max": [14.0], "wind_gusts_10m_max": [25.0],
            "wind_direction_10m_dominant": [200], "uv_index_max": [9.0],
            "sunrise": [f"{today.isoformat()}T06:10"], "sunset": [f"{today.isoformat()}T18:40"],
            "weather_code": [1],
        }}
        with mock.patch.object(weather_service.requests, "get", return_value=FakeResponse(payload)):
            rows = fetch_open_meteo_forecast(18.5, 73.8, days=1)
        self.assertEqual(rows[0].source, "open_meteo")
        self.assertEqual(rows[0].wind_kmh, 14.0)  # forecast wind definition is unchanged
        self.assertEqual((rows[0].sunrise, rows[0].sunset), ("06:10", "18:40"))


class SyncIntegrationTests(TestCase):
    def setUp(self):
        self.farm = FarmProfile.objects.create(
            farm_name="F", farmer_name="Farmer", latitude=18.5, longitude=73.8,
            planting_date=datetime.date.today() - datetime.timedelta(days=60),
        )

    def raw(self, days_ago, source):
        return RawDailyWeather(
            date=datetime.date.today() - datetime.timedelta(days=days_ago), temp_max_c=32, temp_min_c=20,
            humidity_pct=55, rainfall_mm=0, solar_mj_m2=20, wind_kmh=10, source=source,
        )

    def test_history_rows_keep_the_source_they_came_from(self):
        history = [self.raw(6, "open_meteo_archive"), self.raw(1, "open_meteo_recent")]
        with mock.patch.object(sync_service, "fetch_open_meteo_history", return_value=history), \
             mock.patch.object(sync_service, "fetch_open_meteo_forecast", return_value=[]):
            sync_service.sync_farm(self.farm, generate_alerts=False)
        sources = dict(ActualWeatherReading.objects.filter(farm=self.farm).values_list("date", "data_source"))
        self.assertEqual(sorted(sources.values()), ["open_meteo_archive", "open_meteo_recent"])

    def test_recent_row_is_upgraded_when_the_archive_catches_up(self):
        with mock.patch.object(sync_service, "fetch_open_meteo_history", return_value=[self.raw(6, "open_meteo_recent")]), \
             mock.patch.object(sync_service, "fetch_open_meteo_forecast", return_value=[]):
            sync_service.sync_farm(self.farm, generate_alerts=False)
        with mock.patch.object(sync_service, "fetch_open_meteo_history", return_value=[self.raw(6, "open_meteo_archive")]), \
             mock.patch.object(sync_service, "fetch_open_meteo_forecast", return_value=[]):
            sync_service.sync_farm(self.farm, generate_alerts=False)
        self.assertEqual(ActualWeatherReading.objects.filter(farm=self.farm).count(), 1)
        self.assertEqual(ActualWeatherReading.objects.get(farm=self.farm).data_source, "open_meteo_archive")

    def test_history_failure_is_reported_and_forecast_still_syncs(self):
        forecast = [self.raw(0, "open_meteo")]
        with mock.patch.object(sync_service, "fetch_open_meteo_history", side_effect=WeatherServiceError("boom")), \
             mock.patch.object(sync_service, "fetch_open_meteo_forecast", return_value=forecast):
            stats = sync_service.sync_farm(self.farm, generate_alerts=False, max_retries=1)
        self.assertEqual(stats["history_status"], "failed")
        self.assertEqual(stats["open_meteo_status"], "ok")
        self.assertTrue(any("Open-Meteo history" in e for e in stats["errors"]))
        self.assertEqual(ForecastWeatherReading.objects.filter(farm=self.farm).count(), 1)

    def test_run_log_records_history_and_forecast_status(self):
        with mock.patch.object(sync_service, "fetch_open_meteo_history", return_value=[]), \
             mock.patch.object(sync_service, "fetch_open_meteo_forecast", return_value=[self.raw(0, "open_meteo")]):
            log = sync_service.run_weather_sync(trigger="manual", max_retries=1)
        self.assertEqual(log.history_status, "ok")
        self.assertEqual(log.open_meteo_status, "ok")


class ConfigurationTests(SimpleTestCase):
    def _constants(self, env):
        import json
        import os
        import subprocess
        import sys
        from pathlib import Path

        code = (
            "import json, advisory.weather_service as w;"
            "print(json.dumps([w.OPEN_METEO_URL, w.OPEN_METEO_ARCHIVE_URL, w.REQUEST_TIMEOUT]))"
        )
        full_env = {k: v for k, v in os.environ.items() if not k.startswith("OPEN_METEO_")}
        full_env.update(env)
        out = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=True, env=full_env,
            cwd=Path(__file__).resolve().parent.parent,
        ).stdout
        return json.loads(out)

    def test_defaults_are_the_public_open_meteo_endpoints(self):
        self.assertEqual(
            self._constants({}),
            ["https://api.open-meteo.com/v1/forecast", "https://archive-api.open-meteo.com/v1/archive", 15.0],
        )

    def test_empty_values_passed_through_docker_compose_mean_default(self):
        env = {"OPEN_METEO_FORECAST_URL": "", "OPEN_METEO_ARCHIVE_URL": "", "OPEN_METEO_TIMEOUT_SECONDS": ""}
        self.assertEqual(self._constants(env)[0], "https://api.open-meteo.com/v1/forecast")
        self.assertEqual(self._constants(env)[2], 15.0)

    def test_overrides_are_honoured(self):
        env = {"OPEN_METEO_FORECAST_URL": "http://om.local/v1/forecast", "OPEN_METEO_TIMEOUT_SECONDS": "5"}
        got = self._constants(env)
        self.assertEqual((got[0], got[2]), ("http://om.local/v1/forecast", 5.0))
