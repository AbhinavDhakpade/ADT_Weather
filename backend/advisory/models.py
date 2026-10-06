from django.db import models
from django.conf import settings

class Disease(models.Model):
    """Pest / disease reference data, seeded from table_weather___pest_disease.xlsx"""

    TYPE_CHOICES = [
        ("fungal", "Fungal"),
        ("bacterial", "Bacterial"),
        ("viral", "Viral"),
        ("phytoplasma", "Phytoplasma"),
        ("pest", "Pest"),
    ]

    sr_no = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=120)
    organism = models.CharField(max_length=150)
    crop_stage = models.CharField(max_length=150)
    disease_type = models.CharField(max_length=20, choices=TYPE_CHOICES)

    irrigation_requirement_l = models.CharField(max_length=30, blank=True)
    actual_irrigation_given = models.CharField(max_length=30, blank=True)
    rainfall_mm_week = models.CharField(max_length=30)
    vapour_pressure_kpa = models.CharField(max_length=30)
    vpd_kpa = models.CharField(max_length=30)
    relative_humidity_pct = models.CharField(max_length=30)
    avg_temp_c = models.CharField(max_length=30)
    leaf_wetness_hrs = models.CharField(max_length=30)
    gdd_range = models.CharField(max_length=30)

    # Risk score is the deterministic / ML-derived "current" risk percentage shown on the dashboard
    risk_score = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sr_no"]

    def __str__(self):
        return self.name

    @property
    def risk_label(self):
        if self.risk_score >= 70:
            return "Very High"
        if self.risk_score >= 50:
            return "High"
        if self.risk_score >= 30:
            return "Moderate"
        return "Low"


class Treatment(models.Model):
    """Treatment protocol keyed by disease_type (shared across diseases of the same type)."""

    disease_type = models.CharField(max_length=20, unique=True, choices=Disease.TYPE_CHOICES)
    biological = models.TextField()
    chemical = models.TextField()
    timing = models.TextField()
    safety = models.TextField()
    recovery = models.TextField()

    def __str__(self):
        return f"Treatment: {self.disease_type}"


class IrrigationRule(models.Model):
    """Irrigation decision reference table across soil types / crop stages."""

    DECISION_CHOICES = [
        ("Very Low", "Very Low"),
        ("Low", "Low"),
        ("Medium", "Medium"),
        ("High", "High"),
    ]

    sr_no = models.PositiveIntegerField(unique=True)
    soil_type = models.CharField(max_length=60)
    crop_stage = models.CharField(max_length=60)
    moisture_pct = models.CharField(max_length=30)
    rainfall_mm_week = models.CharField(max_length=30)
    temp_c = models.CharField(max_length=30)
    relative_humidity_pct = models.CharField(max_length=30)
    vpd_kpa = models.CharField(max_length=30)
    etc_mm_day = models.CharField(max_length=30)
    requirement_l_plant = models.CharField(max_length=30)
    decision = models.CharField(max_length=20, choices=DECISION_CHOICES)
    remark = models.CharField(max_length=255)

    class Meta:
        ordering = ["sr_no"]

    def __str__(self):
        return f"{self.soil_type} - {self.crop_stage}"


class IrrigationRequirementLog(models.Model):
    """Continuously stored, computed irrigation requirement per farm per day.

    One row per farm per date, written on every weather sync from the
    deterministic irrigation rule (ETc = ET0 * Kc -> water required -> pump
    capacity -> irrigation time). All numeric fields (FloatField) so the values
    are machine-usable JSON, not display strings.
    """

    farm = models.ForeignKey(
        "FarmProfile", on_delete=models.CASCADE, related_name="irrigation_logs"
    )
    date = models.DateField(db_index=True)
    crop_stage = models.CharField(max_length=60)
    kc = models.FloatField()
    et0_mm_day = models.FloatField()
    etc_mm_day = models.FloatField()
    effective_rainfall_mm_day = models.FloatField(default=0.0)
    net_requirement_mm_day = models.FloatField()
    field_area_m2 = models.FloatField()
    water_required_l_day = models.FloatField()
    pump_hp = models.FloatField(null=True, blank=True)
    pump_discharge_l_s = models.FloatField()
    pump_capacity_l_hr = models.FloatField()
    irrigation_time_hr = models.FloatField()
    irrigation_time_label = models.CharField(max_length=30)
    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("farm", "date")
        ordering = ["-date"]

    def __str__(self):
        return f"{self.farm} @ {self.date}: {self.irrigation_time_label}"


class FarmProfile(models.Model):
    """A single farm's static profile data (one row per registered farm)."""

    SOIL_CHOICES = [
        ("Black Cotton", "Black Cotton"),
        ("Loamy", "Loamy"),
        ("Sandy", "Sandy"),
        ("Clay", "Clay"),
        ("Red Soil", "Red Soil"),
        ("Laterite", "Laterite"),
        ("Alluvial", "Alluvial"),
    ]
    IRRIGATION_CHOICES = [
        ("Drip", "Drip"),
        ("Sprinkler", "Sprinkler"),
        ("Flood", "Flood"),
        ("Furrow", "Furrow"),
        ("Rainfed", "Rainfed"),
    ]

    farm_name = models.CharField(max_length=120, default="Dhakpade Farm")
    farmer_name = models.CharField(max_length=120, default="Abhinav R. Dhakpade")
    phone = models.CharField(max_length=20, blank=True, default="")
    village = models.CharField(max_length=120, default="Baramati, Pune")
    latitude = models.FloatField(default=18.1514)
    longitude = models.FloatField(default=74.5815)
    # Elevation above sea level (m) — used by FAO-56 Penman-Monteith ET0 for
    # atmospheric pressure and clear-sky radiation. Baramati ~ 560 m.
    elevation_m = models.FloatField(default=560.0)

    # Crop identification — two separate fields:
    # crop_name = the common name of the crop grown (e.g. "Sugarcane")
    # variety   = the cultivar/variety code (e.g. "Co 86032")
    crop_name = models.CharField(max_length=80, default="Sugarcane")
    variety = models.CharField(max_length=60, default="Co 86032")

    planting_date = models.DateField()
    soil_type = models.CharField(max_length=60, choices=SOIL_CHOICES, default="Black Cotton")
    irrigation_method = models.CharField(max_length=60, choices=IRRIGATION_CHOICES, default="Drip")
    area_hectares = models.FloatField(default=2.4)

    # Farmer-supplied pump inputs — used by the deterministic irrigation rule
    # (pump HP is informational; the water-balance math uses discharge L/s).
    pump_hp = models.FloatField(default=5.0)
    pump_discharge_l_s = models.FloatField(default=5.0)
    base_temp_c = models.FloatField(default=18.0)
    expected_harvest = models.CharField(max_length=60, default="Dec 2025")
    expected_yield_t_ha = models.CharField(max_length=30, default="78–85")
    revenue_estimate = models.CharField(max_length=30, default="₹3.5–3.8 L")

    # Surveyed field boundary, imported from a per-farmer KML export (see the
    # import_kml_farmers management command). boundary_geojson is the outer
    # ring as [[lon, lat], ...] so the frontend Leaflet map can draw the exact
    # surveyed outline instead of just a centroid marker. boundary_source_file
    # is the original KML filename and doubles as the natural key the import
    # command re-matches on, so re-running the import updates rather than
    # duplicates these rows.
    boundary_geojson = models.JSONField(blank=True, null=True)
    boundary_source_file = models.CharField(max_length=255, blank=True, default="")
    # The login account that owns this farm. A farmer can own several farms;
    # farmers see only their own farms, and staff/admin accounts see all of them.
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="farms",
    )

    def __str__(self):
        return self.farm_name

    @property
    def area_m2(self) -> float:
        """Field area in square metres (1 hectare = 10,000 m2)."""
        return (self.area_hectares or 0.0) * 10000.0

    def current_crop_stage(self, gdd_cumulative: float | None = None) -> str:
        """Resolve the current growth stage from cumulative GDD.

        If gdd_cumulative is not passed, the latest ActualWeatherReading for this
        farm is used. Falls back to "Sprouting" when no data is available.
        """
        from .weather_service import crop_stage_for_gdd

        if gdd_cumulative is None:
            latest = self.actual_weather_readings.order_by("-date").first()
            gdd_cumulative = latest.gdd_cumulative if latest else 0.0
        return crop_stage_for_gdd(gdd_cumulative, list(self.growth_stages.all()))


class WeatherRecordBase(models.Model):
    """
    Fields shared by ActualWeatherReading and ForecastWeatherReading. Kept as
    an abstract base (no table of its own) purely to avoid repeating ~20
    field definitions twice — the two concrete models below are genuinely
    separate database tables, not a shared one with a flag.
    """

    date = models.DateField()
    temp_max_c = models.FloatField()
    temp_min_c = models.FloatField()
    humidity_pct = models.FloatField()
    rainfall_mm = models.FloatField()
    et0_mm = models.FloatField()
    vpd_kpa = models.FloatField()
    solar_mj_m2 = models.FloatField()
    wind_kmh = models.FloatField()
    gdd_daily = models.FloatField()
    gdd_cumulative = models.FloatField()
    weather_icon = models.CharField(max_length=10, default="⛅")

    # Extended fields — free in the same Open-Meteo daily payload
    # already being fetched, just previously unused. All nullable so seeded
    # sample data keeps working without a migration backfill.
    wind_direction_deg = models.FloatField(null=True, blank=True)
    wind_gusts_kmh = models.FloatField(null=True, blank=True)
    uv_index_max = models.FloatField(null=True, blank=True)
    precipitation_probability_pct = models.FloatField(null=True, blank=True)
    sunrise = models.TimeField(null=True, blank=True)
    sunset = models.TimeField(null=True, blank=True)
    soil_temp_0cm_c = models.FloatField(null=True, blank=True)
    weather_code = models.IntegerField(null=True, blank=True)
    condition_text = models.CharField(max_length=60, blank=True)
    fetched_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.farm} – {self.date}"

    @property
    def feels_like_c(self):
        """Simple heat-index style 'feels like' for the field-work-safety indicator."""
        if self.humidity_pct >= 40 and self.temp_max_c >= 27:
            return round(self.temp_max_c + (self.humidity_pct - 40) * 0.05, 1)
        return self.temp_max_c


class ActualWeatherReading(WeatherRecordBase):
    """
    The 'Actual Weather Database' — real, observed/reanalysis weather sourced
    from Open-Meteo (ERA5 archive, plus its recent-days window). One row per farm
    per past date. Never contains a
    forecast/predicted value; there is no flag to check, because a row's
    existence in this table *is* the guarantee.
    """

    farm = models.ForeignKey(FarmProfile, on_delete=models.CASCADE, related_name="actual_weather_readings")
    # "open_meteo_archive" (ERA5) | "open_meteo_recent" (past_days window) | "seed" (demo).
    # Rows stored before the Open-Meteo-only migration keep their original label.
    data_source = models.CharField(max_length=20, default="open_meteo_archive")

    class Meta:
        ordering = ["date"]
        unique_together = ("farm", "date")
        verbose_name = "Actual weather reading"

    @property
    def is_forecast(self):
        return False


class ForecastWeatherReading(WeatherRecordBase):
    """
    The 'Forecast Weather Database' — predicted weather sourced from
    Open-Meteo's forecast model. One row per farm per forecast date
    (today included). Fully replaced on every sync since forecasts shift as
    the upstream model updates. Carries a confidence score (decays with lead
    time — a 1-day-out forecast is more reliable than a 7-day-out one) and
    the name of the model that produced it, per the original spec.
    """

    farm = models.ForeignKey(FarmProfile, on_delete=models.CASCADE, related_name="forecast_weather_readings")
    data_source = models.CharField(max_length=20, default="open_meteo")  # "open_meteo" | "seed"
    confidence_score = models.FloatField(
        default=0.9,
        help_text="0-1 confidence, decaying with lead time from today (forecast skill degrades with horizon).",
    )
    prediction_model = models.CharField(max_length=80, default="Open-Meteo (ICON/GFS blend)")

    class Meta:
        ordering = ["date"]
        unique_together = ("farm", "date")
        verbose_name = "Forecast weather reading"

    @property
    def is_forecast(self):
        return True


class Alert(models.Model):
    SEVERITY_CHOICES = [
        ("critical", "Critical"),
        ("warning", "Warning"),
        ("info", "Info"),
        ("ok", "OK"),
    ]
    SOURCE_CHOICES = [
        ("manual", "Manual / Seeded"),
        ("weather_rule", "Auto-generated from weather forecast"),
    ]

    farm = models.ForeignKey(FarmProfile, on_delete=models.CASCADE, related_name="alerts")
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES)
    icon = models.CharField(max_length=10, default="🔔")
    title = models.CharField(max_length=200)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="manual")
    rule_key = models.CharField(max_length=80, blank=True)  # e.g. "heavy_rain_2026-07-02" — dedup key

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class AdvisoryTimelineItem(models.Model):
    DOT_CHOICES = [("done", "Done"), ("today", "Today"), ("upcoming", "Upcoming")]

    farm = models.ForeignKey(FarmProfile, on_delete=models.CASCADE, related_name="timeline_items")
    when_label = models.CharField(max_length=60)
    dot_state = models.CharField(max_length=10, choices=DOT_CHOICES)
    action = models.CharField(max_length=200)
    note = models.CharField(max_length=255)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order"]

    def __str__(self):
        return self.action


class SchedulerLog(models.Model):
    """
    One row per background weather-sync run — scheduled (hourly, via APScheduler),
    manual (the dashboard "Refresh" button / management command), or a startup
    catch-up run. Powers the Scheduler Monitoring panel on the dashboard and
    gives ops visibility into whether the automatic sync is actually healthy
    without needing to read server logs.
    """

    STATUS_CHOICES = [
        ("success", "Success"),
        ("partial", "Partial Success"),
        ("failure", "Failure"),
    ]
    TRIGGER_CHOICES = [
        ("scheduled", "Scheduled (hourly)"),
        ("manual", "Manual"),
        ("startup", "Startup catch-up"),
    ]
    API_STATUS_CHOICES = [("ok", "OK"), ("failed", "Failed")]

    task_name = models.CharField(max_length=80, default="sync_weather")
    trigger = models.CharField(max_length=20, choices=TRIGGER_CHOICES, default="scheduled")

    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.FloatField(null=True, blank=True)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="failure")
    farms_processed = models.PositiveIntegerField(default=0)

    records_fetched = models.PositiveIntegerField(default=0)
    records_updated = models.PositiveIntegerField(default=0)
    duplicates_removed = models.PositiveIntegerField(default=0)
    retry_attempts = models.PositiveIntegerField(default=0)

    # Both are Open-Meteo requests: history (archive + recent days) and forecast.
    history_status = models.CharField(max_length=10, choices=API_STATUS_CHOICES, default="ok")
    open_meteo_status = models.CharField(max_length=10, choices=API_STATUS_CHOICES, default="ok")  # forecast

    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.task_name} @ {self.started_at:%Y-%m-%d %H:%M} — {self.status}"


class CropGrowthStage(models.Model):
    """GDD thresholds defining sugarcane growth stages, used for the GDD meter."""

    farm = models.ForeignKey(FarmProfile, on_delete=models.CASCADE, related_name="growth_stages")
    stage_name = models.CharField(max_length=60)
    gdd_threshold = models.FloatField()
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order"]

    def __str__(self):
        return f"{self.stage_name} ({self.gdd_threshold})"
