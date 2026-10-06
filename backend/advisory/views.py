from datetime import timedelta

from dataclasses import asdict

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets, filters
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from django.http import Http404, HttpResponse
from rest_framework.exceptions import NotAuthenticated, PermissionDenied

from .ml.inference import models_available, predict_irrigation_requirement, predict_yield
from .models import (
    ActualWeatherReading,
    Alert,
    AdvisoryTimelineItem,
    CropGrowthStage,
    Disease,
    FarmProfile,
    ForecastWeatherReading,
    IrrigationRequirementLog,
    IrrigationRule,
    SchedulerLog,
    Treatment,
)
from .history import HISTORY_RANGES, csv_bytes, history_rows, xlsx_bytes
from .kml_import import ImportResult, import_kml_file, _free_username, _new_password
from .serializers import (
    ActualWeatherReadingSerializer,
    AlertSerializer,
    AdvisoryTimelineItemSerializer,
    CropGrowthStageSerializer,
    DiseaseListSerializer,
    DiseaseSerializer,
    FarmProfileSerializer,
    ForecastWeatherReadingSerializer,
    IrrigationRequirementLogSerializer,
    IrrigationRuleSerializer,
    SchedulerLogSerializer,
    TreatmentSerializer,
)
from .weather_service import compute_irrigation_requirement
from .sync_service import compute_and_store_irrigation

def allowed_farm_id(request):
    """
    The one place that decides which farm a request may see.

    - Not logged in            -> 401.
    - Staff/admin account      -> may pass ?farm=<id>, or omit it to see all farms.
    - Farmer account           -> always their own farm. Asking for a different
                                  farm returns 404, so other farms' existence
                                  isn't revealed either.
    """
    user = request.user
    if not user.is_authenticated:
        raise NotAuthenticated()

    requested = request.query_params.get("farm")
    if user.is_staff:
        return requested

    own_ids = [
        str(pk)
        for pk in FarmProfile.objects.filter(owner=user).order_by("id").values_list("id", flat=True)
    ]
    if not own_ids:
        raise Http404("No farm is linked to this account.")
    if not requested:
        return own_ids[0]          # no ?farm= given: their first farm
    if str(requested) not in own_ids:
        raise Http404("Farm not found.")
    return str(requested)

def _latest_weather_for_farm(farm):
    """Most recent actual (non-forecast) reading, used as ML inference context."""
    if farm is None:
        return None
    return ActualWeatherReading.objects.filter(farm=farm).order_by("-date").first()


def _serialize_weather(obj):
    """today_weather can come from either the Actual or Forecast table (e.g. when
    today's history row hasn't landed yet but Open-Meteo's forecast already
    covers today) — pick the matching serializer so extra forecast-only fields
    (confidence_score, prediction_model) only appear when they're real."""
    if obj is None:
        return None
    if isinstance(obj, ForecastWeatherReading):
        return ForecastWeatherReadingSerializer(obj).data
    return ActualWeatherReadingSerializer(obj).data


class DiseaseViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/diseases/            -> list (lightweight, incl. ML risk second-opinion)
    GET /api/diseases/{id}/       -> full detail incl. treatment protocol + ML prediction
    GET /api/diseases/?ordering=-risk_score
    GET /api/diseases/?disease_type=fungal
    GET /api/diseases/?search=red
    GET /api/diseases/?farm=1     -> include ML predictions using that farm's latest weather
    """

    queryset = Disease.objects.all()
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    ordering_fields = ["risk_score", "sr_no", "name"]
    search_fields = ["name", "organism", "crop_stage"]

    def get_serializer_class(self):
        if self.action == "list":
            return DiseaseListSerializer
        return DiseaseSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        farm_id = allowed_farm_id(self.request)
        farm = FarmProfile.objects.filter(pk=farm_id).first() if farm_id else FarmProfile.objects.first()
        context["current_weather"] = _latest_weather_for_farm(farm)
        return context

    def get_queryset(self):
        qs = super().get_queryset()
        disease_type = self.request.query_params.get("disease_type")
        if disease_type:
            qs = qs.filter(disease_type=disease_type)
        min_risk = self.request.query_params.get("min_risk")
        if min_risk:
            qs = qs.filter(risk_score__gte=int(min_risk))
        return qs


class TreatmentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Treatment.objects.all()
    serializer_class = TreatmentSerializer
    lookup_field = "disease_type"


class IrrigationRuleViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/irrigation-rules/
    GET /api/irrigation-rules/?soil_type=Black%20Cotton
    """

    queryset = IrrigationRule.objects.all()
    serializer_class = IrrigationRuleSerializer
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    search_fields = ["soil_type", "crop_stage", "remark"]

    def get_queryset(self):
        qs = super().get_queryset()
        soil_type = self.request.query_params.get("soil_type")
        if soil_type:
            qs = qs.filter(soil_type__iexact=soil_type)
        return qs


class IrrigationRequirementLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Continuously stored, computed irrigation requirements (single-Kc rule).
    GET /api/irrigation-requirements/            -> history (latest first)
    GET /api/irrigation-requirements/?farm=1     -> one farm's history
    GET /api/irrigation-requirements/?farm=1&latest=true -> only today's row
    """

    queryset = IrrigationRequirementLog.objects.all()
    serializer_class = IrrigationRequirementLogSerializer

    def get_queryset(self):
        qs = super().get_queryset().select_related("farm")
        farm_id = allowed_farm_id(self.request)
        if farm_id:
            qs = qs.filter(farm_id=farm_id)
        if self.request.query_params.get("latest") in ("true", "1"):
            qs = qs[:1]
        return qs


class FarmProfileViewSet(viewsets.ModelViewSet):
    """
    GET    /api/farms/        -> list all farms
    GET    /api/farms/<id>/   -> farm detail
    PATCH  /api/farms/<id>/   -> partial update (edit farm details)
    
    Full DELETE is intentionally disabled to prevent accidental data loss.
    POST is allowed to create new farms (for future multi-farm support).
    """
    queryset = FarmProfile.objects.all()
    serializer_class = FarmProfileSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]  # no PUT, no DELETE
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return FarmProfile.objects.all().order_by("id")
        return FarmProfile.objects.filter(owner=user).order_by("id")

    def create(self, request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied("Only admins can create farms.")
        return super().create(request, *args, **kwargs)

class ActualWeatherReadingViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/weather/actual/?farm=1&days=7

    Read-only access to the Actual Weather Database — observed/reanalysis
    readings from Open-Meteo (ERA5 + recent days). Never contains predicted values.
    """

    queryset = ActualWeatherReading.objects.all()
    serializer_class = ActualWeatherReadingSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        farm = allowed_farm_id(self.request)
        if farm:
            qs = qs.filter(farm_id=farm)
        days = self.request.query_params.get("days")
        if days:
            qs = qs.order_by("-date")[: int(days)]
            qs = sorted(qs, key=lambda r: r.date)
        return qs


class ForecastWeatherReadingViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/weather/forecast/?farm=1&days=7

    Read-only access to the Forecast Weather Database — predicted readings
    from Open-Meteo, including confidence_score and prediction_model.
    """

    queryset = ForecastWeatherReading.objects.all()
    serializer_class = ForecastWeatherReadingSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        farm = allowed_farm_id(self.request)
        if farm:
            qs = qs.filter(farm_id=farm)
        days = self.request.query_params.get("days")
        if days:
            qs = qs.order_by("date")[: int(days)]
        return qs


class AlertViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Alert.objects.filter(is_active=True)
    serializer_class = AlertSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        farm = allowed_farm_id(self.request)
        if farm:
            qs = qs.filter(farm_id=farm)
        return qs


class AdvisoryTimelineViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AdvisoryTimelineItem.objects.all()
    serializer_class = AdvisoryTimelineItemSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        farm = allowed_farm_id(self.request)
        if farm:
            qs = qs.filter(farm_id=farm)
        return qs


class CropGrowthStageViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CropGrowthStage.objects.all()
    serializer_class = CropGrowthStageSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        farm = allowed_farm_id(self.request)
        if farm:
            qs = qs.filter(farm_id=farm)
        return qs


@api_view(["GET"])
def dashboard_summary(request):
    """
    GET /api/dashboard/?farm=1

    Composite payload that powers the React dashboard home page in a single round trip:
    farm profile, today's weather, 7-day weather history, top disease risks (with ML
    second-opinion), active alerts, advisory timeline, irrigation snapshot (deterministic
    + ML second-opinion), ML yield prediction, and GDD progress.
    """
    farm_id = allowed_farm_id(request)
    farm = (
        get_object_or_404(FarmProfile, pk=farm_id)
        if farm_id
        else FarmProfile.objects.first()
    )
    if farm is None:
        return Response({"detail": "No farm profiles exist yet."}, status=404)

    import datetime as dt
    real_today = dt.date.today()

    # ── today_weather: ALWAYS the row matching the real current date ──────────
    # Prefer the Actual Weather Database (date == today) if that day's history
    # row has already landed; otherwise fall back to the Forecast Weather Database
    # (Open-Meteo gives today as its first forecast day), then finally to the
    # latest actual row so the dashboard never breaks.
    today = (
        ActualWeatherReading.objects.filter(farm=farm, date=real_today).first()
        or ForecastWeatherReading.objects.filter(farm=farm, date=real_today).first()
        or ActualWeatherReading.objects.filter(farm=farm).order_by("-date").first()
    )

    # ── Auto-refresh seeded data when today's date is not in DB at all ────────
    # This handles the common case where the app was seeded yesterday (or earlier)
    # and today's date is simply missing. We silently re-seed the weather window
    # so the dashboard never shows a stale "yesterday" as "Today."
    # Demo only (settings.DEMO_AUTOSEED): this REPLACES the farm's weather rows with synthetic
    # ones, so it must stay off wherever real or validated readings are stored.
    latest_actual = ActualWeatherReading.objects.filter(farm=farm).order_by("-date").first()
    latest_forecast = ForecastWeatherReading.objects.filter(farm=farm).order_by("-date").first()
    latest_dates = [r.date for r in (latest_actual, latest_forecast) if r is not None]
    if settings.DEMO_AUTOSEED and latest_dates and max(latest_dates) < real_today:
        # Today is not in the DB at all — regenerate the seed weather window
        try:
            from django.core.management import call_command
            from io import StringIO
            call_command("seed_data", "--weather-only", stdout=StringIO(), stderr=StringIO())
            # Re-fetch today after reseed
            today = (
                ActualWeatherReading.objects.filter(farm=farm, date=real_today).first()
                or ForecastWeatherReading.objects.filter(farm=farm, date=real_today).first()
            )
        except Exception:
            pass  # fail silently; dashboard still works with yesterday's data

    # ── 7-day history: the 7 most-recent rows from the Actual Weather Database,
    # oldest→newest ──────────────────────────────────────────────────────────
    history = list(
        ActualWeatherReading.objects.filter(farm=farm).order_by("-date")[:7]
    )
    history.reverse()

    # ── 7-day forecast: rows AFTER today from the Forecast Weather Database,
    # oldest→newest ───────────────────────────────────────────────────────────
    # Exclude today itself (already shown as today_weather) so the timeline
    # strip reads: Today | tomorrow | day+2 … without duplicating "today."
    forecast = list(
        ForecastWeatherReading.objects.filter(
            farm=farm, date__gt=real_today
        ).order_by("date")[:7]
    )
    # Edge case: if today is already in forecast (e.g. first run after seed when
    # Open-Meteo data not yet fetched), also exclude it from the forecast strip.
    forecast = [f for f in forecast if f.date != real_today]

    top_diseases = Disease.objects.order_by("-risk_score")[:9]
    mini_diseases = Disease.objects.order_by("-risk_score")[:4]
    disease_context = {"current_weather": today}

    alerts = Alert.objects.filter(farm=farm, is_active=True)[:5]
    timeline = AdvisoryTimelineItem.objects.filter(farm=farm)
    growth_stages = CropGrowthStage.objects.filter(farm=farm)

    current_gdd = today.gdd_cumulative if today else 0
    next_stage_threshold = None
    current_stage_name = "Sprouting"
    stages = list(growth_stages)
    for i, stage in enumerate(stages):
        if current_gdd >= stage.gdd_threshold:
            current_stage_name = stage.stage_name
        else:
            next_stage_threshold = stage.gdd_threshold
            break

    # Crude health score model: starts at 100, penalized by top disease risks + weather stress
    disease_penalty = sum(d.risk_score for d in top_diseases[:2]) * 0.12
    health_score = max(0, min(100, round(100 - disease_penalty)))

    irrigation_rule = IrrigationRule.objects.filter(
        soil_type__iexact=farm.soil_type
    ).first()

    # Deterministic irrigation requirement (single-Kc rule) from today's ET0 +
    # the farm's pump inputs. This is the number the farmer acts on.
    irrigation_requirement_calc = None
    if today is not None:
        irrigation_requirement_calc = compute_irrigation_requirement(
            et0_mm=today.et0_mm,
            crop_stage=current_stage_name,
            field_area_m2=farm.area_m2,
            pump_discharge_l_s=farm.pump_discharge_l_s,
            rainfall_week_mm=sum(h.rainfall_mm for h in history),
        )

    # ML second opinion: irrigation requirement, using today's weather + farm context
    irrigation_ml = None
    if today is not None:
        irrigation_ml = predict_irrigation_requirement(
            soil_type=farm.soil_type,
            crop_stage=current_stage_name,
            et0_mm=today.et0_mm,
            rainfall_week_mm=sum(h.rainfall_mm for h in history),
            temp_mean_c=(today.temp_max_c + today.temp_min_c) / 2,
            humidity_pct=today.humidity_pct,
            vpd_kpa=today.vpd_kpa,
        )

    # ML yield prediction, using current GDD progress, top disease risk, and a
    # rough irrigation-adequacy proxy from the water-balance check
    avg_disease_risk = (
        sum(d.risk_score for d in top_diseases) / len(top_diseases) if top_diseases else 0
    )
    irrigation_adequacy = 100.0
    if irrigation_rule and today is not None:
        # crude adequacy proxy: 100% if rainfall this week met ETc demand, scaled down otherwise
        etc_week = today.et0_mm * 7
        rainfall_week = sum(h.rainfall_mm for h in history)
        irrigation_adequacy = max(20.0, min(100.0, (rainfall_week / etc_week) * 100)) if etc_week else 80.0

    # Project GDD at harvest using current daily GDD rate (rough but directionally useful)
    avg_daily_gdd = (sum(h.gdd_daily for h in history) / len(history)) if history else 10.0
    days_to_harvest_estimate = 60  # rough remaining-season placeholder for the ML feature only
    projected_gdd_at_harvest = current_gdd + avg_daily_gdd * days_to_harvest_estimate

    yield_ml = predict_yield(
        gdd_at_harvest=projected_gdd_at_harvest,
        avg_disease_risk_pct=avg_disease_risk,
        irrigation_adequacy_pct=irrigation_adequacy,
        soil_type=farm.soil_type,
    )

    payload = {
        "farm": FarmProfileSerializer(farm).data,
        "today_weather": _serialize_weather(today),
        "weather_history": ActualWeatherReadingSerializer(history, many=True).data,
        "weather_forecast": ForecastWeatherReadingSerializer(forecast, many=True).data,
        "top_diseases": DiseaseListSerializer(top_diseases, many=True, context=disease_context).data,
        "mini_diseases": DiseaseListSerializer(mini_diseases, many=True, context=disease_context).data,
        "alerts": AlertSerializer(alerts, many=True).data,
        "timeline": AdvisoryTimelineItemSerializer(timeline, many=True).data,
        "growth_stages": CropGrowthStageSerializer(growth_stages, many=True).data,
        "health_score": health_score,
        "current_gdd": current_gdd,
        "current_stage": current_stage_name,
        "next_stage_threshold": next_stage_threshold,
        "irrigation_snapshot": (
            IrrigationRuleSerializer(irrigation_rule).data if irrigation_rule else None
        ),
        "irrigation_requirement": irrigation_requirement_calc,
        "irrigation_ml_prediction": irrigation_ml,
        "yield_ml_prediction": yield_ml,
        "ml_models_available": models_available(),
    }
    return Response(payload)


@api_view(["GET", "POST"])
@permission_classes([IsAdminUser])
def farmer_details(request):
    """
    Store / retrieve a farmer's details (identity + the image's Farmer Inputs:
    pump HP, pump discharge L/s, field area, irrigation method) in the backend.

        GET  /api/farmer-details/            -> list all stored farmer profiles
        GET  /api/farmer-details/?farm=1     -> one farmer profile
        POST /api/farmer-details/            -> create a new farmer profile
        POST /api/farmer-details/  {"id": 1, ...} -> update an existing one

    On write, an irrigation requirement is (re)computed and stored immediately so
    the new pump inputs take effect without waiting for the next weather sync.
    """
    if request.method == "GET":
        farm_id = request.query_params.get("farm")
        if farm_id:
            farm = get_object_or_404(FarmProfile, pk=farm_id)
            return Response(FarmProfileSerializer(farm).data)
        return Response(FarmProfileSerializer(FarmProfile.objects.all(), many=True).data)

    # POST: create or update
    data = request.data
    instance = None
    if data.get("id"):
        instance = get_object_or_404(FarmProfile, pk=data["id"])

    serializer = FarmProfileSerializer(instance, data=data, partial=instance is not None)
    serializer.is_valid(raise_exception=True)
    farm = serializer.save()

    # Recompute today's irrigation requirement with the new farmer inputs.
    try:
        compute_and_store_irrigation(farm)
    except Exception:
        pass  # no weather yet is fine; sync will fill it in

    return Response(FarmProfileSerializer(farm).data, status=201 if instance is None else 200)

@api_view(["POST"])
@permission_classes([IsAdminUser])
def add_farmer_manual(request):
    """
    POST /api/farmers/add-manual/   (admins only)

    Creates a farm from typed-in details AND a login for the farmer.
    The password is returned once in the response; it is stored hashed.
    """
    data = request.data.copy()

    name = str(data.get("farmer_name", "")).strip()
    if not name:
        return Response({"farmer_name": ["Farmer name is required."]}, status=400)
    data["farmer_name"] = name
    if not str(data.get("farm_name", "")).strip():
        data["farm_name"] = f"{name} Field"

    serializer = FarmProfileSerializer(data=data)
    serializer.is_valid(raise_exception=True)

    User = get_user_model()
    with transaction.atomic():
        farm = serializer.save()
        username = _free_username(User, farm.id)
        password = _new_password()
        user = User.objects.create_user(
            username=username, password=password, first_name=name[:150]
        )
        farm.owner = user
        farm.save(update_fields=["owner"])

    try:
        compute_and_store_irrigation(farm)
    except Exception:
        pass  # no weather yet is fine; the next sync fills it in

    return Response(
        {
            "farm": FarmProfileSerializer(farm).data,
            "login": {"username": username, "password": password},
        },
        status=201,
    )

@api_view(["POST"])
@permission_classes([IsAdminUser])
def add_farmers_from_kml(request):
    """
    POST /api/farmers/import-kml/   (admins only, multipart form)

    Field "kml_files" holds one or more .kml files. Each file is handled by the
    same import_kml() the Django admin page and the management command use, so
    the duplicate rules and login creation are identical everywhere.
    """
    files = request.FILES.getlist("kml_files")
    if not files:
        return Response({"detail": "Please choose at least one .kml file."}, status=400)
    if len(files) > 50:
        return Response({"detail": "Please upload at most 50 files at a time."}, status=400)

    results = []
    for upload in files:
        if not upload.name.lower().endswith(".kml"):
            results.append(ImportResult(upload.name, "error", "Not a .kml file."))
            continue
        results.extend(import_kml_file(upload, upload.name))

    counts = {"created": 0, "added": 0, "exists": 0, "error": 0}
    for r in results:
        counts[r.status] += 1

    return Response({"counts": counts, "results": [asdict(r) for r in results]})

@api_view(["GET"])
def irrigation_requirement(request):
    """
    Deterministic irrigation-requirement rule (single-Kc, FAO-56) as clean JSON.

    From a farm's live weather + pump inputs:
        GET /api/irrigation-requirement/?farm=1
        GET /api/irrigation-requirement/?farm=1&store=true   (also upsert today's log)

    Or fully ad-hoc (no farm needed), e.g. to reproduce the printed example:
        GET /api/irrigation-requirement/?et0_mm=5&crop_stage=Grand%20Growth
            &field_area_m2=4000&pump_discharge_l_s=5
    """
    farm_id = allowed_farm_id(request)

    if farm_id:
        farm = get_object_or_404(FarmProfile, pk=farm_id)
        if request.query_params.get("store") in ("true", "1"):
            log = compute_and_store_irrigation(farm)
            if log is None:
                return Response(
                    {"detail": "No weather data available for this farm yet."},
                    status=404,
                )
            return Response(IrrigationRequirementLogSerializer(log).data)

        today = ActualWeatherReading.objects.filter(farm=farm).order_by("-date").first()
        if today is None:
            return Response(
                {"detail": "No weather data available for this farm yet."}, status=404
            )
        rainfall_week = sum(
            r.rainfall_mm
            for r in ActualWeatherReading.objects.filter(farm=farm).order_by("-date")[:7]
        )
        result = compute_irrigation_requirement(
            et0_mm=today.et0_mm,
            crop_stage=farm.current_crop_stage(today.gdd_cumulative),
            field_area_m2=farm.area_m2,
            pump_discharge_l_s=farm.pump_discharge_l_s,
            rainfall_week_mm=rainfall_week,
        )
        result.update(farm=farm.id, date=today.date, pump_hp=farm.pump_hp)
        return Response(result)

    # Ad-hoc computation from raw query parameters.
    try:
        result = compute_irrigation_requirement(
            et0_mm=float(request.query_params["et0_mm"]),
            crop_stage=request.query_params.get("crop_stage", "Grand Growth"),
            field_area_m2=float(request.query_params.get("field_area_m2", 4000)),
            pump_discharge_l_s=float(request.query_params.get("pump_discharge_l_s", 5)),
            rainfall_week_mm=float(request.query_params.get("rainfall_week_mm", 0)),
            subtract_rainfall=request.query_params.get("subtract_rainfall") in ("true", "1"),
        )
    except KeyError as exc:
        return Response({"detail": f"Missing required parameter: {exc}"}, status=400)
    except ValueError:
        return Response({"detail": "Numeric parameters must be numbers."}, status=400)
    return Response(result)


@api_view(["GET"])
def irrigation_ml_predict(request):
    """
    GET /api/ml/irrigation/?farm=1
    GET /api/ml/irrigation/?soil_type=Sandy&crop_stage=Sprouting&et0_mm=5&rainfall_week_mm=10&temp_mean_c=32&humidity_pct=60&vpd_kpa=1.5

    ML second-opinion irrigation requirement, either from a farm's live weather
    context or from explicit query parameters (useful for "what if" scenarios in
    the frontend, e.g. previewing a different soil type).
    """
    farm_id = allowed_farm_id(request)

    if farm_id:
        farm = get_object_or_404(FarmProfile, pk=farm_id)
        today = _latest_weather_for_farm(farm)
        if today is None:
            return Response({"detail": "No weather data available for this farm."}, status=404)
        result = predict_irrigation_requirement(
            soil_type=request.query_params.get("soil_type", farm.soil_type),
            crop_stage=request.query_params.get("crop_stage", "Vegetative"),
            et0_mm=today.et0_mm,
            rainfall_week_mm=today.rainfall_mm * 7,
            temp_mean_c=(today.temp_max_c + today.temp_min_c) / 2,
            humidity_pct=today.humidity_pct,
            vpd_kpa=today.vpd_kpa,
        )
    else:
        try:
            result = predict_irrigation_requirement(
                soil_type=request.query_params["soil_type"],
                crop_stage=request.query_params["crop_stage"],
                et0_mm=float(request.query_params["et0_mm"]),
                rainfall_week_mm=float(request.query_params["rainfall_week_mm"]),
                temp_mean_c=float(request.query_params["temp_mean_c"]),
                humidity_pct=float(request.query_params["humidity_pct"]),
                vpd_kpa=float(request.query_params["vpd_kpa"]),
            )
        except KeyError as exc:
            return Response({"detail": f"Missing required parameter: {exc}"}, status=400)

    if result is None:
        return Response({"detail": "Irrigation ML model not trained yet. Run: python manage.py train_ml_models"}, status=503)
    return Response(result)


@api_view(["GET"])
def yield_ml_predict(request):
    """
    GET /api/ml/yield/?farm=1
    GET /api/ml/yield/?gdd_at_harvest=4800&avg_disease_risk_pct=20&irrigation_adequacy_pct=90&soil_type=Black%20Cotton
    """
    farm_id = allowed_farm_id(request)

    if farm_id:
        farm = get_object_or_404(FarmProfile, pk=farm_id)
        today = _latest_weather_for_farm(farm)
        current_gdd = today.gdd_cumulative if today else 0
        top_diseases = Disease.objects.order_by("-risk_score")[:9]
        avg_disease_risk = sum(d.risk_score for d in top_diseases) / len(top_diseases) if top_diseases else 30
        result = predict_yield(
            gdd_at_harvest=current_gdd + 600,  # rough remaining-season projection
            avg_disease_risk_pct=avg_disease_risk,
            irrigation_adequacy_pct=float(request.query_params.get("irrigation_adequacy_pct", 80)),
            soil_type=farm.soil_type,
        )
    else:
        try:
            result = predict_yield(
                gdd_at_harvest=float(request.query_params["gdd_at_harvest"]),
                avg_disease_risk_pct=float(request.query_params["avg_disease_risk_pct"]),
                irrigation_adequacy_pct=float(request.query_params["irrigation_adequacy_pct"]),
                soil_type=request.query_params["soil_type"],
            )
        except KeyError as exc:
            return Response({"detail": f"Missing required parameter: {exc}"}, status=400)

    if result is None:
        return Response({"detail": "Yield ML model not trained yet. Run: python manage.py train_ml_models"}, status=503)
    return Response(result)


@api_view(["POST"])
def refresh_weather_now(request):
    """
    POST /api/weather/refresh/?farm=1

    Triggers an on-demand Open-Meteo (history + forecast) sync for the given farm, right
    now, in the request/response cycle — this is what makes the "real-time" claim
    honest rather than implying a live streaming connection. Returns the freshly
    fetched today_weather + a timestamp so the frontend can show "Updated just now".

    This is the user-triggered complement to the automatic hourly sync (see
    advisory/scheduler.py) — both paths go through sync_service.run_weather_sync()
    and log an identical SchedulerLog row (trigger="manual" here).
    """
    farm_id = allowed_farm_id(request)
    farm = get_object_or_404(FarmProfile, pk=farm_id) if farm_id else FarmProfile.objects.first()
    if farm is None:
        return Response({"detail": "No farm profiles exist yet."}, status=404)

    from .sync_service import run_weather_sync

    log = run_weather_sync(farm_qs=FarmProfile.objects.filter(pk=farm.pk), trigger="manual")
    if log.status == "failure":
        return Response(
            {"detail": log.error_message or "Sync failed.", "log": SchedulerLogSerializer(log).data},
            status=502,
        )

    today = (
        ActualWeatherReading.objects.filter(farm=farm, date=timezone.localdate()).first()
        or ForecastWeatherReading.objects.filter(farm=farm, date=timezone.localdate()).first()
        or ActualWeatherReading.objects.filter(farm=farm).order_by("-date").first()
    )
    return Response(
        {
            "synced_at": log.finished_at,
            "today_weather": _serialize_weather(today),
            "log": SchedulerLogSerializer(log).data,
        }
    )


@api_view(["GET"])
def ml_status(request):
    """GET /api/ml/status/ -> which models are currently trained and loadable."""
    return Response(models_available())


@api_view(["GET"])
@permission_classes([IsAdminUser])
def scheduler_status(request):
    """
    GET /api/scheduler/status/

    Snapshot for the dashboard's Scheduler Monitoring panel: whether the
    automatic hourly job is currently running in this process, the
    configured interval, when it will next fire, and a summary of its most
    recent run (success/partial/failure, record counts, per-API health).
    """
    from . import scheduler as scheduler_module

    sched = scheduler_module.get_scheduler()
    next_run_at = None
    if sched is not None:
        job = sched.get_job(scheduler_module.JOB_ID)
        if job is not None and job.next_run_time is not None:
            next_run_at = job.next_run_time

    last_log = SchedulerLog.objects.order_by("-started_at").first()
    interval = settings.WEATHER_SYNC_INTERVAL_MINUTES

    # Production runs the scheduler in its own container (`manage.py run_scheduler`),
    # so this web process has no in-process scheduler to ask. Judge by the log instead:
    # a run within the last 2 intervals + 5 minutes means the external scheduler is alive.
    mode = "in_process" if sched is not None else "stopped"
    running = sched is not None
    if sched is None and last_log is not None:
        age = timezone.now() - last_log.started_at
        if age <= timedelta(minutes=2 * interval + 5):
            mode, running = "external", True
            next_run_at = last_log.started_at + timedelta(minutes=interval)

    return Response(
        {
            "running": running,
            "mode": mode,
            "autostart_enabled": settings.SCHEDULER_AUTOSTART,
            "interval_minutes": interval,
            "max_retries": settings.WEATHER_SYNC_MAX_RETRIES,
            "next_run_at": next_run_at,
            "last_run": SchedulerLogSerializer(last_log).data if last_log else None,
        }
    )


@api_view(["GET"])
@permission_classes([IsAdminUser])
def scheduler_logs(request):
    """GET /api/scheduler/logs/?limit=20 -> recent sync runs, newest first."""
    try:
        limit = min(int(request.query_params.get("limit", 20)), 200)
    except ValueError:
        limit = 20
    logs = SchedulerLog.objects.order_by("-started_at")[:limit]
    return Response(SchedulerLogSerializer(logs, many=True).data)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def scheduler_run_now(request):
    """
    POST /api/scheduler/run-now/

    Triggers an out-of-band sync of every farm right now (not just one, unlike
    /api/weather/refresh/), logged with trigger="manual" the same way a
    scheduled run would be. Useful for an admin "Run sync now" button.
    """
    from .sync_service import run_weather_sync

    log = run_weather_sync(trigger="manual")
    status_code = 200 if log.status != "failure" else 502
    return Response(SchedulerLogSerializer(log).data, status=status_code)
"Added BY Abhinav"
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    """
    GET /api/auth/me/ -> who the logged-in user is and the farms they own.
    `farm` is their first farm (kept for older clients); `farms` is all of them.
    Staff/admin accounts normally own none (farm is null, farms is empty).
    """
    farms = list(FarmProfile.objects.filter(owner=request.user).order_by("id"))
    return Response(
        {
            "username": request.user.username,
            "is_staff": request.user.is_staff,
            "farm": FarmProfileSerializer(farms[0]).data if farms else None,
            "farms": FarmProfileSerializer(farms, many=True).data,
        }
        
    )
    
    
@api_view(["GET"])
def history_list(request):
    """
    GET /api/history/?range=last20|7d|30d&farm=<id>

    The observed (Open-Meteo) daily readings for one farm, newest first.
    Farmers always get their own farm; admins can pick one with ?farm=.
    """
    range_key = request.query_params.get("range", "last20")
    if range_key not in HISTORY_RANGES:
        return Response(
            {"detail": "range must be one of: " + ", ".join(HISTORY_RANGES)},
            status=400,
        )

    farm_id = allowed_farm_id(request)
    farm = (
        FarmProfile.objects.filter(pk=farm_id).first()
        if farm_id
        else FarmProfile.objects.order_by("id").first()
    )
    if farm is None:
        raise Http404("Farm not found.")

    rows = history_rows(farm.id, range_key)
    return Response(
        {
            "farm": {"id": farm.id, "farm_name": farm.farm_name, "farmer_name": farm.farmer_name},
            "range": range_key,
            "count": len(rows),
            "results": ActualWeatherReadingSerializer(rows, many=True).data,
        }
    )
@api_view(["GET"])
def history_export(request):
    """
    GET /api/history/export/?range=last20|7d|30d&file=csv|xlsx&farm=<id>

    The same rows as /api/history/, as a downloadable file. (The parameter is
    called `file`, not `format`, because DRF reserves ?format= for itself.)
    """
    range_key = request.query_params.get("range", "last20")
    file_type = request.query_params.get("file", "csv")
    if range_key not in HISTORY_RANGES:
        return Response({"detail": "range must be one of: " + ", ".join(HISTORY_RANGES)}, status=400)
    if file_type not in ("csv", "xlsx"):
        return Response({"detail": "file must be csv or xlsx"}, status=400)

    farm_id = allowed_farm_id(request)
    farm = (
        FarmProfile.objects.filter(pk=farm_id).first()
        if farm_id
        else FarmProfile.objects.order_by("id").first()
    )
    if farm is None:
        raise Http404("Farm not found.")

    rows = history_rows(farm.id, range_key)
    if file_type == "csv":
        content = csv_bytes(rows)
        content_type = "text/csv; charset=utf-8"
    else:
        content = xlsx_bytes(rows, farm, range_key)
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="agriaura-history-farm{farm.id}-{range_key}.{file_type}"'
    return response    