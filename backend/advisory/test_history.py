import datetime

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from .models import ActualWeatherReading, FarmProfile


def add_readings(farm, days, last_date):
    """`days` consecutive daily readings ending on last_date."""
    for i in range(days):
        ActualWeatherReading.objects.create(
            farm=farm, date=last_date - datetime.timedelta(days=i),
            temp_max_c=30.0, temp_min_c=20.0, humidity_pct=60.0, rainfall_mm=float(i),
            et0_mm=4.0, vpd_kpa=1.2, solar_mj_m2=18.0, wind_kmh=10.0,
            gdd_daily=12.0, gdd_cumulative=100.0 + i,
        )


class HistoryListTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user_a = User.objects.create_user("farmer_a", password="pw12345!")
        cls.user_b = User.objects.create_user("farmer_b", password="pw12345!")
        cls.staff = User.objects.create_user("admin_user", password="pw12345!", is_staff=True)
        today = datetime.date.today()
        cls.farm_a = FarmProfile.objects.create(farm_name="A", farmer_name="Farmer A", planting_date=today, owner=cls.user_a)
        cls.farm_b = FarmProfile.objects.create(farm_name="B", farmer_name="Farmer B", planting_date=today, owner=cls.user_b)
        # Newest reading is 2 days old (e.g. after a missed sync); history counts back from it.
        cls.latest = today - datetime.timedelta(days=2)
        add_readings(cls.farm_a, 35, cls.latest)
        add_readings(cls.farm_b, 5, cls.latest)

    def get(self, query=""):
        return self.client.get(f"/api/history/{query}")

    def test_default_is_last_20_newest_first(self):
        self.client.force_authenticate(self.user_a)
        data = self.get().data
        self.assertEqual(data["range"], "last20")
        self.assertEqual(data["count"], 20)
        dates = [r["date"] for r in data["results"]]
        self.assertEqual(dates[0], self.latest.isoformat())
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_7_and_30_days_count_back_from_newest_reading(self):
        self.client.force_authenticate(self.user_a)
        d7 = self.get("?range=7d").data
        self.assertEqual(d7["count"], 7)
        self.assertEqual(d7["results"][-1]["date"], (self.latest - datetime.timedelta(days=6)).isoformat())
        self.assertEqual(self.get("?range=30d").data["count"], 30)

    def test_fewer_rows_than_the_range_is_fine(self):
        self.client.force_authenticate(self.user_b)
        self.assertEqual(self.get("?range=30d").data["count"], 5)

    def test_bad_range_is_400(self):
        self.client.force_authenticate(self.user_a)
        self.assertEqual(self.get("?range=forever").status_code, 400)

    def test_farmer_only_gets_own_farm(self):
        self.client.force_authenticate(self.user_b)
        data = self.get().data
        self.assertEqual(data["farm"]["id"], self.farm_b.id)
        self.assertEqual(data["count"], 5)
        self.assertEqual(self.get(f"?farm={self.farm_a.id}").status_code, 404)

    def test_anonymous_gets_401(self):
        self.assertEqual(self.get().status_code, 401)

    def test_staff_can_pick_any_farm(self):
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.get(f"?farm={self.farm_a.id}&range=30d").data["count"], 30)
        self.assertEqual(self.get(f"?farm={self.farm_b.id}").data["farm"]["farmer_name"], "Farmer B")
        self.assertEqual(self.get("?farm=99999").status_code, 404)

    def test_farm_with_no_readings_returns_empty_list(self):
        empty_user = get_user_model().objects.create_user("farmer_c", password="pw12345!")
        FarmProfile.objects.create(farm_name="C", farmer_name="Farmer C", planting_date=datetime.date.today(), owner=empty_user)
        self.client.force_authenticate(empty_user)
        for r in ("last20", "7d", "30d"):
            data = self.get(f"?range={r}").data
            self.assertEqual(data["count"], 0)
            self.assertEqual(data["results"], [])
