#!/data/data/com.termux/files/usr/bin/bash

# Start Flask backend
echo "Starting Flask backend..."
cd backend
python app.py &
BACKEND_PID=$!

# Wait a moment for backend to start
sleep 2

# Start a simple HTTP server for frontend
echo "Starting frontend server..."
cd ../frontend
python -m http.server 8000 &
FRONTEND_PID=$!

echo "✅ XRP Wallet Scanner is running!"
echo "📱 Frontend: http://localhost:8000"
echo "🔧 Backend API: http://localhost:5000"
echo ""
echo "Press Ctrl+C to stop both servers"

# Handle Ctrl+C
trap "kill $BACKEND_PID $FRONTEND_PID; exit" INT

# Wait for processes
wait
