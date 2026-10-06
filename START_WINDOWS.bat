@echo off
echo ================================================
echo   AgriAura - Smart Sugarcane Advisory System
echo ================================================
echo.
echo Starting Django backend on port 8000...
cd backend
call venv\Scripts\activate
start "AgriAura Backend" cmd /k "python manage.py runserver 0.0.0.0:8000"

echo Waiting for backend to start...
timeout /t 4 /nobreak > nul

echo Starting React frontend on port 5173...
cd ..\frontend
start "AgriAura Frontend" cmd /k "npm run dev"

echo.
echo ================================================
echo   Both servers are starting...
echo   Open your browser to: http://localhost:5173
echo ================================================
pause
