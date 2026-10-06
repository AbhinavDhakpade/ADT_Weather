import datetime

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from .models import FarmProfile


class FarmAccessTests(APITestCase):
    """A farmer sees only their own farm; staff see all; anonymous see nothing."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user_a = User.objects.create_user("farmer_a", password="pw12345!")
        cls.user_b = User.objects.create_user("farmer_b", password="pw12345!")
        cls.staff = User.objects.create_user("admin_user", password="pw12345!", is_staff=True)

        today = datetime.date.today()
        cls.farm_a = FarmProfile.objects.create(
            farm_name="A Field", farmer_name="Farmer A", planting_date=today, owner=cls.user_a
        )
        cls.farm_b = FarmProfile.objects.create(
            farm_name="B Field", farmer_name="Farmer B", planting_date=today, owner=cls.user_b
        )

    def test_anonymous_gets_401_everywhere(self):
        for url in ["/api/farms/", "/api/alerts/", "/api/weather/actual/",
                    "/api/dashboard/", "/api/diseases/", "/api/treatments/"]:
            self.assertEqual(self.client.get(url).status_code, 401, url)

    def test_farmer_lists_only_own_farm(self):
        self.client.force_authenticate(self.user_a)
        resp = self.client.get("/api/farms/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["id"], self.farm_a.id)

    def test_farmer_cannot_open_another_farm(self):
        self.client.force_authenticate(self.user_a)
        b = self.farm_b.id
        for url in [f"/api/farms/{b}/", f"/api/dashboard/?farm={b}",
                    f"/api/alerts/?farm={b}", f"/api/weather/actual/?farm={b}",
                    f"/api/weather/forecast/?farm={b}", f"/api/diseases/?farm={b}"]:
            self.assertEqual(self.client.get(url).status_code, 404, url)

    def test_farmer_cannot_edit_another_farm(self):
        self.client.force_authenticate(self.user_a)
        resp = self.client.patch(f"/api/farms/{self.farm_b.id}/", {"phone": "1"}, format="json")
        self.assertEqual(resp.status_code, 404)

    def test_farmer_cannot_create_farm(self):
        self.client.force_authenticate(self.user_a)
        resp = self.client.post("/api/farms/", {"farm_name": "X"}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_farmer_blocked_from_admin_endpoints(self):
        self.client.force_authenticate(self.user_a)
        for url in ["/api/scheduler/status/", "/api/scheduler/logs/", "/api/farmer-details/"]:
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_staff_can_see_everything(self):
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get("/api/farms/").data["count"], 2)
        self.assertEqual(self.client.get(f"/api/farms/{self.farm_b.id}/").status_code, 200)
        self.assertEqual(self.client.get(f"/api/alerts/?farm={self.farm_b.id}").status_code, 200)
        
        
    def test_farmer_with_two_farms_sees_both_but_not_others(self):
        farm_a2 = FarmProfile.objects.create(
            farm_name="A Field 2", farmer_name="Farmer A",
            planting_date=datetime.date.today(), owner=self.user_a,
        )
        self.client.force_authenticate(self.user_a)
        self.assertEqual(self.client.get("/api/farms/").data["count"], 2)
        for fid in (self.farm_a.id, farm_a2.id):
            self.assertEqual(self.client.get(f"/api/farms/{fid}/").status_code, 200, fid)
            self.assertEqual(self.client.get(f"/api/alerts/?farm={fid}").status_code, 200, fid)
        self.assertEqual(self.client.get(f"/api/farms/{self.farm_b.id}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/alerts/?farm={self.farm_b.id}").status_code, 404)
        self.assertEqual(self.client.get("/api/alerts/?farm=abc").status_code, 404)
        
        
    def test_me_lists_all_own_farms(self):
        FarmProfile.objects.create(
            farm_name="A Field 2", farmer_name="Farmer A",
            planting_date=datetime.date.today(), owner=self.user_a,
        )
        self.client.force_authenticate(self.user_a)
        data = self.client.get("/api/auth/me/").data
        self.assertEqual(len(data["farms"]), 2)
        self.assertEqual(data["farm"]["id"], self.farm_a.id)
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get("/api/auth/me/").data["farms"], [])    