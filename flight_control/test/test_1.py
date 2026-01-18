import asyncio
import zmq
from mavsdk import System
from mavsdk.offboard import VelocityBodyYawspeed, PositionNedYaw

async def run():
    # 1. Init ZMQ Subscriber (Listening to Hailo Venv)
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    # Assuming Hailo venv publishes on port 5555
    socket.connect("tcp://127.0.0.1:5555") 
    socket.subscribe("") # Subscribe to all topics
    print("[INFO] ZMQ Listener initialized. Waiting for Hailo data...")

    # 2. Init MAVSDK
    drone = System()
    # Connect to the drone (usually serial on Pi, e.g., /dev/ttyAMA0 or UDP if sim)
    # await drone.connect(system_address="serial:///dev/ttyAMA0:57600")
    print("[INFO] MAVSDK initialized (Simulated connection).")

    # 3. Simple Loop Example
    # In a real mission, you'd read ZMQ data -> calculate velocity -> send to drone
    print("[INFO] Dependencies are working correctly.")

if __name__ == "__main__":
    asyncio.run(run())