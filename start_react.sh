#!/usr/bin/env bash
# Start Python Flask API backend (port 5001) and React frontend (port 3000) concurrently.
# Usage:  bash start_react.sh
set -u
cd "$(dirname "$0")"

# Use Python from .venv if present (Flask/pandas deps live there), else fall back to python3
PY="python3"
if [ -x .venv/bin/python ]; then
  PY=".venv/bin/python"
fi

# Free up the ports if a previous instance is still running
kill_port() {
  local port="$1"
  local pids
  pids=$(lsof -ti tcp:"$port" 2>/dev/null)
  if [ -n "$pids" ]; then
    echo "Port $port already in use (PID $pids) - stopping it..."
    kill $pids 2>/dev/null
    sleep 1
  fi
}
kill_port 5001
kill_port 3000

echo "Starting Flask API backend on http://localhost:5001 ..."
"$PY" api.py &
FLASK_PID=$!
echo "  Flask PID: $FLASK_PID"

echo "Starting React frontend on http://localhost:3000 ..."
echo "  (leave this terminal open; press Ctrl+C to stop both)"
cd frontend
BROWSER=none npm start &
REACT_PID=$!
echo "  React PID: $REACT_PID"

cleanup() {
  echo ""
  echo "Stopping servers..."
  kill "$FLASK_PID" "$REACT_PID" 2>/dev/null
}
trap cleanup EXIT

# Kill the React toolchain if this script gets Ctrl+C
wait "$REACT_PID"
kill "$FLASK_PID" 2>/dev/null
