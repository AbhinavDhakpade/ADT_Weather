from rest_framework import serializers

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
from .ml.inference import predict_disease_risk


class TreatmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Treatment
        fields = [
            "disease_type",
            "biological",
            "chemical",
            "timing",
            "safety",
            "recovery",
        ]


class DiseaseSerializer(serializers.ModelSerializer):
    risk_label = serializers.ReadOnlyField()
    treatment = serializers.SerializerMethodField()
    ml_prediction = serializers.SerializerMethodField()

    class Meta:
        model = Disease
        fields = [
            "id",
            "sr_no",
            "name",
            "organism",
            "crop_stage",
            "disease_type",
            "irrigation_requirement_l",
            "actual_irrigation_given",
            "rainfall_mm_week",
            "vapour_pressure_kpa",
            "vpd_kpa",
            "relative_humidity_pct",
            "avg_temp_c",
            "leaf_wetness_hrs",
            "gdd_range",
            "risk_score",
            "risk_label",
            "treatment",
            "ml_prediction",
        ]

    def get_treatment(self, obj):
        t = Treatment.objects.filter(disease_type=obj.disease_type).first()
        if not t:
            return None
        return TreatmentSerializer(t).data

    def get_ml_prediction(self, obj):
        """
        RandomForest 'second opinion' risk probability, computed from the farm's
        most recent weather reading. Returns None if no weather context is
        available in the serializer's context or if the ML model isn't trained.
        """
        weather = self.context.get("current_weather")
        if weather is None:
            return None

        result = predict_disease_risk(
            disease_type=obj.disease_type,
            temp_max_c=weather.temp_max_c,
            temp_min_c=weather.temp_min_c,
            humidity_pct=weather.humidity_pct,
            rainfall_week_mm=weather.rainfall_mm * 7 if weather.rainfall_mm else 0,
            leaf_wetness_hrs=min(24, weather.humidity_pct / 5),
            vpd_kpa=weather.vpd_kpa,
            gdd_cumulative=weather.gdd_cumulative,
        )
        return result


class DiseaseListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for mini/dashboard widgets."""

    risk_label = serializers.ReadOnlyField()
    ml_risk_pct = serializers.SerializerMethodField()

    class Meta:
        model = Disease
        fields = [
            "id",
            "name",
            "disease_type",
            "crop_stage",
            "avg_temp_c",
            "relative_humidity_pct",
            "gdd_range",
            "risk_score",
            "risk_label",
            "ml_risk_pct",
        ]

    def get_ml_risk_pct(self, obj):
        weather = self.context.get("current_weather")
        if weather is None:
            return None
        from .ml.inference import predict_disease_risk

        result = predict_disease_risk(
            disease_type=obj.disease_type,
            temp_max_c=weather.temp_max_c,
            temp_min_c=weather.temp_min_c,
            humidity_pct=weather.humidity_pct,
            rainfall_week_mm=weather.rainfall_mm * 7 if weather.rainfall_mm else 0,
            leaf_wetness_hrs=min(24, weather.humidity_pct / 5),
            vpd_kpa=weather.vpd_kpa,
            gdd_cumulative=weather.gdd_cumulative,
        )
        return result["risk_pct"] if result else None


class IrrigationRequirementLogSerializer(serializers.ModelSerializer):
    """Computed, continuously stored irrigation requirement — all numeric JSON."""

    class Meta:
        model = IrrigationRequirementLog
        fields = [
            "id",
            "farm",
            "date",
            "crop_stage",
            "kc",
            "et0_mm_day",
            "etc_mm_day",
            "effective_rainfall_mm_day",
            "net_requirement_mm_day",
            "field_area_m2",
            "water_required_l_day",
            "pump_hp",
            "pump_discharge_l_s",
            "pump_capacity_l_hr",
            "irrigation_time_hr",
            "irrigation_time_label",
            "computed_at",
        ]


class IrrigationRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = IrrigationRule
        fields = [
            "id",
            "sr_no",
            "soil_type",
            "crop_stage",
            "moisture_pct",
            "rainfall_mm_week",
            "temp_c",
            "relative_humidity_pct",
            "vpd_kpa",
            "etc_mm_day",
            "requirement_l_plant",
            "decision",
            "remark",
        ]


_WEATHER_COMMON_FIELDS = [
    "date",
    "temp_max_c",
    "temp_min_c",
    "humidity_pct",
    "rainfall_mm",
    "et0_mm",
    "vpd_kpa",
    "solar_mj_m2",
    "wind_kmh",
    "gdd_daily",
    "gdd_cumulative",
    "weather_icon",
    "is_forecast",
    "wind_direction_deg",
    "wind_gusts_kmh",
    "uv_index_max",
    "precipitation_probability_pct",
    "sunrise",
    "sunset",
    "soil_temp_0cm_c",
    "weather_code",
    "condition_text",
    "data_source",
    "fetched_at",
    "feels_like_c",
]


class ActualWeatherReadingSerializer(serializers.ModelSerializer):
    """Serializes rows from the Actual Weather Database (Open-Meteo history)."""

    feels_like_c = serializers.ReadOnlyField()
    is_forecast = serializers.ReadOnlyField()

    class Meta:
        model = ActualWeatherReading
        fields = _WEATHER_COMMON_FIELDS


class ForecastWeatherReadingSerializer(serializers.ModelSerializer):
    """Serializes rows from the Forecast Weather Database (Open-Meteo forecast),
    including the confidence score and prediction model absent from actual readings."""

    feels_like_c = serializers.ReadOnlyField()
    is_forecast = serializers.ReadOnlyField()

    class Meta:
        model = ForecastWeatherReading
        fields = _WEATHER_COMMON_FIELDS + ["confidence_score", "prediction_model"]


class AlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = Alert
        fields = [
            "id",
            "severity",
            "icon",
            "title",
            "description",
            "created_at",
            "is_active",
            "source",
        ]


class AdvisoryTimelineItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdvisoryTimelineItem
        fields = ["id", "when_label", "dot_state", "action", "note", "sort_order"]


class CropGrowthStageSerializer(serializers.ModelSerializer):
    class Meta:
        model = CropGrowthStage
        fields = ["stage_name", "gdd_threshold", "sort_order"]


class IrrigationMLPredictionSerializer(serializers.Serializer):
    requirement_l_plant = serializers.FloatField()
    uncertainty_l_plant = serializers.FloatField()


class YieldMLPredictionSerializer(serializers.Serializer):
    yield_t_ha = serializers.FloatField()


class FarmProfileSerializer(serializers.ModelSerializer):
    growth_stages = CropGrowthStageSerializer(many=True, read_only=True)

    class Meta:
        model = FarmProfile
        fields = [
            "id",
            "farm_name",
            "farmer_name",
            "phone",
            "village",
            "latitude",
            "longitude",
            "crop_name",
            "variety",
            "planting_date",
            "soil_type",
            "irrigation_method",
            "area_hectares",
            "pump_hp",
            "pump_discharge_l_s",
            "elevation_m",
            "base_temp_c",
            "expected_harvest",
            "expected_yield_t_ha",
            "revenue_estimate",
            "growth_stages",
            "boundary_geojson",
            "boundary_source_file",
        ]

    def validate_latitude(self, value):
        if not (-90 <= value <= 90):
            raise serializers.ValidationError("Latitude must be between -90 and 90.")
        return value

    def validate_longitude(self, value):
        if not (-180 <= value <= 180):
            raise serializers.ValidationError("Longitude must be between -180 and 180.")
        return value

    def validate_pump_discharge_l_s(self, value):
        if value <= 0:
            raise serializers.ValidationError("Pump discharge must be greater than 0 L/s.")
        return value

    def validate_pump_hp(self, value):
        if value <= 0:
            raise serializers.ValidationError("Pump HP must be greater than 0.")
        return value

    def validate_area_hectares(self, value):
        if value <= 0:
            raise serializers.ValidationError("Field area must be greater than 0.")
        return value

    def validate_area_hectares(self, value):
        if value <= 0:
            raise serializers.ValidationError("Area must be greater than 0.")
        if value > 10000:
            raise serializers.ValidationError("Area seems too large. Enter value in hectares.")
        return value


class SchedulerLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = SchedulerLog
        fields = [
            "id",
            "task_name",
            "trigger",
            "started_at",
            "finished_at",
            "duration_seconds",
            "status",
            "farms_processed",
            "records_fetched",
            "records_updated",
            "duplicates_removed",
            "retry_attempts",
            "history_status",
            "open_meteo_status",
            "error_message",
        ]
