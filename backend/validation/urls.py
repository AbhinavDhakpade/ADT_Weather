from django.urls import path

from . import views

urlpatterns = [
    path("stations/", views.station_list, name="validation-stations"),
    path("summary/", views.validation_summary, name="validation-summary"),
]
