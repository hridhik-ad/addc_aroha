#!/bin/bash

# ------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------

# Directories
HAILO_DIR="/home/pi/aroha_addc/hailo-rpi5-examples"
FLIGHT_DIR="/home/pi/aroha_addc/flight_control"

# Activation Scripts
FLIGHT_VENV="$FLIGHT_DIR/flight_env/bin/activate"
HAILO_ENV_SCRIPT="./setup_env.sh" # We will run this relative to HAILO_DIR

# Python Scripts
HAILO_SCRIPT="checking/direct_sitl.py" # Relative to HAILO_DIR
DRONE_SCRIPT="$FLIGHT_DIR/addc/missionMode.py"

# ------------------------------------------------------------------

cleanup() {
    echo ""
    echo "=========================================="
    echo "[LAUNCHER] Shutting down all systems..."
    
    # CRITICAL FIX: Disable the trap so we don't loop forever
    trap - SIGINT SIGTERM EXIT
    
    # Kill the specific background process group
    kill -- -$$ 
}

# Trap the signals
trap cleanup SIGINT SIGTERM EXIT

echo "=========================================="
echo "[LAUNCHER] INITIALIZING MISSION SYSTEMS"
echo "=========================================="

# -------------------------------------------------------
# 1. Start Hailo Vision System (background)
# -------------------------------------------------------
echo "[1/2] Starting Hailo Vision System..."

# Subshell '()' creates a temporary environment. 
# We CD inside it so it doesn't affect the rest of the script.
(
    echo "[HAILO] Changing directory to: $HAILO_DIR"
    cd "$HAILO_DIR" || { echo "Failed to find Hailo directory"; exit 1; }

    echo "[HAILO] Activating Hailo environment..."
    source "$HAILO_ENV_SCRIPT"

    # Confirm we are using the correct python
    echo "[HAILO] Python Path: $(which python)"
    
    # Run the script
    python "$HAILO_SCRIPT"
) &

HAILO_PID=$!

echo "      Waiting 5s for camera warmup..."
sleep 5

# -------------------------------------------------------
# 2. Start Drone Controller (foreground)
# -------------------------------------------------------
echo "[2/2] Starting Drone Controller..."
echo "=========================================="

(
    # Optional: CD to flight dir if your drone script uses relative paths
    cd "$FLIGHT_DIR" || { echo "Failed to find Flight directory"; exit 1; }

    echo "[DRONE] Activating Flight Control environment..."
    source "$FLIGHT_VENV"

    echo "[DRONE] Python Path: $(which python)"
    
    # Run the script
    python "$DRONE_SCRIPT"
)

# Wait is strictly not needed here as the foreground process holds the script,
# but good for safety if you change the logic later.
wait