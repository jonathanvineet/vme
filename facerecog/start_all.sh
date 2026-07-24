#!/bin/bash
# Starts the in-gate, out-gate, and admin servers together.
# Ctrl+C stops all three. Logs go to logs/*.log.

set -e
cd "$(dirname "$0")"

mkdir -p logs

PORT_IN=5050
PORT_OUT=5051
PORT_ADMIN=5052

for PORT in $PORT_IN $PORT_OUT $PORT_ADMIN; do
    PID=$(lsof -ti :$PORT 2>/dev/null || true)
    if [ -n "$PID" ]; then
        echo "Port $PORT is in use by PID $PID, killing it..."
        kill -9 $PID
    fi
done

cleanup() {
    echo ""
    echo "Stopping all servers..."
    kill $PID_IN $PID_OUT $PID_ADMIN 2>/dev/null
    wait 2>/dev/null
    exit 0
}
trap cleanup INT TERM

python3 gate_server.py --mode in --port $PORT_IN > logs/gate_in.log 2>&1 &
PID_IN=$!

python3 gate_server.py --mode out --port $PORT_OUT > logs/gate_out.log 2>&1 &
PID_OUT=$!

python3 admin_server.py --port $PORT_ADMIN > logs/admin.log 2>&1 &
PID_ADMIN=$!

IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "<mac-ip>")

sleep 3
echo ""
echo "All servers running:"
echo "  IN gate:    https://$IP:$PORT_IN"
echo "  OUT gate:   https://$IP:$PORT_OUT"
echo "  Admin:      https://$IP:$PORT_ADMIN/login"
echo ""
echo "Logs: logs/gate_in.log logs/gate_out.log logs/admin.log"
echo "Press Ctrl+C to stop everything."

wait
