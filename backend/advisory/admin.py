import csv
import io
from urllib.parse import quote

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.template.response import TemplateResponse
from django.urls import path

from .forms import ManualFarmerForm
from .kml_import import ImportResult, import_kml_file, _free_username, _new_password


from .kml_import import ImportResult, import_kml
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


@admin.register(Disease)
class DiseaseAdmin(admin.ModelAdmin):
    list_display = ("sr_no", "name", "disease_type", "crop_stage", "risk_score", "risk_label")
    list_filter = ("disease_type",)
    search_fields = ("name", "organism")
    ordering = ("sr_no",)


@admin.register(Treatment)
class TreatmentAdmin(admin.ModelAdmin):
    list_display = ("disease_type",)


@admin.register(IrrigationRule)
class IrrigationRuleAdmin(admin.ModelAdmin):
    list_display = ("sr_no", "soil_type", "crop_stage", "decision", "etc_mm_day")
    list_filter = ("soil_type", "decision")


@admin.register(IrrigationRequirementLog)
class IrrigationRequirementLogAdmin(admin.ModelAdmin):
    list_display = (
        "farm", "date", "crop_stage", "kc", "etc_mm_day",
        "water_required_l_day", "pump_capacity_l_hr", "irrigation_time_label",
    )
    list_filter = ("farm", "crop_stage")
    ordering = ("-date",)


@admin.register(FarmProfile)
class FarmProfileAdmin(admin.ModelAdmin):
    list_display = ("farm_name", "farmer_name", "owner", "village", "variety", "soil_type")
    search_fields = ("farm_name", "farmer_name", "owner__username")
    # Adds an "Import KML files" button to the top of the farm list.
    change_list_template = "admin/advisory/farmprofile/change_list.html"

    def get_urls(self):
        custom = [
            path(
                "add-farmer/",
                self.admin_site.admin_view(self.add_farmer_view),
                name="advisory_farmprofile_add_farmer",
            ),
            path(
                "add-farmer/manual/",
                self.admin_site.admin_view(self.add_manual_view),
                name="advisory_farmprofile_add_manual",
            ),
            path(
                "import-kml/",
                self.admin_site.admin_view(self.import_kml_view),
                name="advisory_farmprofile_import_kml",
            ),
        ]
        return custom + super().get_urls()
    def add_farmer_view(self, request):
        """Chooser page: add farmers from KML files, or manually."""
        if not (request.user.has_perm("advisory.add_farmprofile") and request.user.has_perm("auth.add_user")):
            raise PermissionDenied

        context = {
            **self.admin_site.each_context(request),
            "title": "Add farmer",
            "opts": self.model._meta,
        }
        return TemplateResponse(request, "admin/advisory/farmprofile/add_farmer.html", context)

    def add_manual_view(self, request):
        """Type in a farmer's details; creates the farm plus a login for them."""
        if not (request.user.has_perm("advisory.add_farmprofile") and request.user.has_perm("auth.add_user")):
            raise PermissionDenied

        context = {
            **self.admin_site.each_context(request),
            "title": "Add farmer manually",
            "opts": self.model._meta,
        }

        if request.method == "POST":
            form = ManualFarmerForm(request.POST)
            if form.is_valid():
                User = get_user_model()
                with transaction.atomic():
                    farm = form.save()
                    username = _free_username(User, farm.id)
                    password = _new_password()
                    user = User.objects.create_user(
                        username=username,
                        password=password,
                        first_name=farm.farmer_name[:150],
                    )
                    farm.owner = user
                    farm.save(update_fields=["owner"])
                context["created"] = {
                    "farmer_name": farm.farmer_name,
                    "farm_id": farm.id,
                    "username": username,
                    "password": password,
                }
                return TemplateResponse(request, "admin/advisory/farmprofile/add_manual.html", context)
        else:
            form = ManualFarmerForm()

        context["form"] = form
        return TemplateResponse(request, "admin/advisory/farmprofile/add_manual.html", context)
    
    
    def import_kml_view(self, request):
        """Upload one or more KML files; show what happened to each one."""
        # Importing creates farms AND login accounts, so require both permissions.
        if not (request.user.has_perm("advisory.add_farmprofile") and request.user.has_perm("auth.add_user")):
            raise PermissionDenied

        context = {
            **self.admin_site.each_context(request),
            "title": "Import farmers from KML files",
            "opts": self.model._meta,
        }

        if request.method == "POST":
            files = request.FILES.getlist("kml_files")
            if not files:
                context["error"] = "Please choose at least one .kml file."
                return TemplateResponse(request, "admin/advisory/farmprofile/import_kml.html", context)

            results = []
            for upload in files:
                if not upload.name.lower().endswith(".kml"):
                    results.append(ImportResult(upload.name, "error", "Not a .kml file."))
                    continue
                    results.extend(import_kml_file(upload, upload.name))

            counts = {"created": 0, "added": 0, "exists": 0, "error": 0}
            for r in results:
                counts[r.status] += 1

            # New passwords exist only in memory right now. Offer them as a CSV
            # built into the page itself, so nothing is ever stored on the server.
            credentials = [r for r in results if r.password]
            csv_href = ""
            if credentials:
                buf = io.StringIO()
                writer = csv.writer(buf)
                writer.writerow(["Farmer", "Username", "Password", "Farm id"])
                for r in credentials:
                    writer.writerow([r.farmer_name, r.username, r.password, r.farm_id])
                csv_href = "data:text/csv;charset=utf-8," + quote(buf.getvalue())

            context.update(
                results=results,
                counts=counts,
                credentials=credentials,
                csv_href=csv_href,
            )

        return TemplateResponse(request, "admin/advisory/farmprofile/import_kml.html", context)


@admin.register(ActualWeatherReading)
class ActualWeatherReadingAdmin(admin.ModelAdmin):
    list_display = ("farm", "date", "temp_max_c", "temp_min_c", "humidity_pct", "rainfall_mm", "data_source")
    list_filter = ("farm", "data_source")
    ordering = ("-date",)


@admin.register(ForecastWeatherReading)
class ForecastWeatherReadingAdmin(admin.ModelAdmin):
    list_display = (
        "farm", "date", "temp_max_c", "temp_min_c", "humidity_pct", "rainfall_mm",
        "confidence_score", "prediction_model",
    )
    list_filter = ("farm", "prediction_model")
    ordering = ("date",)


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ("title", "severity", "farm", "is_active", "created_at")
    list_filter = ("severity", "is_active", "farm")


@admin.register(AdvisoryTimelineItem)
class AdvisoryTimelineItemAdmin(admin.ModelAdmin):
    list_display = ("farm", "when_label", "action", "dot_state", "sort_order")
    ordering = ("farm", "sort_order")


@admin.register(CropGrowthStage)
class CropGrowthStageAdmin(admin.ModelAdmin):
    list_display = ("farm", "stage_name", "gdd_threshold", "sort_order")
    ordering = ("farm", "sort_order")


@admin.register(SchedulerLog)
class SchedulerLogAdmin(admin.ModelAdmin):
    list_display = (
        "task_name", "trigger", "started_at", "status", "farms_processed",
        "records_fetched", "duplicates_removed", "retry_attempts",
        "history_status", "open_meteo_status", "duration_seconds",
    )
    list_filter = ("status", "trigger", "history_status", "open_meteo_status")
    ordering = ("-started_at",)
    readonly_fields = [f.name for f in SchedulerLog._meta.fields]

    def has_add_permission(self, request):
        return False  # log rows are only ever written by the sync service
