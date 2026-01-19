import os
import gi
import json
import zmq  # Import ZMQ
from pathlib import Path

gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import hailo
from hailo_apps.hailo_app_python.core.gstreamer.gstreamer_app import app_callback_class
from hailo_apps.hailo_app_python.apps.detection_simple.detection_pipeline_simple import GStreamerDetectionApp

# -----------------------------------------------------------------------------------------------
# CONFIGURATION
# -----------------------------------------------------------------------------------------------
HOST_IP = "10.42.0.1"
HEF_PATH = "/home/pi/aroha_addc/hailo-rpi5-examples/custom_hef/qr_simulation.hef"
POST_PROCESS_SO = "/usr/local/hailo/resources/so/libyolo_hailortpp_postprocess.so"

# ZMQ Configuration
ZMQ_PORT = 5555  # Safe port (doesn't clash with 5000/5001)
# -----------------------------------------------------------------------------------------------

class user_app_callback_class(app_callback_class):
    def __init__(self):
        super().__init__()
        # Initialize ZMQ Context and Publisher Socket
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PUB)
        # Bind to all interfaces so other venvs/machines can listen
        self.socket.bind(f"tcp://*:{ZMQ_PORT}")
        print(f"ZMQ Publisher started on port {ZMQ_PORT}")

def app_callback(pad, info, user_data):
    user_data.increment()
    buffer = info.get_buffer()
    if buffer is None:
        return Gst.PadProbeReturn.OK
    
    detections = hailo.get_roi_from_buffer(buffer).get_objects_typed(hailo.HAILO_DETECTION)
    frame_data = []
    
    for detection in detections:
        confidence_pct = detection.get_confidence() * 100
        obj_data = {
            "label": detection.get_label(),
            "confidence": f"{confidence_pct:.2f}%",
            "bbox": {
                "xmin": detection.get_bbox().xmin(),
                "ymin": detection.get_bbox().ymin(),
                "xmax": detection.get_bbox().xmax(),
                "ymax": detection.get_bbox().ymax()
            }
        }
        frame_data.append(obj_data)
    
    # Send via ZMQ instead of printing
    if len(frame_data) > 0:
        json_output = {
            "frame_id": user_data.get_count(),
            "detections": frame_data
        }
        try:
            # We send the dictionary directly as a JSON object
            user_data.socket.send_json(json_output)
        except Exception as e:
            # Prevent ZMQ errors from crashing the video pipeline
            print(f"ZMQ Send Error: {e}")
        
    return Gst.PadProbeReturn.OK

class GStreamerUDPHailoApp(GStreamerDetectionApp):
    def __init__(self, callback, user_data):
        super().__init__(callback, user_data)
        
    def get_pipeline_string(self):
        pipeline = (
            f"udpsrc port=5000 buffer-size=0 ! "
            f"application/x-rtp, media=(string)video, clock-rate=(int)90000, encoding-name=(string)H264, payload=(int)96 ! "
            f"rtph264depay ! h264parse ! avdec_h264 ! "
            f"queue leaky=no max-size-buffers=3 ! " 
            f"videoscale ! videoconvert ! video/x-raw, format=RGB, pixel-aspect-ratio=1/1 ! "
            f"hailonet hef-path={HEF_PATH} ! "
            f"hailofilter so-path={POST_PROCESS_SO} qos=false ! "
            f"identity name=identity_callback ! " 
            f"hailooverlay ! "
            f"videoconvert ! x264enc tune=zerolatency speed-preset=ultrafast ! "
            f"rtph264pay ! udpsink host={HOST_IP} port=5001 sync=false"
        )
        return pipeline

if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent.parent
    env_file = project_root / ".env"
    os.environ["HAILO_ENV_FILE"] = str(env_file)
    
    user_data = user_app_callback_class()
    app = GStreamerUDPHailoApp(app_callback, user_data)
    app.run()