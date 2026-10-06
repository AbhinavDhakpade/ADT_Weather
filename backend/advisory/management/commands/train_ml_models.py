"""
Management command: train_ml_models

Trains all three AgriAura ML models (disease risk classifier, irrigation
requirement regressor, yield prediction regressor) and saves them to
advisory/ml/trained_models/. Safe to re-run any time — each run overwrites the
previous model files and metrics.

Usage:
    python manage.py train_ml_models
"""

from django.core.management.base import BaseCommand

from advisory.ml.inference import clear_model_cache
from advisory.ml.train import train_all


class Command(BaseCommand):
    help = "Train AgriAura's ML models (disease risk, irrigation, yield) on physically-grounded synthetic data."

    def handle(self, *args, **options):
        self.stdout.write("Training disease risk classifier, irrigation regressor, and yield regressor...")
        results = train_all()
        clear_model_cache()

        self.stdout.write(self.style.SUCCESS("\nTraining complete. Metrics:"))
        self.stdout.write(f"\nDisease risk classifier (per disease_type, accuracy / ROC-AUC):")
        for disease_type, m in results["disease_risk"].items():
            self.stdout.write(f"  {disease_type:14s} acc={m['accuracy']:.3f}  auc={m['roc_auc']}")

        irr = results["irrigation"]
        self.stdout.write(f"\nIrrigation regressor: MAE={irr['mae_l_per_plant']} L/plant, R²={irr['r2']}")

        yld = results["yield"]
        self.stdout.write(f"Yield regressor: MAE={yld['mae_t_per_ha']} t/ha, R²={yld['r2']}")

        self.stdout.write(self.style.SUCCESS("\nModels saved to advisory/ml/trained_models/"))
