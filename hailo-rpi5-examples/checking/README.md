# checking/ — Aroha Custom Hailo Detection Scripts

This directory contains the Aroha-specific detection scripts that run on the **Raspberry Pi 5 with Hailo-8L** and bridge the AI vision pipeline to the flight controller via ZMQ.

These scripts are distinct from the stock Hailo examples in `basic_pipelines/`.

---

## Scripts Overview

| Script | Phase | Camera Input | Deployment Target |
|--------|-------|-------------|-------------------|
| `vision_module.py` *(in `flight_control/addc/`)* | Phase 1 — Initial Testing | Gazebo UDP RTP H.264 (port 5600) | x86 PC (not RPi5) |
| [`direct_sitl.py`](#direct_sitlpy--phase-2-hitl-simulation) | Phase 2 — HITL Simulation | Gazebo UDP RTP H.264 (port 5000) | RPi5 + Hailo-8L |
| [`first_flight.py`](#first_flightpy--phase-3-real-world-flight) | Phase 3 — Real-World Flight | Physical RPi5 / USB camera | RPi5 + Hailo-8L |

> **Note:** `vision_module.py` is located in `flight_control/addc/` and is documented in [`flight_control/README.md`](../../flight_control/README.md). It is listed here for completeness as the Phase 1 predecessor to both scripts below.

---

## `direct_sitl.py` — Phase 2: HITL Simulation

Receives a **H.264 RTP stream from Gazebo** (simulated drone camera on UDP port 5000), runs inference using the custom `qr_simulation.hef` YOLO model on the Hailo-8L, and publishes detection results over ZMQ for `controller.py` to consume.

### Pipeline

```
Gazebo camera → UDP:5000 (H.264 RTP)
  → GStreamer: rtph264depay → avdec_h264 → videoscale → 640×640 RGB
  → hailonet  (qr_simulation.hef on Hailo-8L)
  → hailofilter (YOLO post-process .so)
  → app_callback  →  ZMQ PUB tcp://*:5555
  → re-encode (x264enc zerolatency) → UDP:5001 → HOST_IP  (annotated preview)
```

### Key Configuration

```python
HOST_IP   = "10.42.0.1"           # Destination for annotated preview re-stream
HEF_PATH  = ".../custom_hef/qr_simulation.hef"
ZMQ_PORT  = 5555
FRAME_WIDTH  = 640
FRAME_HEIGHT = 640
```

### Latency Optimisations

| Location | Setting | Effect |
|----------|---------|--------|
| GStreamer queue | `leaky=downstream max-size-buffers=1` | Drops backed-up frames immediately, preventing pipeline stall |
| ZMQ publisher | `SNDHWM=1` | Drops outgoing messages if the subscriber is slow |
| ZMQ subscriber (`controller.py`) | `CONFLATE=1` | Always reads only the newest message, discards backlog |

---

## `first_flight.py` — Phase 3: Real-World Flight

Replaces `direct_sitl.py` for physical deployment. Uses the onboard RPi5 camera (USB or CSI) as input instead of a Gazebo UDP stream. Runs the same `qr_simulation.hef` model on the Hailo-8L and publishes **identical ZMQ messages** to `controller.py`.

This script also records the camera feed to disk for post-flight review.

> **Note:** The corresponding real-world launch script (equivalent to `flight_control/launch.sh` but using `first_flight.py`) has not yet been committed to this repository.

---

## ZMQ Message Schema

Both `direct_sitl.py` and `first_flight.py` publish to `tcp://*:5555` using this JSON structure:

```json
{
  "detections": [
    {
      "normalized_error": {
        "x": 0.1234,
        "y": -0.0567
      }
    }
  ]
}
```

- `x` and `y` are normalised to `[-1.0, 1.0]`, derived from the bounding box centre:
  ```
  error_x = (bbox_center_x - 0.5) * 2
  error_y = (bbox_center_y - 0.5) * 2
  ```
  A value of `0.0` means the target is centred on that axis. The precision landing controller drives both values toward zero.

- Only detections with **confidence > 75%** are published. This threshold was lowered from a higher value to reduce detection flicker during the approach.
- If multiple detections exist, `controller.py` uses `detections[0]`.

---

## Custom Model: `qr_simulation.hef`

| Property | Details |
|----------|---------|
| **Architecture** | YOLOv8 |
| **Target** | QR codes / landing pad markers |
| **Training** | Custom dataset → exported to ONNX → compiled to `.hef` for Hailo-8L |
| **Input size** | 640 × 640 RGB |
| **Location** | `hailo-rpi5-examples/custom_hef/qr_simulation.hef` |
| **Throughput** | ~30 FPS on Hailo-8L (HITL tested) |

---

## Running

### As part of HITL simulation (via `launch.sh`)

```bash
cd /path/to/addc_aroha/flight_control
bash launch.sh
```

### Vision pipeline in isolation

```bash
cd hailo-rpi5-examples
source setup_env.sh
python checking/direct_sitl.py
```

### Verify ZMQ detections are publishing

```bash
source flight_control/flight_env/bin/activate
python flight_control/test/zmq_detection.py
```
