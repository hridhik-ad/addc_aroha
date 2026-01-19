import sys
import cv2
import numpy as np
import threading

# --- IMPORT GAZEBO LIBRARIES ---
# If these fail, you may need to install: sudo apt-get install python3-gz-transport12 python3-gz-msgs9
try:
    from gz.transport12 import Node
    from gz.msgs9.image_pb2 import Image
except ImportError:
    # Fallback for newer Harmonic/Garden versions
    try:
        from gz.transport13 import Node
        from gz.msgs10.image_pb2 import Image
    except ImportError:
        print("CRITICAL ERROR: Could not import Gazebo Python bindings.")
        print("Please run: sudo apt-get install python3-gz-transport* python3-gz-msgs*")
        sys.exit(1)

# --- CONFIGURATION ---
# The exact topic you found in 'gz topic -l'
INPUT_TOPIC = "/world/mission/model/x500_mono_cam_down_0/link/camera_link/sensor/imager/image"
UDP_IP = "127.0.0.1"
UDP_PORT = 5600

# --- GSTREAMER PIPELINE ---
# We use 'appsrc' to push OpenCV frames into a GStreamer pipeline
# Then we encode to H.264 and blast it over UDP
gst_out = (
    "appsrc ! "
    "videoconvert ! "
    "video/x-raw, format=I420 ! "
    "x264enc tune=zerolatency bitrate=2000 speed-preset=ultrafast ! "
    "rtph264pay config-interval=1 pt=96 ! "
    f"udpsink host={UDP_IP} port={UDP_PORT} sync=false"
)

writer = None

def cb(msg):
    global writer
    
    # 1. Parse Dimensions
    width = msg.width
    height = msg.height
    
    # 2. Convert Raw Bytes to NumPy
    # Gazebo images are typically RGB8
    try:
        # Create numpy array from the byte buffer
        # Note: If pixel_format is not RGB, this might need tweaking
        img = np.frombuffer(msg.data, dtype=np.uint8).reshape((height, width, 3))
    except Exception as e:
        print(f"Frame Error: {e}")
        return

    # 3. Convert RGB -> BGR (OpenCV standard)
    frame = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    # 4. Initialize the UDP Streamer (only once)
    if writer is None:
        print(f"[Bridge] Connected to Camera: {width}x{height}")
        print(f"[Bridge] Streaming to udp://{UDP_IP}:{UDP_PORT}")
        # 30 FPS is standard
        writer = cv2.VideoWriter(gst_out, cv2.CAP_GSTREAMER, 0, 30, (width, height))
    
    # 5. Push Frame to Stream
    if writer.isOpened():
        writer.write(frame)
        
    # Optional: Preview to prove it works
    cv2.imshow("Gazebo Camera Bridge", frame)
    cv2.waitKey(1)

def main():
    node = Node()
    print(f"[Bridge] Subscribing to: {INPUT_TOPIC}")
    print("[Bridge] Waiting for drone video feed...")
    
    if not node.subscribe(Image, INPUT_TOPIC, cb):
        print("Error: Could not subscribe! Check if simulation is running.")
        return

    # Keep script alive to process callbacks
    try:
        while True:
            pass
    except KeyboardInterrupt:
        print("\n[Bridge] Stopping...")

if __name__ == "__main__":
    main()