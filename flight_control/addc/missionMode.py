import asyncio
import math
from mavsdk import System
from mavsdk.mission import (MissionItem, MissionPlan)
from controller import DroneController  

# --- Configuration ---
LANDING_PAD_X = 0.5  # Meters North (x)
LANDING_PAD_Y = 19.0   # Meters East (y)
FLIGHT_ALTITUDE = 4.0 # Meters
CONNECTION_STRING = "udpin://0.0.0.0:14540"

async def run():
    drone = System()
    print("-- Connecting to drone...")
    await drone.connect(system_address=CONNECTION_STRING)

    print("-- Waiting for drone to connect...")
    async for state in drone.core.connection_state():
        if state.is_connected:
            print(f"-- Connected to drone!")
            break

    print("-- Waiting for global position (GPS lock)...")
    async for health in drone.telemetry.health():
        if health.is_global_position_ok and health.is_home_position_ok:
            print("-- Global position state is good.")
            break

    # 1. GET HOME POSITION AND HEADING
    print("-- Fetching home position...")
    home_lat = 0.0
    home_lon = 0.0
    current_heading = 0.0

    # We need to grab the heading (yaw) so we can tell the drone 
    # "Keep facing this way" instead of twisting.
    async for telemetry in drone.telemetry.heading():
        current_heading = telemetry.heading_deg
        print(f"   Current Heading: {current_heading} degrees")
        break
        
    async for terrain_info in drone.telemetry.home():
        home_lat = terrain_info.latitude_deg
        home_lon = terrain_info.longitude_deg
        print(f"   Home Coordinates: {home_lat}, {home_lon}")
        break

    # 2. CLEAR GEOFENCE
    print("-- Clearing existing Geofence...")
    await drone.geofence.clear_geofence()

    # 3. DISABLE GEOFENCE ACTION
    print("-- Disabling Geofence Action...")
    await drone.param.set_param_int("GF_ACTION", 0)

    # 4. CALCULATE TARGET
    target_lat, target_lon = get_location_metres(home_lat, home_lon, LANDING_PAD_X, LANDING_PAD_Y)
    print(f"   Target Coordinates: {target_lat}, {target_lon}")

    # 5. CREATE MISSION PLAN
    mission_items = []

    # Waypoint 1: Fly to Target
    # STABILIZATION FIX: Instead of float('nan') for yaw_deg, we use 'current_heading'.
    # This tells the drone: "Fly to the point, but keep looking exactly where you are looking now."
    mission_items.append(MissionItem(
        target_lat,
        target_lon,
        FLIGHT_ALTITUDE,
        5.0,               # Reduced speed to 5m/s for smoother start
        True,
        float('nan'),
        float('nan'),
        MissionItem.CameraAction.NONE,
        float('nan'),
        float('nan'),
        float('nan'),
        current_heading,   # <--- FIXED: Lock heading to current value
        float('nan'),
        MissionItem.VehicleAction.NONE
    ))

   
    
    print("-- Uploading mission...")
    mission_plan = MissionPlan(mission_items)
    await drone.mission.set_return_to_launch_after_mission(False) 
    await drone.mission.upload_mission(mission_plan)

    print("-- Arming...")
    await drone.action.arm()
# ... (Previous imports and setup code remains the same) ...

    print("-- Starting mission...")
    await drone.mission.start_mission()
    
    # Wait for mission progress
    async for mission_progress in drone.mission.mission_progress():
        print(f"   Mission progress: {mission_progress.current}/{mission_progress.total}")
        if mission_progress.current == mission_progress.total:
            print("Reached the coordinates")
            break

    # --- HANDOVER TO CONTROLLER ---
    print("-- Mission Complete. Initializing Precision Landing...")
    
    # UPDATED: Pass the 'drone' object we are already using!
    controller = DroneController(drone) 
    await controller.run()

# ... (Rest of file remains the same) ...

def get_location_metres(original_lat, original_lon, dNorth, dEast):
    earth_radius = 6378137.0 
    dLat = dNorth / earth_radius
    dLon = dEast / (earth_radius * math.cos(math.pi * original_lat / 180))
    newlat = original_lat + (dLat * 180/math.pi)
    newlon = original_lon + (dLon * 180/math.pi)
    return newlat, newlon

if __name__ == "__main__":
    asyncio.run(run())