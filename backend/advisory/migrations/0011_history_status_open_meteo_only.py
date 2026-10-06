"""
Open-Meteo is now the only weather provider.

Data-preserving by design:
  - RenameField keeps every SchedulerLog row; only the column name changes.
  - AlterField only changes the DEFAULT for new ActualWeatherReading rows. Rows that
    were stored earlier keep their original `data_source` label — historical readings
    are not deleted or relabelled.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("advisory", "0010_alter_farmprofile_owner"),
    ]

    operations = [
        migrations.RenameField(
            model_name="schedulerlog",
            old_name="nasa_power_status",
            new_name="history_status",
        ),
        migrations.AlterField(
            model_name="actualweatherreading",
            name="data_source",
            field=models.CharField(default="open_meteo_archive", max_length=20),
        ),
    ]
