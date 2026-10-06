import datetime
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from . import sync_service
from .models import ActualWeatherReading, FarmProfile, ForecastWeatherReading
from .weather_service import RawDailyWeather


def raw_days(end, count, tmax=32.0):
    days = [end - datetime.timedelta(days=i) for i in range(count - 1, -1, -1)]
    return [
        RawDailyWeather(date=d, temp_max_c=tmax, temp_min_c=20.0, humidity_pct=55.0,
                        rainfall_mm=0.0, solar_mj_m2=20.0, wind_kmh=10.0)
        for d in days
    ]


class CumulativeGddTests(TestCase):
    def setUp(self):
        self.farm = FarmProfile.objects.create(
            farm_name="F", farmer_name="X",
            planting_date=datetime.date.today() - datetime.timedelta(days=90),
            latitude=18.5, longitude=73.8,
        )
        self.end = datetime.date.today() - datetime.timedelta(days=1)

    def sync(self, history, forecast=()):
        with mock.patch.object(sync_service, "fetch_open_meteo_history", return_value=list(history)), \
             mock.patch.object(sync_service, "fetch_open_meteo_forecast", return_value=list(forecast)):
            sync_service.sync_farm(self.farm, history_days=len(history), forecast_days=7, generate_alerts=False)

    def newest(self):
        return ActualWeatherReading.objects.filter(farm=self.farm).order_by("-date").first()

    def test_repeating_the_same_sync_does_not_inflate_the_total(self):
        history = raw_days(self.end, 7)
        self.sync(history)
        first = self.newest().gdd_cumulative
        self.assertGreater(first, 0)
        for _ in range(3):
            self.sync(history)
            self.assertEqual(self.newest().gdd_cumulative, first)
        self.assertEqual(ActualWeatherReading.objects.filter(farm=self.farm).count(), 7)

    def test_a_new_day_adds_exactly_that_days_gdd(self):
        self.sync(raw_days(self.end, 7))
        before = self.newest().gdd_cumulative
        # Next day: the window slides forward by one day.
        self.sync(raw_days(self.end + datetime.timedelta(days=1), 7))
        newest = self.newest()
        self.assertEqual(newest.date, self.end + datetime.timedelta(days=1))
        self.assertAlmostEqual(newest.gdd_cumulative, before + newest.gdd_daily, places=1)

    def test_longer_backfill_then_normal_syncs_stay_consistent(self):
        self.sync(raw_days(self.end, 30))
        thirty = self.newest().gdd_cumulative
        self.sync(raw_days(self.end, 7))  # the regular 7-day sync afterwards
        self.assertEqual(self.newest().gdd_cumulative, thirty)

    def test_gdd_counts_only_from_the_planting_date(self):
        # Planted 2 days before the newest reading: only the last 3 days count.
        self.farm.planting_date = self.end - datetime.timedelta(days=2)
        self.farm.save()
        self.sync(raw_days(self.end, 7))
        rows = list(ActualWeatherReading.objects.filter(farm=self.farm).order_by("date"))
        before, after = rows[:-3], rows[-3:]
        self.assertTrue(all(r.gdd_cumulative == 0 for r in before))
        self.assertAlmostEqual(after[-1].gdd_cumulative, sum(r.gdd_daily for r in after), places=1)
        # Fixing the planting date and recomputing moves the total accordingly.
        self.farm.planting_date = self.end - datetime.timedelta(days=4)
        self.farm.save()
        call_command("recompute_gdd", stdout=StringIO())
        newest = self.newest()
        five = list(ActualWeatherReading.objects.filter(farm=self.farm).order_by("-date")[:5])
        self.assertAlmostEqual(newest.gdd_cumulative, sum(r.gdd_daily for r in five), places=1)

    def test_recompute_command_repairs_inflated_totals_and_skips_seed_rows(self):
        self.sync(raw_days(self.end, 5))
        good = self.newest().gdd_cumulative
        # Simulate the old bug: inflate the stored totals.
        ActualWeatherReading.objects.filter(farm=self.farm).update(gdd_cumulative=9999.0)
        out = StringIO()
        call_command("recompute_gdd", "--dry-run", stdout=out)
        self.assertEqual(self.newest().gdd_cumulative, 9999.0)  # dry run changes nothing
        call_command("recompute_gdd", stdout=out)
        self.assertEqual(self.newest().gdd_cumulative, good)

        demo = FarmProfile.objects.create(farm_name="Demo", farmer_name="Demo", planting_date=datetime.date.today())
        ActualWeatherReading.objects.create(
            farm=demo, date=self.end, temp_max_c=30, temp_min_c=20, humidity_pct=60, rainfall_mm=0,
            et0_mm=4, vpd_kpa=1, solar_mj_m2=18, wind_kmh=10, gdd_daily=12, gdd_cumulative=1500.0,
            data_source="seed",
        )
        call_command("recompute_gdd", stdout=out)
        self.assertEqual(ActualWeatherReading.objects.get(farm=demo).gdd_cumulative, 1500.0)
