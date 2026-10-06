from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views
from rest_framework.authtoken.views import obtain_auth_token

router = DefaultRouter()
router.register(r"diseases", views.DiseaseViewSet, basename="disease")
router.register(r"treatments", views.TreatmentViewSet, basename="treatment")
router.register(r"irrigation-rules", views.IrrigationRuleViewSet, basename="irrigationrule")
router.register(
    r"irrigation-requirements",
    views.IrrigationRequirementLogViewSet,
    basename="irrigationrequirement",
)
router.register(r"farms", views.FarmProfileViewSet, basename="farm")
router.register(r"weather/actual", views.ActualWeatherReadingViewSet, basename="actualweatherreading")
router.register(r"weather/forecast", views.ForecastWeatherReadingViewSet, basename="forecastweatherreading")
router.register(r"alerts", views.AlertViewSet, basename="alert")
router.register(r"timeline", views.AdvisoryTimelineViewSet, basename="timelineitem")
router.register(r"growth-stages", views.CropGrowthStageViewSet, basename="growthstage")

urlpatterns = [
    path("dashboard/", views.dashboard_summary, name="dashboard-summary"),
    path("auth/login/", obtain_auth_token, name="auth-login"),
    path("auth/me/", views.me, name="auth-me"),
    path("history/", views.history_list, name="history"),
    path("history/export/", views.history_export, name="history-export"),
    path("weather/refresh/", views.refresh_weather_now, name="weather-refresh"),
    path("scheduler/status/", views.scheduler_status, name="scheduler-status"),
    path("scheduler/logs/", views.scheduler_logs, name="scheduler-logs"),
    path("scheduler/run-now/", views.scheduler_run_now, name="scheduler-run-now"),
    path("ml/status/", views.ml_status, name="ml-status"),
    path("farmer-details/", views.farmer_details, name="farmer-details"),
    path("farmers/add-manual/", views.add_farmer_manual, name="add-farmer-manual"),
    path("farmers/import-kml/", views.add_farmers_from_kml, name="add-farmers-kml"),
    path("irrigation-requirement/", views.irrigation_requirement, name="irrigation-requirement"),
    path("ml/irrigation/", views.irrigation_ml_predict, name="ml-irrigation-predict"),
    path("ml/yield/", views.yield_ml_predict, name="ml-yield-predict"),
    path("", include(router.urls)),
]