# AgriAura Setup (First Time Only)

## Backend Setup
```bash
cd backend
python -m venv venv

# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

pip install -r requirements.txt
python manage.py migrate
python manage.py seed_data --reset
python manage.py createsuperuser
python manage.py train_ml_models
```

## Frontend Setup
```bash
cd frontend
npm install
```

## Weather data (Open-Meteo)
Open-Meteo is the only weather provider. It needs **no API key and no account**, only outbound internet
access to `api.open-meteo.com` and `archive-api.open-meteo.com`. The app starts with demo data; to pull real
weather run `python manage.py sync_weather` (the built-in scheduler also does this every hour). Optional
overrides (`OPEN_METEO_FORECAST_URL`, `OPEN_METEO_ARCHIVE_URL`, `OPEN_METEO_TIMEOUT_SECONDS`) are listed in
`.env.example`. Details: README, "Live weather data: Open-Meteo".

## Run the App
- **Windows:** Double-click `START_WINDOWS.bat`
- **Mac/Linux:** Run `./START_MAC_LINUX.sh`
- Or manually: open 2 terminals and run each server separately

## Open
http://localhost:5173

## Admin Panel
http://localhost:8000/admin  →  the superuser you create with `python manage.py createsuperuser`
