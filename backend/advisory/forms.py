from django import forms

from .models import FarmProfile


class ManualFarmerForm(forms.ModelForm):
    """Form used by the admin 'Add farmer > Add manually' page."""

    class Meta:
        model = FarmProfile
        fields = [
            "farmer_name",
            "phone",
            "village",
            "farm_name",
            "latitude",
            "longitude",
            "area_hectares",
            "crop_name",
            "variety",
            "planting_date",
            "soil_type",
            "irrigation_method",
            "pump_hp",
            "pump_discharge_l_s",
        ]
        widgets = {
            "planting_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Start these fields empty instead of using the model's demo defaults.
        for name in ("farmer_name", "farm_name", "village", "latitude", "longitude", "area_hectares"):
            self.initial[name] = None

    def clean_latitude(self):
        value = self.cleaned_data["latitude"]
        if not -90 <= value <= 90:
            raise forms.ValidationError("Latitude must be between -90 and 90.")
        return value

    def clean_longitude(self):
        value = self.cleaned_data["longitude"]
        if not -180 <= value <= 180:
            raise forms.ValidationError("Longitude must be between -180 and 180.")
        return value

    def clean_area_hectares(self):
        value = self.cleaned_data["area_hectares"]
        if value <= 0:
            raise forms.ValidationError("Area must be greater than 0.")
        return value