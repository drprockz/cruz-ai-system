#!/usr/bin/env bash
# Run CRUZ load-test scenarios against the PM2 stack.
#
# Usage:
#   ./run_scenarios.sh [scenario]       # run one: morning_rush|agent_mix|sse_streaming|overnight|all
#   ./run_scenarios.sh --dry-run        # print commands without executing
#   HOST=http://host:3000 ./run_scenarios.sh all
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="${HOST:-http://localhost:3000}"
RESULTS_DIR="${RESULTS_DIR:-$SCRIPT_DIR/results}"
DRY_RUN=0
TARGET="${1:-all}"

if [[ "$TARGET" == "--dry-run" ]]; then
    DRY_RUN=1
    TARGET="${2:-all}"
elif [[ "${2:-}" == "--dry-run" ]]; then
    DRY_RUN=1
fi

mkdir -p "$RESULTS_DIR"

run() {
    local scenario="$1" users="$2" spawn="$3" runtime="$4"
    local out="$RESULTS_DIR/${scenario}_$(date +%Y%m%d_%H%M%S)"
    local cmd=(locust -f "$SCRIPT_DIR/locustfile.py" --headless
        --host "$HOST" --users "$users" --spawn-rate "$spawn"
        --run-time "$runtime" --csv "$out" --html "$out.html"
        --only-summary)
    echo "[$scenario] LOCUST_SCENARIO=$scenario ${cmd[*]}"
    if [[ "$DRY_RUN" -eq 1 ]]; then
        return 0
    fi
    LOCUST_SCENARIO="$scenario" "${cmd[@]}"
}

case "$TARGET" in
    morning_rush)  run morning_rush  20 20 60s ;;
    agent_mix)     run agent_mix     50 10 2m ;;
    sse_streaming) run sse_streaming 10 10 90s ;;
    overnight)     run overnight      3  1 3m ;;
    all)
        run morning_rush  20 20 60s
        run agent_mix     50 10 2m
        run sse_streaming 10 10 90s
        run overnight      3  1 3m
        ;;
    *)
        echo "Unknown scenario: $TARGET" >&2
        exit 2
        ;;
esac

echo "Done. Results in $RESULTS_DIR"
