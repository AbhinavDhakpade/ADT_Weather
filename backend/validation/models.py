"""
Models for validating fetched weather against a physical weather station.

  WeatherStation   - one station, linked to the farm whose weather it validates.
  StationReading   - one raw reading at the station's native interval (UTC).
  ForecastSnapshot - the forecast AS ISSUED, one row per farm / target date /
                     lead time. advisory.ForecastWeatherReading is overwritten
                     on every sync, so without these snapshots a forecast can
                     never be compared with what really happened.
"""

from django.db import models


class WeatherStation(models.Model):
    name = models.CharField(max_length=120, unique=True)
    farm = models.ForeignKey(
        "advisory.FarmProfile", on_delete=models.CASCADE, related_name="weather_stations",
        help_text="The farm whose fetched weather this station is used to validate.",
    )
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    elevation_m = models.FloatField(null=True, blank=True)
    timezone = models.CharField(
        max_length=60, default="Asia/Kolkata",
        help_text="IANA timezone of the station's timestamps and of its calendar day.",
    )
    wind_height_m = models.FloatField(
        default=2.0, help_text="Anemometer height above ground (m). Used to convert wind to 2 m / 10 m.",
    )
    notes = models.TextField(blank=True)

    def __str__(self):
        return self.name


class StationReading(models.Model):
    """Raw station reading. Every measurement is nullable: stations differ in what they log."""

    station = models.ForeignKey(WeatherStation, on_delete=models.CASCADE, related_name="readings")
    timestamp = models.DateTimeField(db_index=True)  # stored UTC
    temp_c = models.FloatField(null=True, blank=True)
    humidity_pct = models.FloatField(null=True, blank=True)
    rain_mm = models.FloatField(null=True, blank=True, help_text="Rain that fell in this interval (mm).")
    wind_ms = models.FloatField(null=True, blank=True, help_text="Wind speed at the station's anemometer height (m/s).")
    solar_wm2 = models.FloatField(null=True, blank=True, help_text="Mean incoming shortwave radiation (W/m2).")

    class Meta:
        ordering = ["timestamp"]
        constraints = [
            models.UniqueConstraint(fields=["station", "timestamp"], name="uniq_station_timestamp"),
        ]

    def __str__(self):
        return f"{self.station} @ {self.timestamp:%Y-%m-%d %H:%M}"


class ForecastSnapshot(models.Model):
    """The forecast for `target_date`, as issued `lead_days` days earlier (first sync of that day)."""

    farm = models.ForeignKey("advisory.FarmProfile", on_delete=models.CASCADE, related_name="forecast_snapshots")
    target_date = models.DateField(db_index=True)
    lead_days = models.PositiveSmallIntegerField()
    issued_at = models.DateTimeField()
    source = models.CharField(max_length=30, default="open_meteo")

    temp_max_c = models.FloatField(null=True, blank=True)
    temp_min_c = models.FloatField(null=True, blank=True)
    humidity_pct = models.FloatField(null=True, blank=True)
    rainfall_mm = models.FloatField(null=True, blank=True)
    solar_mj_m2 = models.FloatField(null=True, blank=True)
    wind_kmh = models.FloatField(null=True, blank=True)
    et0_mm = models.FloatField(null=True, blank=True)
    precipitation_probability_pct = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["target_date", "lead_days"]
        constraints = [
            models.UniqueConstraint(fields=["farm", "target_date", "lead_days"], name="uniq_snapshot_farm_target_lead"),
        ]

    def __str__(self):
        return f"{self.farm} {self.target_date} (lead {self.lead_days}d)"
