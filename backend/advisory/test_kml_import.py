import io

from django.contrib.auth import authenticate, get_user_model
from django.test import TestCase

from .kml_import import import_kml
from .models import FarmProfile


def make_kml(name, lon, lat, size=0.0005):
    """A minimal one-polygon KML like the ones exported from Google Earth Pro."""
    ring = [(lon, lat), (lon + size, lat), (lon + size, lat + size), (lon, lat + size), (lon, lat)]
    coords = " ".join(f"{x},{y},0" for x, y in ring)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark>'
        f"<name>{name}</name><Polygon><outerBoundaryIs><LinearRing>"
        f"<coordinates>{coords}</coordinates></LinearRing></outerBoundaryIs></Polygon>"
        "</Placemark></Document></kml>"
    )
    return io.BytesIO(xml.encode("utf-8"))


class KmlImportTests(TestCase):
    def test_new_farmer_gets_farm_and_working_login(self):
        res = import_kml(make_kml("Ramesh Patil", 77.10, 19.10), "ramesh.kml")
        self.assertEqual(res.status, "created")
        self.assertTrue(res.username and res.password)
        farm = FarmProfile.objects.get(pk=res.farm_id)
        self.assertEqual(farm.farmer_name, "Ramesh Patil")
        self.assertEqual(farm.owner.username, res.username)
        self.assertIsNotNone(authenticate(username=res.username, password=res.password))
        self.assertFalse(farm.owner.is_staff)

    def test_same_file_name_is_already_present(self):
        import_kml(make_kml("Ramesh Patil", 77.10, 19.10), "ramesh.kml")
        res = import_kml(make_kml("Someone Else", 77.50, 19.50), "ramesh.kml")
        self.assertEqual(res.status, "exists")
        self.assertEqual(FarmProfile.objects.count(), 1)
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_renamed_copy_at_same_place_is_already_present(self):
        first = import_kml(make_kml("Ramesh Patil", 77.10, 19.10), "ramesh.kml")
        res = import_kml(make_kml("ramesh patil", 77.10001, 19.10001), "ramesh_copy.kml")
        self.assertEqual(res.status, "exists")
        self.assertEqual(res.farm_id, first.farm_id)
        self.assertEqual(FarmProfile.objects.count(), 1)

    def test_same_farmer_at_new_place_gets_second_farm_same_login(self):
        first = import_kml(make_kml("Ramesh Patil", 77.10, 19.10), "ramesh1.kml")
        res = import_kml(make_kml("Ramesh Patil", 77.20, 19.20), "ramesh2.kml")
        self.assertEqual(res.status, "added")
        self.assertEqual(res.password, "")
        self.assertEqual(res.username, first.username)
        self.assertEqual(FarmProfile.objects.filter(owner__username=first.username).count(), 2)
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_bad_files_are_errors_and_write_nothing(self):
        self.assertEqual(import_kml(io.BytesIO(b"this is not xml"), "bad.kml").status, "error")
        no_poly = io.BytesIO(
            b'<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark>'
            b"<name>X</name></Placemark></Document></kml>"
        )
        self.assertEqual(import_kml(no_poly, "nopoly.kml").status, "error")
        self.assertEqual(FarmProfile.objects.count(), 0)

    def test_dry_run_writes_nothing(self):
        res = import_kml(make_kml("Ramesh Patil", 77.10, 19.10), "ramesh.kml", dry_run=True)
        self.assertEqual(res.status, "created")
        self.assertEqual(res.password, "")
        self.assertEqual(FarmProfile.objects.count(), 0)
        self.assertEqual(get_user_model().objects.count(), 0)

    def test_username_collision_gets_a_free_name(self):
        User = get_user_model()
        # Pre-create the username the next farm would get.
        next_id = (FarmProfile.objects.order_by("-id").values_list("id", flat=True).first() or 0) + 1
        User.objects.create_user(f"farmer{next_id}", password="x")
        res = import_kml(make_kml("Sita Jadhav", 77.30, 19.30), "sita.kml")
        self.assertEqual(res.status, "created")
        self.assertNotEqual(res.username, f"farmer{next_id}")
        self.assertTrue(User.objects.filter(username=res.username).exists())

    def test_entity_expansion_tricks_are_rejected(self):
        bomb = io.BytesIO(
            b'<?xml version="1.0"?><!DOCTYPE kml [<!ENTITY a "aaaaaaaaaa">]>'
            b'<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark>'
            b"<name>&a;</name></Placemark></Document></kml>"
        )
        res = import_kml(bomb, "bomb.kml")
        self.assertEqual(res.status, "error")
        self.assertIn("not allowed", res.message)
        self.assertEqual(FarmProfile.objects.count(), 0)

    def test_oversized_file_is_rejected(self):
        res = import_kml(io.BytesIO(b"<kml>" + b"x" * (5 * 1024 * 1024 + 10)), "huge.kml")
        self.assertEqual(res.status, "error")
        self.assertIn("5 MB", res.message)
