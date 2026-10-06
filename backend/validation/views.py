"""Read-only validation API for administrators."""

import datetime

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from . import engine
from .models import WeatherStation
from .service import validate_station


@api_view(["GET"])
@permission_classes([IsAdminUser])
def station_list(request):
    """GET /api/validation/stations/ -> stations with reading counts."""
    data = []
    for s in WeatherStation.objects.select_related("farm"):
        data.append({
            "id": s.id, "name": s.name, "farm": s.farm_id, "farm_name": s.farm.farm_name,
            "timezone": s.timezone, "readings": s.readings.count(),
        })
    return Response(data)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def validation_summary(request):
    """
    GET /api/validation/summary/?station=<id>&days=30
    Metrics (bias/MAE/RMSE/r, rain skill, skill by forecast lead time) for the last N days.
    """
    try:
        station = WeatherStation.objects.select_related("farm").get(pk=request.query_params.get("station"))
    except (WeatherStation.DoesNotExist, ValueError, TypeError):
        return Response({"detail": "Pass ?station=<id> of an existing station."}, status=404)
    try:
        days = max(1, min(int(request.query_params.get("days", 30)), 365))
        min_cov = float(request.query_params.get("min_coverage", engine.DEFAULT_MIN_COVERAGE))
        thr = float(request.query_params.get("rain_threshold", engine.DEFAULT_RAIN_THRESHOLD_MM))
    except ValueError:
        return Response({"detail": "days, min_coverage and rain_threshold must be numbers."}, status=400)
    end = datetime.date.today()
    start = end - datetime.timedelta(days=days)
    result, _daily, context = validate_station(station, start, end, min_cov, thr)
    return Response({"context": context, **result.to_dict()})
