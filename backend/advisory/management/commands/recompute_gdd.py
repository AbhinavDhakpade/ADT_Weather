"""
Management command: recompute_gdd

Repairs the running cumulative GDD (growing degree days) of stored weather.

Older versions of the weather sync added the same days to the total again on
every run, so gdd_cumulative kept growing. This walks each farm's stored days
in date order and rebuilds the running total from the daily GDD values:

  - Real readings (Open-Meteo) are re-chained: each day's total is
    the previous day's total plus that day's gdd_daily. Days before the farm's
    planting date add nothing (GDD is counted from planting), so run this
    again after you correct a farm's planting date.
  - Demo "seed" rows are left exactly as they are, and real readings after them
    continue from the seed total.
  - Forecast rows continue on from the last observed day.

Usage:
    python manage.py recompute_gdd --dry-run     # show what would change
    python manage.py recompute_gdd               # repair every farm
    python manage.py recompute_gdd --farm 2      # one farm only
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from advisory.models import ActualWeatherReading, FarmProfile, ForecastWeatherReading


def rebuild_farm(farm, dry_run=False):
    """Returns (rows_changed, rows_total) for one farm."""
    changed = total = 0
    running = 0.0

    with transaction.atomic():
        for row in ActualWeatherReading.objects.filter(farm=farm).order_by("date"):
            total += 1
            if row.data_source == "seed":
                running = row.gdd_cumulative
                continue
            if row.date >= farm.planting_date:
                running += row.gdd_daily
            new_value = round(running, 1)
            if row.gdd_cumulative != new_value:
                changed += 1
                if not dry_run:
                    row.gdd_cumulative = new_value
                    row.save(update_fields=["gdd_cumulative"])

        for row in ForecastWeatherReading.objects.filter(farm=farm).order_by("date"):
            total += 1
            if row.data_source == "seed":
                running = row.gdd_cumulative
                continue
            if row.date >= farm.planting_date:
                running += row.gdd_daily
            new_value = round(running, 1)
            if row.gdd_cumulative != new_value:
                changed += 1
                if not dry_run:
                    row.gdd_cumulative = new_value
                    row.save(update_fields=["gdd_cumulative"])

    return changed, total


class Command(BaseCommand):
    help = "Rebuild cumulative GDD from the stored daily GDD values (repairs inflated totals)."

    def add_arguments(self, parser):
        parser.add_argument("--farm", type=int, default=None, help="Only this farm id")
        parser.add_argument("--dry-run", action="store_true", help="Show changes without saving them")

    def handle(self, *args, **options):
        farms = FarmProfile.objects.all().order_by("id")
        if options["farm"]:
            farms = farms.filter(pk=options["farm"])
        if not farms.exists():
            self.stdout.write(self.style.WARNING("No farms found."))
            return

        grand_changed = 0
        for farm in farms:
            changed, total = rebuild_farm(farm, dry_run=options["dry_run"])
            grand_changed += changed
            line = f"  farm #{farm.id} {farm.farmer_name}: {changed} of {total} rows {'would change' if options['dry_run'] else 'fixed'}"
            self.stdout.write(self.style.SUCCESS(line) if changed else line)

        self.stdout.write(
            f"\nDone{' (dry run, nothing saved)' if options['dry_run'] else ''}: {grand_changed} row(s) "
            f"{'would be' if options['dry_run'] else 'were'} corrected."
        )
