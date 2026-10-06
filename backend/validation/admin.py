from django.contrib import admin

from .models import ForecastSnapshot, StationReading, WeatherStation


@admin.register(WeatherStation)
class WeatherStationAdmin(admin.ModelAdmin):
    list_display = ("name", "farm", "timezone", "wind_height_m", "elevation_m")
    search_fields = ("name", "farm__farm_name")


@admin.register(StationReading)
class StationReadingAdmin(admin.ModelAdmin):
    list_display = ("station", "timestamp", "temp_c", "humidity_pct", "rain_mm", "wind_ms", "solar_wm2")
    list_filter = ("station",)
    date_hierarchy = "timestamp"


@admin.register(ForecastSnapshot)
class ForecastSnapshotAdmin(admin.ModelAdmin):
    list_display = ("farm", "target_date", "lead_days", "temp_max_c", "rainfall_mm", "issued_at")
    list_filter = ("lead_days", "farm")
