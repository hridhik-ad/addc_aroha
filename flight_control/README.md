# flight_control — Mission & Precision Landing System

This module implements the complete autonomous mission for ADDC Aroha: GPS-guided navigation to the drop zone followed by vision-based precision landing using offboard velocity control.

> **Scope:** This directory currently contains the **HITL (Hardware-in-the-Loop) simulation** configuration. The real-world flight launch script is not yet uploaded — see [Missing Components](#missing-components).

---

## Architecture

The mission runs as two sequential phases, both driven from a single entry point:

```
missionMode.py
  │
  ├─ Phase 1: GPS Waypoint Navigation
  │    ├── Connect to FC via MAVLink (udpin://0.0.0.0:14550)
  │    ├── Fetch home GPS position + current heading
  │    ├── Calculate target coordinates from (LANDING_PAD_X, LANDING_PAD_Y) offset
  │    ├── Clear geofence, disable GF_ACTION
  │    ├── Upload MissionPlan → Arm → Start mission
  │    └── Monitor mission_progress until arrival at waypoint
  │
  └─ Phase 2: Precision Landing  (handoff to DroneController)
       ├── Subscribe to ZMQ detections from Hailo vision (port 5555)
       ├── Enter MAVSDK Offboard mode (20 Hz loop)
       ├── P-controller: normalised X/Y error → VelocityBodyYawspeed
       ├── Descend only when horizontal error < ALIGN_THRESHOLD (0.1)
       └── Issue land() when altitude < LANDING_ALTITUDE (0.3 m)
```

### Vision Dependency

`controller.py` consumes detection data published over ZMQ by one of two Hailo scripts:

| Script | Used For | Camera Source |
|--------|----------|---------------|
| `hailo-rpi5-examples/checking/direct_sitl.py` | Phase 2 — HITL simulation | Gazebo UDP H.264 stream (port 5000) |
| `hailo-rpi5-examples/checking/first_flight.py` | Phase 3 — Real-world flight | Physical RPi5 camera |

Both scripts publish identical ZMQ messages on `tcp://*:5555`. `controller.py` is fully agnostic to which one is running.

### `vision_module.py` — Phase 1 Only

This file is **not part of the RPi5 deployment**. It was used during Phase 1 (x86 PC, Gazebo SITL) and implements native OpenCV-based circle/arc detection on an RTP H.264 stream (UDP port 5600). It has been superseded by the Hailo-based detection pipeline and is kept for reference.

---

## HITL Launch

`launch.sh` orchestrates both processes for HITL simulation:

```bash
bash launch.sh
```

What it does:
1. Sources the Hailo environment (`setup_env.sh`) and starts `direct_sitl.py` **in the background**
2. Waits **5 seconds** for the Hailo pipeline and ZMQ publisher to initialise
3. Activates `flight_env` and starts `missionMode.py` **in the foreground**
4. On exit (Ctrl+C or completion), kills the entire process group via `kill -- -$$`

> ⚠️ **Hardcoded paths:** `launch.sh` currently hardcodes `/home/pi/aroha_addc/`. Update the `HAILO_DIR` and `FLIGHT_DIR` variables at the top of the script to match your installation path before running.

---

## Setup

### 1. Create the Python virtual environment

```bash
cd flight_control
python3 -m venv flight_env
source flight_env/bin/activate
pip install -r requirements.txt
```

### 2. Set up the Hailo vision subsystem

Follow the instructions in [`hailo-rpi5-examples/README.md`](../hailo-rpi5-examples/README.md):

```bash
cd ../hailo-rpi5-examples
./install.sh
source setup_env.sh
```

### 3. Configure mission parameters

Edit the constants at the top of `addc/missionMode.py`:

```python
LANDING_PAD_X = 0.5      # Metres North of takeoff point
LANDING_PAD_Y = 19.0     # Metres East of takeoff point
FLIGHT_ALTITUDE = 4.0    # Cruise altitude in metres AGL
CONNECTION_STRING = "udpin://0.0.0.0:14550"
```

---

## Controller Tuning Reference

All tuning constants are defined at the top of `addc/controller.py`:

| Constant | Value | Description |
|----------|-------|-------------|
| `KP_X` | `0.6` | Proportional gain — lateral (right) velocity |
| `KP_Y` | `0.6` | Proportional gain — forward velocity |
| `DIR_X` | `1.0` | Sign correction for X axis (flip to `-1.0` if drone drifts opposite direction) |
| `DIR_Y` | `-1.0` | Sign correction for Y axis |
| `MAX_SPEED_XY` | `0.8 m/s` | Hard cap on horizontal velocity commands |
| `DESCENT_SPEED_FAST` | `0.4 m/s` | Descent rate when altitude > 1.5 m and aligned |
| `DESCENT_SPEED_SLOW` | `0.15 m/s` | Descent rate when altitude ≤ 1.5 m and aligned |
| `ALIGN_THRESHOLD` | `0.1` | Max normalised error (sum of |x| + |y|) before descent is permitted |
| `LANDING_ALTITUDE` | `0.3 m` | Altitude that triggers `drone.action.land()` |

**ZMQ latency settings** (in `controller.py`):
- Subscriber socket uses `zmq.CONFLATE = 1` — always processes only the newest detection, discarding any backlog.

> **Note on FPS sensitivity:** These gains were tuned at ~30 FPS (Hailo-8L). At significantly lower FPS (e.g., 5 FPS on native RPi5 CPU), the effective loop latency increases and gains should be reduced to prevent oscillation.

---

## Missing Components

The following are not yet committed to this repository:

| Missing File | Description | Status |
|-------------|-------------|--------|
| Real-world launch script | Equivalent of `launch.sh` for physical flight (orchestrates `first_flight.py` + `flight_env`) | TODO: Upload |
| ONNX competition fallback | YOLOv8 exported to `.onnx`, run via `onnxruntime` on native RPi5 CPU — used at competition after Hailo-8L failure | TODO: Upload |

---

## Competition Post-Mortem

During HITL testing with RPi5 + Hailo-8L, the system achieved approximately **30 FPS** detection throughput, and the precision landing P-controller was tuned against this performance.

At the competition, the **Hailo-8L hardware failed**. Within 2 days, the team pivoted to running the YOLO model natively on the RPi5 CPU using ONNX Runtime with post-training quantization. This reduced inference throughput to approximately **5 FPS** — far below the controller's tuned operating point — causing the precision landing to perform poorly due to stale error signals driving inappropriate velocity commands.

**Key takeaways for future iterations:**

- Always maintain a tested ONNX/CPU fallback path with controller gains re-tuned specifically for lower FPS
- Use a timestamped ZMQ message and a **no-detection timeout** safety mode: if no fresh detection is received within N seconds, issue a zero-velocity command (hover) rather than continuing to act on stale data
- `zmq.CONFLATE` (currently used) handles queue buildup but does not handle the case where the publisher is simply slow — add a detection timestamp to the message and validate staleness on the subscriber side
- Consider splitting `KP_X`/`KP_Y` into separate forward/lateral gains; the landing pad geometry may benefit from asymmetric tuning

---

## File Reference

| File | Purpose |
|------|---------|
| `launch.sh` | HITL orchestrator — starts Hailo vision + drone controller |
| `addc/missionMode.py` | Mission entry point: GPS navigation → precision landing handoff |
| `addc/controller.py` | `DroneController` class: ZMQ subscriber + offboard P-controller |
| `addc/vision_module.py` | Phase 1 only: OpenCV arc detection over GStreamer RTP (not used on RPi5) |
| `test/zmq_detection.py` | Debug utility: prints raw ZMQ detection messages from the Hailo publisher |
| `requirements.txt` | Python dependencies for `flight_env` |
