#!/data/data/com.termux/files/usr/bin/bash

echo "=== XRP Wallet Scanner ==="
echo "Starting services..."

# Kill any existing processes
pkill -f "python app.py" 2>/dev/null
pkill -f "http.server" 2>/dev/null

# Start backend in background
echo "1. Starting Flask backend on port 5000..."
cd backend
python app.py > backend.log 2>&1 &
BACKEND_PID=$!
cd ..

# Wait for backend to start
echo "   Waiting for backend to initialize..."
sleep 3

# Test backend
echo "2. Testing backend connection..."
curl -s http://localhost:5000/api/test || {
    echo "   ❌ Backend not responding. Check backend.log"
    cat backend/backend.log
    exit 1
}
echo "   ✅ Backend is working!"

# Start frontend
echo "3. Starting frontend server on port 8000..."
cd frontend
python -m http.server 8000 > frontend.log 2>&1 &
FRONTEND_PID=$!
cd ..

echo ""
echo "✅ All services started successfully!"
echo "📱 Frontend: http://localhost:8000"
echo "🔧 Backend API: http://localhost:5000"
echo "📝 Logs: backend/backend.log and frontend/frontend.log"
echo ""
echo "Press Ctrl+C to stop all services"

# Handle shutdown
trap "echo 'Stopping services...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT

# Wait
wait
