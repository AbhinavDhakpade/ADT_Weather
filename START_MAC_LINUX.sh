#!/bin/bash
echo "================================================"
echo "  AgriAura - Smart Sugarcane Advisory System"
echo "================================================"

# Start Django backend
cd backend
source venv/bin/activate
echo "Starting Django on http://127.0.0.1:8000 ..."
python manage.py runserver 0.0.0.0:8000 &
DJANGO_PID=$!

sleep 3

# Start Vite frontend
cd ../frontend
echo "Starting React frontend on http://localhost:5173 ..."
npm run dev &
VITE_PID=$!

echo ""
echo "================================================"
echo "  Open: http://localhost:5173"
echo "  Stop: Press Ctrl+C"
echo "================================================"

trap "kill $DJANGO_PID $VITE_PID" EXIT
wait
