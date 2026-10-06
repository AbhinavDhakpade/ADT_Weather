import secrets
import string

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from advisory.models import FarmProfile


class Command(BaseCommand):
    help = "Create a login account for every KML-imported farm that has no owner yet."

    def handle(self, *args, **options):
        User = get_user_model()
        alphabet = string.ascii_letters + string.digits
        rows = []

        with transaction.atomic():
            farms = FarmProfile.objects.filter(owner__isnull=True).exclude(boundary_source_file="")
            for farm in farms:
                username = f"farmer{farm.pk}"
                if User.objects.filter(username=username).exists():
                    self.stdout.write(self.style.WARNING(f"Skipped {username}: username already exists"))
                    continue

                password = "".join(secrets.choice(alphabet) for _ in range(10))
                user = User.objects.create_user(
                    username=username,
                    password=password,
                    first_name=farm.farmer_name,
                )
                farm.owner = user
                farm.save(update_fields=["owner"])
                rows.append((farm.farmer_name, username, password))

        if not rows:
            self.stdout.write("No new accounts created (every imported farm already has an owner).")
            return

        self.stdout.write(self.style.SUCCESS(f"Created {len(rows)} farmer account(s):\n"))
        self.stdout.write(f"{'Farmer':<34}{'Username':<12}Password")
        for name, username, password in rows:
            self.stdout.write(f"{name:<34}{username:<12}{password}")
        self.stdout.write(
            self.style.WARNING("\nPasswords are shown only once. Copy them somewhere safe now.")
        )