import os
import gi
import json
import zmq
from pathlib import Path

gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import hailo
from hailo_apps.hailo_app_python.core.gstreamer.gstreamer_app import app_callback_class
from hailo_apps.hailo_app_python.apps.detection_simple.detection_pipeline_simple import GStreamerDetectionApp

# -----------------------------------------------------------------------------------------------
# CONFIGURATION
# -----------------------------------------------------------------------------------------------
CAM_DEVICE = "/dev/video0"
CAM_WIDTH = 640
CAM_HEIGHT = 480
RECORD_PATH = "/home/pi/flight_record.mkv"
HEF_PATH = "/home/pi/aroha_addc/hailo-rpi5-examples/custom_hef/qr_simulation.hef"
POST_PROCESS_SO = "/usr/local/hailo/resources/so/libyolo_hailortpp_postprocess.so"
ZMQ_PORT = 5555
# -----------------------------------------------------------------------------------------------

class user_app_callback_class(app_callback_class):
    def __init__(self):
        super().__init__()
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PUB)
        self.socket.setsockopt(zmq.SNDHWM, 1) # Internal ZMQ buffer limit
        self.socket.bind(f"tcp://*:{ZMQ_PORT}")
        print(f"[Hailo] ZMQ Publisher bound to port {ZMQ_PORT}")

def app_callback(pad, info, user_data):
    user_data.increment()
    buffer = info.get_buffer()
    if buffer is None:
        return Gst.PadProbeReturn.OK
    
    detections = hailo.get_roi_from_buffer(buffer).get_objects_typed(hailo.HAILO_DETECTION)
    valid_detections = []
    
    for detection in detections:
        if detection.get_confidence() > 0.50: 
            bbox = detection.get_bbox()
            norm_center_x = (bbox.xmin() + bbox.xmax()) / 2.0
            norm_center_y = (bbox.ymin() + bbox.ymax()) / 2.0

            error_x = (norm_center_x - 0.5) * 2
            error_y = (norm_center_y - 0.5) * 2

            obj_data = {
                "label": detection.get_label(),
                "normalized_error": {
                    "x": float(f"{error_x:.4f}"), 
                    "y": float(f"{error_y:.4f}")
                }
            }
            valid_detections.append(obj_data)
    
    if len(valid_detections) > 0:
        json_output = {"detections": valid_detections}
        try:
            user_data.socket.send_json(json_output, flags=zmq.NOBLOCK)
        except zmq.Again:
            pass 
        
    return Gst.PadProbeReturn.OK

class GStreamerUSBRecorderApp(GStreamerDetectionApp):
    def __init__(self, callback, user_data):
        super().__init__(callback, user_data)
        
    def get_pipeline_string(self):
        # ---------------------------------------------------------
        # ROBUST RECORDING PIPELINE (Fixes Black Screen)
        # ---------------------------------------------------------
        pipeline = (
            # 1. SOURCE: USB Webcam (640x480)
            f"v4l2src device={CAM_DEVICE} io-mode=2 ! "
            f"video/x-raw, width={CAM_WIDTH}, height={CAM_HEIGHT}, framerate=30/1 ! "
            
            # 2. DROP QUEUE (Force Latest Frame)
            f"queue name=src_q leaky=downstream max-size-buffers=1 ! "
            
            # 3. SCALE & CONVERT (RGB for Hailo)
            f"videoscale ! "
            f"videoconvert ! "
            f"video/x-raw, format=RGB, width=640, height=640, pixel-aspect-ratio=1/1 ! "
            
            # 4. INFERENCE
            f"hailonet hef-path={HEF_PATH} ! "
            f"hailofilter so-path={POST_PROCESS_SO} qos=false ! "
            
            # 5. CONTROL POINT
            f"identity name=identity_callback ! " 
            f"hailooverlay ! " 
            
            # 6. RECORDING QUEUE
            f"queue name=rec_q max-size-time=0 max-size-bytes=0 max-size-buffers=0 ! "
            
            # 7. COLOR CONVERSION (Fixes Black Screen Part 1)
            # x264enc needs I420 (YUV), not RGB. We must convert it here.
            f"videoconvert ! "
            f"video/x-raw, format=I420 ! "
            
            # 8. ENCODING
            f"x264enc tune=zerolatency speed-preset=superfast bitrate=2500 ! "
            
            # 9. PARSING (Fixes Black Screen Part 2)
            # Critical: Organizing the H.264 stream so .mkv understands it
            f"h264parse ! "
            
            # 10. CONTAINER
            f"matroskamux ! "
            f"filesink location={RECORD_PATH}"
        )
        return pipeline

if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent.parent
    env_file = project_root / ".env"
    os.environ["HAILO_ENV_FILE"] = str(env_file)
    
    print("[Hailo] Starting Pipeline (Low Latency Mode)...")
    user_data = user_app_callback_class()
    app = GStreamerUSBRecorderApp(app_callback, user_data)
    app.run()