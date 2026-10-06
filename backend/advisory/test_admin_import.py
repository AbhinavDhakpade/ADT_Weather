from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from .models import FarmProfile
from .test_kml_import import make_kml

URL = "/admin/advisory/farmprofile/import-kml/"


def kml_upload(name, farmer, lon, lat):
    return SimpleUploadedFile(name, make_kml(farmer, lon, lat).getvalue(), content_type="application/vnd.google-earth.kml+xml")


class AdminKmlImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_superuser("boss", password="pw12345!")
        cls.staff_no_perms = User.objects.create_user("clerk", password="pw12345!", is_staff=True)
        cls.farmer = User.objects.create_user("plain", password="pw12345!")

    def test_anonymous_and_farmers_cannot_reach_the_page(self):
        self.assertEqual(self.client.get(URL).status_code, 302)  # sent to the admin login
        self.client.force_login(self.farmer)
        self.assertEqual(self.client.get(URL).status_code, 302)  # not staff
        self.client.force_login(self.staff_no_perms)
        self.assertEqual(self.client.get(URL).status_code, 403)  # staff, but no permission to add farms/users

    def test_admin_sees_form_and_changelist_button(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(URL), 'type="file"')
        self.assertContains(self.client.get("/admin/advisory/farmprofile/"), "Add farmer")

    def test_upload_creates_farmers_and_shows_one_time_credentials(self):
        self.client.force_login(self.admin)
        resp = self.client.post(URL, {"kml_files": [
            kml_upload("a.kml", "Ramesh Patil", 77.10, 19.10),
            kml_upload("b.kml", "Sita Jadhav", 77.30, 19.30),
        ]})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["counts"]["created"], 2)
        self.assertEqual(len(resp.context["credentials"]), 2)
        self.assertContains(resp, "agriaura-new-logins.csv")
        self.assertTrue(resp.context["csv_href"].startswith("data:text/csv"))
        self.assertEqual(FarmProfile.objects.count(), 2)

    def test_second_upload_says_already_present_and_shows_no_passwords(self):
        self.client.force_login(self.admin)
        self.client.post(URL, {"kml_files": [kml_upload("a.kml", "Ramesh Patil", 77.10, 19.10)]})
        resp = self.client.post(URL, {"kml_files": [kml_upload("a.kml", "Ramesh Patil", 77.10, 19.10)]})
        self.assertEqual(resp.context["counts"]["exists"], 1)
        self.assertEqual(resp.context["credentials"], [])
        self.assertContains(resp, "Already present")
        self.assertEqual(FarmProfile.objects.count(), 1)

    def test_bad_inputs_are_reported_not_crashed(self):
        self.client.force_login(self.admin)
        resp = self.client.post(URL, {"kml_files": [
            SimpleUploadedFile("notes.txt", b"hello"),
            SimpleUploadedFile("broken.kml", b"not xml at all"),
        ]})
        self.assertEqual(resp.context["counts"]["error"], 2)
        self.assertEqual(FarmProfile.objects.count(), 0)
        self.assertContains(self.client.post(URL, {}), "Please choose at least one")
