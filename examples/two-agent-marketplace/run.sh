#!/usr/bin/env bash
# Start both agents + the dashboard.
set -e

DEMO_DIR="${DEMO_DIR:-/tmp/two-agent-marketplace}"
PLANNER_MODE="${DEMO_PLANNER_MODE:-openrouter}"
PLANNER_MODEL="${DEMO_PLANNER_MODEL:-anthropic/claude-sonnet-4}"

if [ ! -d "$DEMO_DIR/buyer" ] || [ ! -d "$DEMO_DIR/oracle" ]; then
  echo "  ERROR: agents not generated. Run ./setup.sh first."
  exit 1
fi

# Start oracle (port 8002 health, 9002 A2A)
echo "Starting oracle..."
forge run "$DEMO_DIR/oracle" \
  --mode paper --auto-approve \
  --interval 30 --max-ticks 999 \
  --health-port 8002 --a2a-port 9002 \
  --planner-mode "$PLANNER_MODE" --planner-model "$PLANNER_MODEL" \
  > "$DEMO_DIR/oracle.log" 2>&1 &
ORACLE_PID=$!

# Start buyer (port 8001 health, 9001 A2A)
echo "Starting buyer..."
forge run "$DEMO_DIR/buyer" \
  --mode paper --auto-approve \
  --interval 30 --max-ticks 999 \
  --health-port 8001 --a2a-port 9001 \
  --planner-mode "$PLANNER_MODE" --planner-model "$PLANNER_MODEL" \
  > "$DEMO_DIR/buyer.log" 2>&1 &
BUYER_PID=$!

# Start dashboard (port 5000)
echo "Starting dashboard..."
DEMO_DIR="$DEMO_DIR" python3 "$(dirname "$0")/dashboard.py" &
DASH_PID=$!

trap "kill $ORACLE_PID $BUYER_PID $DASH_PID 2>/dev/null" EXIT INT TERM

echo ""
echo "  Oracle:    PID $ORACLE_PID  → log: $DEMO_DIR/oracle.log"
echo "  Buyer:     PID $BUYER_PID   → log: $DEMO_DIR/buyer.log"
echo "  Dashboard: http://localhost:5000"
echo ""
echo "  Trigger a payment:  python3 $(dirname "$0")/pay-once.py"
echo ""
echo "  Press Ctrl+C to stop all."
wait
