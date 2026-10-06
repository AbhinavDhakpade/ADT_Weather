"""
Management command: import_kml_farmers

Reads every .kml file in advisory/data/kml_farmers/ (one field boundary per
file, exported from Google Earth Pro) and, for each file, uses the shared
import function in advisory/kml_import.py, which decides one of four things:

  NEW FARMER  a farmer we have not seen: creates the farm AND a login
              (username + one-time password, printed at the end)
  NEW FARM    a known farmer with a field at a different place: creates the
              farm and links it to that farmer's existing login
  EXISTS      already present (same file name, or same farmer at the same
              place): nothing is changed
  ERROR       the file could not be read: nothing is written

Usage:
    python manage.py import_kml_farmers
    python manage.py import_kml_farmers --dir /path/to/other/kml/folder
    python manage.py import_kml_farmers --dry-run
"""

import glob
import os

from django.core.management.base import BaseCommand

from advisory.kml_import import import_kml

DEFAULT_KML_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "kml_farmers")

LABELS = {"created": "NEW FARMER", "added": "NEW FARM  ", "exists": "EXISTS    ", "error": "ERROR     "}


class Command(BaseCommand):
    help = "Import farmer field boundaries from KML files, creating a login for each new farmer."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dir",
            default=DEFAULT_KML_DIR,
            help="Folder containing .kml files (default: advisory/data/kml_farmers/)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would happen without writing anything to the database.",
        )

    def handle(self, *args, **options):
        kml_dir = os.path.abspath(options["dir"])
        dry_run = options["dry_run"]

        kml_files = sorted(glob.glob(os.path.join(kml_dir, "*.kml")))
        if not kml_files:
            self.stderr.write(self.style.ERROR(f"No .kml files found in {kml_dir}"))
            return

        self.stdout.write(f"Found {len(kml_files)} KML file(s) in {kml_dir}\n")

        counts = {"created": 0, "added": 0, "exists": 0, "error": 0}
        credentials = []

        for path in kml_files:
            filename = os.path.basename(path)
            result = import_kml(path, filename, dry_run=dry_run)
            counts[result.status] += 1

            line = f"  {LABELS[result.status]} {filename}: {result.message}"
            if result.status in ("created", "added"):
                self.stdout.write(self.style.SUCCESS(line))
            elif result.status == "exists":
                self.stdout.write(self.style.WARNING(line))
            else:
                self.stdout.write(self.style.ERROR(line))

            if result.password:
                credentials.append((result.farmer_name, result.username, result.password))

        self.stdout.write(
            f"\nDone{' (dry run, nothing written)' if dry_run else ''}: "
            f"{counts['created']} new farmer(s), {counts['added']} extra farm(s), "
            f"{counts['exists']} already present, {counts['error']} error(s)."
        )

        if credentials:
            self.stdout.write(f"\n{'Farmer':<34}{'Username':<14}Password")
            for name, username, password in credentials:
                self.stdout.write(f"{name:<34}{username:<14}{password}")
            self.stdout.write(
                self.style.WARNING("\nPasswords are shown only once. Copy them somewhere safe now.")
            )

        if not dry_run and (counts["created"] or counts["added"]):
            self.stdout.write(
                "Note: village/phone are blank and planting_date defaulted to today. These KML "
                "files only carry field boundaries, so edit those fields in /admin/."
            )