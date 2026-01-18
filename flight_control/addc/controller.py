import asyncio
from mavsdk import System
from mavsdk.offboard import (OffboardError, VelocityBodyYawspeed)
from vision_module import VisionSystem

# --- TUNING PARAMETERS ---
KP_X = 0.8   
KP_Y = 0.8   
DESCENT_SPEED = 0.3 
LANDING_HEIGHT = 2.0 

class DroneController:
    # UPDATED: Accept the existing 'system' (drone) as an argument
    def __init__(self, drone_system):
        self.drone = drone_system  # Use the drone passed from missionMode
        self.vision = VisionSystem()

    async def run(self):
        # 1. Start Vision Thread
        self.vision.start()
        
        # 2. (REMOVED) Connection logic is no longer needed here 
        # because 'self.drone' is already connected and flying!

        # 3. SWITCH TO OFFBOARD & LAND
        print("Mission Reached. Handing over to Vision Controller...")
        await self.perform_precision_landing()

        # Cleanup
        self.vision.stop()

    async def perform_precision_landing(self):
        """
        Executes the visual servoing landing.
        """
        # Send a setpoint first (Required by MAVSDK before starting offboard)
        print("-- Setting initial setpoint")
        await self.drone.offboard.set_velocity_body(
            VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0))

        try:
            print("-- Starting Offboard Mode")
            await self.drone.offboard.start()
            print("-- Offboard Mode Active")
        except OffboardError as error:
            print(f"Offboard failed: {error}")
            return

        # The Landing Loop
        while True:
            # A. GET DATA
            detected, err_x, err_y = self.vision.get_target_data()
            
            # Get Altitude (Optimized to not block loop)
            # We use an async generator but only grab the next value
            async for position in self.drone.telemetry.position():
                altitude = position.relative_altitude_m
                break 

            # B. LANDING LOGIC
            if altitude < LANDING_HEIGHT:
                print(f"Altitude {altitude:.2f}m < {LANDING_HEIGHT}m. Engaging Standard Land.")
                try:
                    await self.drone.action.land()

                    await asyncio.sleep(3)
                    await self.drone.return_to_launch()  # Give some time for the command to register
                except Exception as e:
                    print(f"Landing trigger failed: {e}")
                break # Exit loop

            # C. VELOCITY CALCULATION (PID)
            vel_forward = 0.0
            vel_right = 0.0
            vel_down = 0.0

            if detected:
                # PID Control
                vel_right = err_x * KP_X
                vel_forward = -1 * err_y * KP_Y 
                vel_down = DESCENT_SPEED
                
                print(f"Target Found! Corr: X={vel_right:.2f} Y={vel_forward:.2f} Alt={altitude:.1f}")
            else:
                # Search Mode (Hover)
                print("Target Searching...")
                vel_down = 0.0 

            # D. SEND COMMANDS
            await self.drone.offboard.set_velocity_body(
                VelocityBodyYawspeed(vel_forward, vel_right, vel_down, 0.0))
            
            await asyncio.sleep(0.1) # 10Hz Update Rate