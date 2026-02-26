# ADDC Aroha — Autonomous Precision Landing Drone

ADDC Aroha is a high-performance autonomous drone system developed for the **ADDC (Autonomous Drone Delivery Challenge)** competition. The system autonomously navigates to a target area via GPS, detects a landing marker using a custom-trained YOLOv8 model, and executes a **vision-based precision landing** using normalised X/Y error feedback.

## Hardware Stack

| Component | Details |
|-----------|---------|
| **Flight Controller** | Cube Orange (ArduPilot / PX4 firmware) |
| **Companion Computer** | Raspberry Pi 5 |
| **AI Accelerator** | Hailo-8L (13 TOPS) |
| **AI Model** | Custom YOLOv8, trained on QR/landing markers, compiled to `.hef` |
| **MAVLink Link** | UDP `0.0.0.0:14550` (FC ↔ RPi5) |

## Development Phases

| Phase | Environment | Vision Script | Inference Backend |
|-------|------------|--------------|-------------------|
| **Phase 1** — Initial Testing | x86 PC + Gazebo SITL | `vision_module.py` (OpenCV arc detection) | Native x86 CPU |
| **Phase 2** — HITL Simulation | RPi5 + Hailo-8L + Gazebo | `direct_sitl.py` | Hailo-8L NPU ~30 FPS |
| **Phase 3** — Real-World Flight | RPi5 + Hailo-8L + Physical camera | `first_flight.py` | Hailo-8L NPU |

> ⚠️ **Work In Progress:** The real-world flight launch script and the ONNX competition fallback model are not yet committed to this repository. See [`flight_control/README.md`](flight_control/README.md#missing-components) for context.

## Repository Structure

```
addc_aroha/
├── flight_control/                  # 🚁 Mission logic & precision landing (MAVSDK + Python)
│   ├── README.md                    # ← Full setup, architecture, tuning guide
│   ├── launch.sh                    # HITL orchestrator (Hailo vision + drone controller)
│   ├── requirements.txt             # Python dependencies for flight_env
│   └── addc/
│       ├── missionMode.py           # Entry point: GPS mission → handoff to controller
│       ├── controller.py            # Offboard precision landing (20 Hz P-controller)
│       └── vision_module.py         # Phase 1 only: OpenCV circle detection (x86, not RPi5)
│
└── hailo-rpi5-examples/             # 🤖 AI vision subsystem (RPi5 + Hailo-8L)
    ├── README.md                    # Hailo setup, pipelines, community projects
    ├── custom_hef/
    │   └── qr_simulation.hef        # YOLOv8 compiled for Hailo-8L
    └── checking/                    # Aroha-specific Hailo detection scripts
        ├── README.md                # ← Per-script context and ZMQ schema
        ├── direct_sitl.py           # Phase 2: Gazebo UDP input → Hailo → ZMQ
        └── first_flight.py          # Phase 3: Physical RPi5 camera → Hailo → ZMQ
```

## System Data Flow

```
[Gazebo Camera (sim) / Physical Camera (real-world)]
            │  H.264 RTP over UDP
            ▼
┌───────────────────────────────────────┐
│  direct_sitl.py  /  first_flight.py   │  RPi5 + Hailo-8L
│  YOLOv8 → qr_simulation.hef           │  ~30 FPS (HITL)
│  confidence > 75% → norm X/Y error   │
└──────────────────┬────────────────────┘
                   │  ZMQ PUB  tcp://*:5555
                   ▼
┌───────────────────────────────────────┐
│  controller.py   (P-controller)       │  RPi5
│  error → VelocityBodyYawspeed         │  20 Hz offboard loop
└──────────────────┬────────────────────┘
                   │  MAVSDK offboard commands
                   ▼
          [Cube Orange FC]  ←── MAVLink UDP:14550
```

## Quick Start (HITL Simulation)

```bash
cd flight_control
bash launch.sh
```

See [`flight_control/README.md`](flight_control/README.md) for full prerequisites and setup.

## License

MIT
