import asyncio
import zmq
import json
from mavsdk import System
from mavsdk.offboard import (OffboardError, VelocityBodyYawspeed)

# -----------------------------------------------------------------------------------------------
# CONFIGURATION
# -----------------------------------------------------------------------------------------------
ZMQ_IP = "127.0.0.1"
ZMQ_PORT = 5555

# --- TUNING GAINS ---
KP_X = 0.6   
KP_Y = 0.6   

# --- DIRECTION FIX (CONFIRMED WORKING) ---
DIR_X = 1.0 
DIR_Y = -1.0 

# --- LANDING SETTINGS ---
MAX_SPEED_XY = 0.8      # Max horizontal speed (m/s)
DESCENT_SPEED_FAST = 0.4 # Speed when high up (m/s)
DESCENT_SPEED_SLOW = 0.15 # Speed when close to target (m/s)
ALIGN_THRESHOLD = 0.1    # How close to center (0.0 - 1.0) before descending
LANDING_ALTITUDE = 0.3   # Height (meters) to cut motors/land
# -----------------------------------------------------------------------------------------------

class VisionSystem:
    def __init__(self):
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.SUB)
        # Latency Fix: Keep only the newest message
        self.socket.setsockopt(zmq.CONFLATE, 1)
        self.socket.connect(f"tcp://{ZMQ_IP}:{ZMQ_PORT}")
        self.socket.setsockopt_string(zmq.SUBSCRIBE, "")

    def get_latest_error(self):
        try:
            msg = self.socket.recv_json(flags=zmq.NOBLOCK)
            if msg and "detections" in msg:
                det = msg["detections"][0]["normalized_error"]
                return True, det["x"], det["y"]
        except zmq.Again:
            pass
        except Exception as e:
            print(f"ZMQ Error: {e}")
        return False, 0.0, 0.0

class DroneController:
    def __init__(self, drone):
        self.drone = drone
        self.vision = VisionSystem()
        self.current_altitude = 0.0 # Stores latest altitude

    async def update_altitude(self):
        """
        Background task to keep altitude updated without blocking the vision loop.
        """
        async for position in self.drone.telemetry.position():
            self.current_altitude = position.relative_altitude_m

    async def run(self):
        print("-- Connecting to Drone...")
        # Start the background altitude reader
        asyncio.create_task(self.update_altitude())
        
        print("-- Arming & Starting Offboard")
        # Initialize to 0 velocity before starting
        await self.drone.offboard.set_velocity_body(VelocityBodyYawspeed(0,0,0,0))
        
        try:
            await self.drone.offboard.start()
        except OffboardError as e:
            print(f"Offboard Start Failed: {e}")
            return

        print("-- Precision Landing Sequence Started --")

        while True:
            # 1. Get Fresh Vision Data
            found, err_x, err_y = self.vision.get_latest_error()
            
            # 2. Prepare Commands
            vel_fwd = 0.0
            vel_right = 0.0
            vel_down = 0.0
            
            if found:
                # --- HORIZONTAL LOGIC (Align) ---
                vel_right = (err_x * KP_X) * DIR_X
                vel_fwd   = (err_y * KP_Y) * DIR_Y 

                # Clamp Horizontal Speed
                vel_right = max(min(vel_right, MAX_SPEED_XY), -MAX_SPEED_XY)
                vel_fwd   = max(min(vel_fwd, MAX_SPEED_XY), -MAX_SPEED_XY)
                
                # --- VERTICAL LOGIC (Descend) ---
                # Calculate total distance from center
                total_error = abs(err_x) + abs(err_y)
                
                # Only descend if we are roughly centered
                if total_error < ALIGN_THRESHOLD:
                    if self.current_altitude > 1.5:
                        vel_down = DESCENT_SPEED_FAST # Go down faster if high up
                        status = "DESCENDING (FAST)"
                    else:
                        vel_down = DESCENT_SPEED_SLOW # Go slow near ground
                        status = "DESCENDING (PRECISION)"
                else:
                    # If not centered, stop descending and fix position
                    vel_down = 0.0 
                    status = "ALIGNING"

                # --- TOUCHDOWN LOGIC ---
                if self.current_altitude < LANDING_ALTITUDE:
                    print(f"!! Touchdown Detected ({self.current_altitude:.2f}m). Landing !!")
                    try:
                        await self.drone.action.land()
                    except Exception as e:
                        print(f"Land Command Failed: {e}")
                    break # Exit the loop, mission done.

                # Debug Print
                print(f"Alt: {self.current_altitude:.2f}m | Err: {total_error:.2f} | {status} -> V_down: {vel_down:.2f}")

            else:
                # Target Lost
                print("Target Lost! Hovering...")
                vel_fwd, vel_right, vel_down = 0.0, 0.0, 0.0

            # 3. Send Command
            await self.drone.offboard.set_velocity_body(
                VelocityBodyYawspeed(vel_fwd, vel_right, vel_down, 0.0)
            )

            await asyncio.sleep(0.05) # 20Hz Loop

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    drone = System()
    # loop.run_until_complete(drone.connect(system_address="udp://:14540"))
    controller = DroneController(drone)
    try:
        loop.run_until_complete(controller.run())
    except KeyboardInterrupt:
        print("Landing triggered by user...")
        loop.run_until_complete(drone.action.land())