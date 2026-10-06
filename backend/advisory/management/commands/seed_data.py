"""
Management command: seed_data

Reads advisory/data/pest_disease.xlsx (the uploaded table_weather___pest_disease.xlsx)
and populates the Disease table from it. Also seeds IrrigationRule, Treatment,
FarmProfile, ActualWeatherReading + ForecastWeatherReading (history + 7-day
forecast, in their separate tables), Alert, AdvisoryTimelineItem and
CropGrowthStage records so the dashboard has a complete, realistic dataset
out of the box — mirroring the data that powered the original static HTML
prototype, but now served from the database via the REST API.

Usage:
    python manage.py seed_data
    python manage.py seed_data --reset   # wipe existing rows first
"""

import datetime
import os
import random
import re

from django.core.management.base import BaseCommand
from django.db import transaction

from advisory.models import (
    ActualWeatherReading,
    Alert,
    AdvisoryTimelineItem,
    CropGrowthStage,
    Disease,
    FarmProfile,
    ForecastWeatherReading,
    IrrigationRule,
    Treatment,
)

EXCEL_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "pest_disease.xlsx")

# Curated short display names + risk score + organism-driven type classification,
# matched 1:1 by Sr No to the rows in the uploaded Excel sheet.
DISEASE_META = {
    1: {"name": "Pineapple / Sett Rot", "type": "fungal", "risk": 72},
    2: {"name": "Early Shoot Borer", "type": "pest", "risk": 55},
    3: {"name": "White Grub", "type": "pest", "risk": 40},
    4: {"name": "Termites", "type": "pest", "risk": 28},
    5: {"name": "Thrips", "type": "pest", "risk": 35},
    6: {"name": "Brown Rust", "type": "fungal", "risk": 68},
    7: {"name": "Brown Spot / Cercospora", "type": "fungal", "risk": 62},
    8: {"name": "Eye Spot", "type": "fungal", "risk": 70},
    9: {"name": "Whiplash Smut", "type": "fungal", "risk": 45},
    10: {"name": "Pokkah Boeng", "type": "fungal", "risk": 82},
    11: {"name": "Red Stripe / Top Rot", "type": "bacterial", "risk": 55},
    12: {"name": "Leaf Scald", "type": "bacterial", "risk": 48},
    13: {"name": "Sugarcane Mosaic Virus", "type": "viral", "risk": 30},
    14: {"name": "Grassy Shoot Disease", "type": "phytoplasma", "risk": 38},
    15: {"name": "Root Borer", "type": "pest", "risk": 42},
    16: {"name": "Whitefly", "type": "pest", "risk": 33},
    17: {"name": "Black Aphid", "type": "pest", "risk": 29},
    18: {"name": "Top Shoot Borer", "type": "pest", "risk": 58},
    19: {"name": "Red Rot", "type": "fungal", "risk": 78},
    20: {"name": "Wilt Disease", "type": "fungal", "risk": 60},
    21: {"name": "Ratoon Stunting Disease", "type": "bacterial", "risk": 35},
    22: {"name": "Gumming Disease", "type": "bacterial", "risk": 52},
    23: {"name": "Yellow Leaf Disease", "type": "viral", "risk": 28},
    24: {"name": "Internode Borer", "type": "pest", "risk": 50},
    25: {"name": "Sugarcane Woolly Aphid", "type": "pest", "risk": 42},
    26: {"name": "Mealybug", "type": "pest", "risk": 36},
    27: {"name": "Pyrilla / Leaf Hopper", "type": "pest", "risk": 44},
    28: {"name": "Scale Insect", "type": "pest", "risk": 32},
    29: {"name": "Leaf Footed Bug", "type": "pest", "risk": 30},
    30: {"name": "Secondary Fungal Decay (Post-Harvest)", "type": "fungal", "risk": 65},
}

TREATMENTS = [
    dict(
        disease_type="fungal",
        biological="Trichoderma viride – 2.5 kg/ha; Pseudomonas fluorescens – 2.5 L/ha",
        chemical="Mancozeb 0.2%, Propiconazole 0.1%, Carbendazim 0.1%",
        timing="Apply at first symptom appearance and repeat after 10–14 days",
        safety="Wear gloves, mask, and protective clothing. Keep away from water bodies. Observe 7-day PHI.",
        recovery="4–6 weeks with proper management",
    ),
    dict(
        disease_type="bacterial",
        biological="Pseudomonas fluorescens – 2.5 L/ha; avoid wound transmission via tools",
        chemical="Copper oxychloride 0.3%; Streptomycin sulphate 200 ppm",
        timing="Apply during early infection stage; avoid spraying during peak sun",
        safety="Wear protective gear. Dispose of infected crop material by burning.",
        recovery="6–10 weeks; roguing infected plants recommended",
    ),
    dict(
        disease_type="pest",
        biological="NPV (Nuclear Polyhedrosis Virus) – 250 LE/ha; Trichogramma spp. egg parasitoids",
        chemical="Chlorpyrifos 0.05%, Lambda-cyhalothrin 0.5%, Imidacloprid 0.5 ml/L",
        timing="Apply at early instar stage; monitor pheromone traps weekly",
        safety="Wear protective clothing. Observe pollinator safety – avoid spraying during flowering.",
        recovery="2–4 weeks post treatment",
    ),
    dict(
        disease_type="viral",
        biological="Remove and destroy infected plants; control aphid vectors with Imidacloprid",
        chemical="No curative treatment. Use disease-free seed setts. Vector control is key.",
        timing="Preventive: apply insecticides at vector peaks in Jan–Feb",
        safety="Burn infected material. Disinfect cutting tools with bleach.",
        recovery="No recovery; rogue infected plants",
    ),
    dict(
        disease_type="phytoplasma",
        biological="Roguing infected plants; vector (leafhopper) control",
        chemical="Tetracycline group not practically effective for phytoplasma in sugarcane",
        timing="Remove infected plants immediately on detection",
        safety="Burn removed plants to prevent spread",
        recovery="Plant in new disease-free sets next season",
    ),
]

IRRIGATION_RULES = [
    dict(sr_no=1, soil_type="Sandy", crop_stage="Sprouting", moisture_pct="10–20", rainfall_mm_week="0–10",
         temp_c="30–40", relative_humidity_pct="40–60", vpd_kpa="1.5–2.5", etc_mm_day="6–8",
         requirement_l_plant="18–22", decision="High", remark="Immediate irrigation required"),
    dict(sr_no=2, soil_type="Sandy", crop_stage="Tillering", moisture_pct="20–30", rainfall_mm_week="10–25",
         temp_c="28–36", relative_humidity_pct="50–70", vpd_kpa="1.2–2.0", etc_mm_day="5–7",
         requirement_l_plant="22–28", decision="High", remark="Maintain moisture"),
    dict(sr_no=3, soil_type="Loamy", crop_stage="Sprouting", moisture_pct="20–35", rainfall_mm_week="10–30",
         temp_c="25–35", relative_humidity_pct="60–80", vpd_kpa="1.0–1.8", etc_mm_day="4–6",
         requirement_l_plant="12–18", decision="Medium", remark="Normal irrigation"),
    dict(sr_no=4, soil_type="Loamy", crop_stage="Grand Growth", moisture_pct="30–45", rainfall_mm_week="20–50",
         temp_c="25–34", relative_humidity_pct="65–85", vpd_kpa="0.8–1.5", etc_mm_day="4–5",
         requirement_l_plant="18–25", decision="Medium", remark="Adjust based on ETc"),
    dict(sr_no=5, soil_type="Clay", crop_stage="Sprouting", moisture_pct="30–50", rainfall_mm_week="20–60",
         temp_c="24–32", relative_humidity_pct="70–90", vpd_kpa="0.5–1.2", etc_mm_day="3–4",
         requirement_l_plant="8–12", decision="Low", remark="High water retention"),
    dict(sr_no=6, soil_type="Clay", crop_stage="Grand Growth", moisture_pct="40–60", rainfall_mm_week="40–80",
         temp_c="22–30", relative_humidity_pct="75–95", vpd_kpa="0.3–1.0", etc_mm_day="2–4",
         requirement_l_plant="10–18", decision="Low", remark="Avoid over-irrigation"),
    dict(sr_no=7, soil_type="Black Cotton", crop_stage="Vegetative", moisture_pct="35–55", rainfall_mm_week="25–70",
         temp_c="24–34", relative_humidity_pct="60–85", vpd_kpa="0.8–1.4", etc_mm_day="3–5",
         requirement_l_plant="12–18", decision="Low", remark="Crack formation if too dry"),
    dict(sr_no=8, soil_type="Red Soil", crop_stage="Vegetative", moisture_pct="20–35", rainfall_mm_week="10–30",
         temp_c="28–36", relative_humidity_pct="50–75", vpd_kpa="1.2–2.0", etc_mm_day="5–6",
         requirement_l_plant="16–22", decision="Medium", remark="Frequent light irrigation"),
    dict(sr_no=9, soil_type="Laterite", crop_stage="Any", moisture_pct="15–30", rainfall_mm_week="0–25",
         temp_c="28–38", relative_humidity_pct="45–70", vpd_kpa="1.5–2.5", etc_mm_day="5–7",
         requirement_l_plant="18–24", decision="High", remark="Low water holding capacity"),
    dict(sr_no=10, soil_type="Any Soil", crop_stage="Maturity", moisture_pct="40–60", rainfall_mm_week=">50",
         temp_c="22–30", relative_humidity_pct="70–95", vpd_kpa="0.2–0.8", etc_mm_day="2–3",
         requirement_l_plant="0–8", decision="Very Low", remark="Reduce irrigation before harvest"),
]

ALERTS = [
    dict(severity="critical", icon="🔴", title="Pokkah Boeng Risk – Very High",
         description="Humidity 82%, Leaf Wetness 16hrs – ideal for Fusarium. Apply protective fungicide after rain."),
    dict(severity="warning", icon="🌧️", title="Heavy Rain Expected Tomorrow",
         description="18mm forecast. Ensure drainage channels are clear. Skip irrigation for next 3 days."),
    dict(severity="critical", icon="🍂", title="Red Rot Monitor Required",
         description="GDD 3,200 enters high-risk window. Inspect stems weekly. Look for red discolouration inside."),
    dict(severity="info", icon="💧", title="Irrigation Not Required",
         description="Soil moisture adequate. 42mm rainfall this week meets crop water demand for black cotton soil."),
    dict(severity="ok", icon="✅", title="GDD Progress on Track",
         description="3,200 GDD accumulated. Grand Growth stage proceeding normally. Harvest on schedule Dec 2025."),
]

TIMELINE = [
    dict(when_label="Today", dot_state="today", action="🔍 Inspect field for Pokkah Boeng",
         note="Look for leaf twisting, stunting near growing point", sort_order=1),
    dict(when_label="Tomorrow", dot_state="upcoming", action="🚿 Check drainage channels",
         note="Heavy rain expected – prevent waterlogging", sort_order=2),
    dict(when_label="After Rainfall", dot_state="upcoming", action="🧪 Apply fungicide if RH stays >80%",
         note="Mancozeb 0.2% or Propiconazole 0.1%", sort_order=3),
    dict(when_label="In 7 Days", dot_state="upcoming", action="🔄 Re-inspect field",
         note="Confirm disease status, reassess irrigation", sort_order=4),
]

GROWTH_STAGES = [
    dict(stage_name="Sprouting", gdd_threshold=0, sort_order=1),
    dict(stage_name="Tillering", gdd_threshold=250, sort_order=2),
    dict(stage_name="Grand Growth", gdd_threshold=1500, sort_order=3),
    dict(stage_name="Maturity", gdd_threshold=3000, sort_order=4),
    dict(stage_name="Harvest Ready", gdd_threshold=5000, sort_order=5),
]

WEATHER_ICONS = ["⛅", "🌧️", "⛅", "🌦️", "☀️", "⛅", "🌧️"]


def parse_first_number(value):
    """'25–35' -> 25.0, '>6000' -> 6000.0, 'Dependent' -> 0.0"""
    if value is None:
        return 0.0
    nums = re.findall(r"\d+\.?\d*", str(value))
    return float(nums[0]) if nums else 0.0


class Command(BaseCommand):
    help = "Seed the AgriAura database from the pest/disease Excel file plus reference data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing rows for all advisory models before seeding.",
        )
        parser.add_argument(
            "--reference-only",
            action="store_true",
            help=(
                "Load ONLY the reference tables (diseases, treatments, irrigation rules) from the "
                "Excel file. Creates no farm, weather, alerts or timeline items, deletes nothing, "
                "and is safe to run on a production database at every deploy."
            ),
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Allow --reset when DEBUG is off. --reset deletes EVERY farm and all their weather data.",
        )
        parser.add_argument(
            "--weather-only",
            action="store_true",
            help=(
                "Regenerate ONLY the ActualWeatherReading/ForecastWeatherReading rows for "
                "the current date window. Used by the auto-refresh in dashboard_summary "
                "when today's date is missing from the DB. Does NOT touch diseases, "
                "irrigation rules, alerts, or farm profiles."
            ),
        )

    def handle(self, *args, **options):
        # --weather-only: quick regeneration of the date window, no full reset
        if options.get("weather_only"):
            farm = FarmProfile.objects.first()
            if farm:
                self.seed_weather(farm)
                self.stdout.write(self.style.SUCCESS("Weather readings refreshed for current date window."))
            return

        if options["reference_only"]:
            with transaction.atomic():
                self.seed_diseases()
                self.seed_treatments()
                self.seed_irrigation_rules()
            self.stdout.write(self.style.SUCCESS("Reference tables loaded (no farm, weather or alert data touched)."))
            return

        if options["reset"]:
            from django.conf import settings
            from django.core.management.base import CommandError

            if not settings.DEBUG and not options["force"]:
                raise CommandError(
                    "--reset deletes every farm and all weather data. DEBUG is off, so this looks like "
                    "a real deployment; re-run with --force if you really mean it."
                )
            self.stdout.write("Resetting existing advisory data...")
            ActualWeatherReading.objects.all().delete()
            ForecastWeatherReading.objects.all().delete()
            Alert.objects.all().delete()
            AdvisoryTimelineItem.objects.all().delete()
            CropGrowthStage.objects.all().delete()
            Disease.objects.all().delete()
            Treatment.objects.all().delete()
            IrrigationRule.objects.all().delete()
            FarmProfile.objects.all().delete()
            self._reset_primary_key_sequences()

        with transaction.atomic():
            farm = self.seed_farm()
            self.seed_diseases()
            self.seed_treatments()
            self.seed_irrigation_rules()
            self.seed_alerts(farm)
            self.seed_timeline(farm)
            self.seed_growth_stages(farm)
            self.seed_weather(farm)
            self.seed_irrigation_requirement(farm)

        self.stdout.write(self.style.SUCCESS("AgriAura database seeded successfully."))

    def seed_irrigation_requirement(self, farm):
        """Compute + store today's deterministic irrigation requirement so the
        API has data immediately, before the first live weather sync runs."""
        from advisory.sync_service import compute_and_store_irrigation

        log = compute_and_store_irrigation(farm)
        if log is not None:
            self.stdout.write(f"Irrigation requirement seeded -> {log.irrigation_time_label}")

    def _reset_primary_key_sequences(self):
        """
        After deleting all rows, reset auto-increment counters so a fresh seed
        always produces FarmProfile id=1, Disease ids 1-30, etc. Without this,
        repeated --reset runs keep incrementing SQLite's internal counter, so
        the farm id silently drifts away from 1 — breaking any client (or this
        project's own frontend) that assumes farm=1 is always valid.
        """
        from django.db import connection

        with connection.cursor() as cursor:
            for model in [
                FarmProfile, Disease, Treatment, IrrigationRule,
                Alert, AdvisoryTimelineItem, CropGrowthStage,
                ActualWeatherReading, ForecastWeatherReading,
            ]:
                table = model._meta.db_table
                if connection.vendor == "sqlite":
                    cursor.execute("DELETE FROM sqlite_sequence WHERE name = %s", [table])
                elif connection.vendor == "postgresql":
                    cursor.execute(f'ALTER SEQUENCE "{table}_id_seq" RESTART WITH 1')

    # ------------------------------------------------------------------
    def seed_farm(self):
        farm, created = FarmProfile.objects.update_or_create(
            farm_name="Dhakpade Farm",
            defaults=dict(
                farmer_name="Abhinav R. Dhakpade",
                village="Baramati, Pune",
                latitude=18.1514,
                longitude=74.5815,
                variety="Co 86032",
                planting_date=datetime.date(2024, 10, 15),
                soil_type="Black Cotton",
                irrigation_method="Drip",
                area_hectares=2.4,
                pump_hp=5.0,
                pump_discharge_l_s=5.0,
                base_temp_c=18.0,
                expected_harvest="Dec 2025",
                expected_yield_t_ha="78–85",
                revenue_estimate="₹3.5–3.8 L",
            ),
        )
        self.stdout.write(f"Farm profile: {'created' if created else 'updated'} -> {farm}")
        return farm

    def seed_diseases(self):
        if not os.path.exists(EXCEL_PATH):
            self.stdout.write(self.style.WARNING(f"Excel file not found at {EXCEL_PATH}, skipping disease import."))
            return

        import openpyxl

        wb = openpyxl.load_workbook(EXCEL_PATH, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(min_row=2, values_only=True))

        count = 0
        for row in rows:
            (
                sr_no, disease_observed, crop_stage, name_of_org,
                irrig_req, actual_irrig, rainfall, vap_press, vpd,
                rh, avg_temp, leaf_wetness, gdd,
            ) = row[:13]

            if sr_no is None:
                continue
            sr_no = int(sr_no)
            meta = DISEASE_META.get(sr_no, {})

            Disease.objects.update_or_create(
                sr_no=sr_no,
                defaults=dict(
                    name=meta.get("name", str(disease_observed)),
                    organism=str(name_of_org or ""),
                    crop_stage=str(crop_stage or ""),
                    disease_type=meta.get("type", "fungal"),
                    irrigation_requirement_l=str(irrig_req or ""),
                    actual_irrigation_given=str(actual_irrig or ""),
                    rainfall_mm_week=str(rainfall or ""),
                    vapour_pressure_kpa=str(vap_press or ""),
                    vpd_kpa=str(vpd or ""),
                    relative_humidity_pct=str(rh or ""),
                    avg_temp_c=str(avg_temp or ""),
                    leaf_wetness_hrs=str(leaf_wetness or ""),
                    gdd_range=str(gdd or ""),
                    risk_score=meta.get("risk", 40),
                ),
            )
            count += 1
        self.stdout.write(f"Diseases imported from Excel: {count}")

    def seed_treatments(self):
        for t in TREATMENTS:
            Treatment.objects.update_or_create(disease_type=t["disease_type"], defaults=t)
        self.stdout.write(f"Treatments seeded: {len(TREATMENTS)}")

    def seed_irrigation_rules(self):
        for r in IRRIGATION_RULES:
            IrrigationRule.objects.update_or_create(sr_no=r["sr_no"], defaults=r)
        self.stdout.write(f"Irrigation rules seeded: {len(IRRIGATION_RULES)}")

    def seed_alerts(self, farm):
        Alert.objects.filter(farm=farm).delete()
        for a in ALERTS:
            Alert.objects.create(farm=farm, **a)
        self.stdout.write(f"Alerts seeded: {len(ALERTS)}")

    def seed_timeline(self, farm):
        AdvisoryTimelineItem.objects.filter(farm=farm).delete()
        for t in TIMELINE:
            AdvisoryTimelineItem.objects.create(farm=farm, **t)
        self.stdout.write(f"Timeline items seeded: {len(TIMELINE)}")

    def seed_growth_stages(self, farm):
        CropGrowthStage.objects.filter(farm=farm).delete()
        for g in GROWTH_STAGES:
            CropGrowthStage.objects.create(farm=farm, **g)
        self.stdout.write(f"Growth stages seeded: {len(GROWTH_STAGES)}")

    def seed_weather(self, farm):
        ActualWeatherReading.objects.filter(farm=farm).delete()
        ForecastWeatherReading.objects.filter(farm=farm).delete()

        random.seed(42)
        today = datetime.date.today()

        # 7-day history ending today, cumulative GDD ramping up to 3,200 by "today"
        hi_temps = [28, 30, 29, 27, 29, 29, 31]
        lo_temps = [21, 22, 21, 20, 22, 21, 23]
        humidity = [80, 84, 82, 78, 82, 82, 86]
        rainfall = [8, 12, 6, 16, 0, 0, 18]
        et0 = [3.8, 4.0, 4.2, 3.6, 4.5, 4.2, 3.9]
        vpd = [0.5, 0.6, 0.6, 0.7, 0.6, 0.6, 0.5]
        solar = [16, 18, 17, 15, 19, 18, 14]
        wind = [12, 14, 11, 10, 13, 12, 16]
        gdd_daily = [10, 12, 11, 9, 11, 11, 13]

        base_temp = farm.base_temp_c
        cumulative = 3205.0 - sum(gdd_daily[1:])  # so the last day lands near 3205
        actual_records = []
        forecast_records = []
        for i in range(7):
            date = today - datetime.timedelta(days=6 - i)
            cumulative += gdd_daily[i]
            actual_records.append(
                ActualWeatherReading(
                    farm=farm,
                    date=date,
                    temp_max_c=hi_temps[i],
                    temp_min_c=lo_temps[i],
                    humidity_pct=humidity[i],
                    rainfall_mm=rainfall[i],
                    et0_mm=et0[i],
                    vpd_kpa=vpd[i],
                    solar_mj_m2=solar[i],
                    wind_kmh=wind[i],
                    gdd_daily=gdd_daily[i],
                    gdd_cumulative=round(cumulative, 1),
                    weather_icon=WEATHER_ICONS[i],
                    data_source="seed",
                )
            )

        # 7-day forecast continuing from the last cumulative GDD value
        fc_hi = [30, 31, 28, 29, 32, 30, 29]
        fc_lo = [22, 23, 21, 21, 24, 22, 22]
        fc_hum = [81, 79, 85, 83, 77, 80, 84]
        fc_rain = [0, 0, 14, 22, 0, 5, 9]
        fc_et0 = [4.1, 4.3, 3.5, 3.3, 4.6, 4.2, 3.9]
        fc_vpd = [0.6, 0.65, 0.5, 0.45, 0.7, 0.6, 0.55]
        fc_solar = [18, 19, 14, 13, 20, 18, 16]
        fc_wind = [13, 15, 10, 9, 16, 13, 12]
        fc_gdd_daily = [12, 13, 10, 11, 14, 12, 11]
        fc_icons = ["☀️", "☀️", "🌧️", "🌧️", "☀️", "⛅", "🌦️"]

        for i in range(7):
            date = today + datetime.timedelta(days=i + 1)
            cumulative += fc_gdd_daily[i]
            forecast_records.append(
                ForecastWeatherReading(
                    farm=farm,
                    date=date,
                    temp_max_c=fc_hi[i],
                    temp_min_c=fc_lo[i],
                    humidity_pct=fc_hum[i],
                    rainfall_mm=fc_rain[i],
                    et0_mm=fc_et0[i],
                    vpd_kpa=fc_vpd[i],
                    solar_mj_m2=fc_solar[i],
                    wind_kmh=fc_wind[i],
                    gdd_daily=fc_gdd_daily[i],
                    gdd_cumulative=round(cumulative, 1),
                    weather_icon=fc_icons[i],
                    data_source="seed",
                    confidence_score=round(max(0.55, 0.95 - 0.055 * (i + 1)), 2),
                    prediction_model="Open-Meteo (ICON/GFS blend)",
                )
            )

        # 30-day GDD history (older than the 7-day window) for the GDD trend chart
        hist_start_cumulative = actual_records[0].gdd_cumulative
        for i in range(30, 0, -1):
            date = today - datetime.timedelta(days=6 + i)
            value = max(0, hist_start_cumulative - i * 11 + random.uniform(-4, 4))
            actual_records.append(
                ActualWeatherReading(
                    farm=farm,
                    date=date,
                    temp_max_c=round(random.uniform(27, 32), 1),
                    temp_min_c=round(random.uniform(20, 23), 1),
                    humidity_pct=round(random.uniform(70, 90), 1),
                    rainfall_mm=round(random.uniform(0, 20), 1),
                    et0_mm=round(random.uniform(3.5, 4.5), 1),
                    vpd_kpa=round(random.uniform(0.4, 0.8), 2),
                    solar_mj_m2=round(random.uniform(14, 19), 1),
                    wind_kmh=round(random.uniform(8, 16), 1),
                    gdd_daily=round(random.uniform(9, 13), 1),
                    gdd_cumulative=round(value, 1),
                    weather_icon="⛅",
                    data_source="seed",
                )
            )

        ActualWeatherReading.objects.bulk_create(actual_records, ignore_conflicts=True)
        ForecastWeatherReading.objects.bulk_create(forecast_records, ignore_conflicts=True)
        self.stdout.write(
            f"Weather readings seeded: {len(actual_records)} actual, {len(forecast_records)} forecast"
        )
