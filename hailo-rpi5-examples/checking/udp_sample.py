import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import os
import setproctitle
import cv2
import numpy as np
from pathlib import Path

# Import Hailo Infrastructure
from hailo_apps.hailo_app_python.core.gstreamer.gstreamer_app import app_callback_class
from hailo_apps.hailo_app_python.apps.detection_simple.detection_pipeline_simple import GStreamerDetectionApp

# -----------------------------------------------------------------------------------------------
# 1. Custom Class to Override the Pipeline
# -----------------------------------------------------------------------------------------------
class UDPDetectionApp(GStreamerDetectionApp):
    def __init__(self, app_callback, user_data):
        # --- CRITICAL FIX: DEFINE VARIABLES BEFORE super().__init__ ---
        # Since .env is missing, we must hardcode all these values
        # so the pipeline builder finds them immediately.
        
        self.network_width = 640
        self.network_height = 640
        self.batch_size = 1
        self.hef_path = "/home/pi/aroha_addc/hailo-rpi5-examples/custom_hef/qr_simulation.hef"
        self.default_postprocess_so = "/usr/local/hailo/resources/so/libyolo_hailortpp_postprocess.so"
        
        # Standard Hailo thresholds configuration
        self.thresholds_str = "nms-score-threshold=0.3 nms-iou-threshold=0.45 output-format-type=HAILO_FORMAT_TYPE_FLOAT32"
        
        # Leave empty if you don't have a specific labels JSON; the SO file handles basic classes
        self.labels_config = "" 

        # --- NOW CALL PARENT ---
        # The parent will immediately call get_pipeline_string(), 
        # but now the variables above exist, so it won't crash.
        super().__init__(app_callback, user_data)

    def get_pipeline_string(self):
        # Your custom UDP Source Pipeline
        source_element = (
            # buffer-size=0: Don't let the OS buffer network packets
            "udpsrc port=5600 buffer-size=0 caps=\"application/x-rtp, media=video, clock-rate=90000, encoding-name=H264, payload=96\" ! "
            # CRITICAL: This queue drops any frame older than the newest one
            "queue max-size-buffers=1 leaky=downstream ! "
            "rtph264depay ! "
            "h264parse ! "
            "avdec_h264 ! "
            "videoconvert ! "
            "videoscale ! "
            f"video/x-raw, format=RGB, width={self.network_width}, height={self.network_height}, pixel-aspect-ratio=1/1 ! "
        )

        pipeline_string = (
            f"hailomuxer name=hmux "
            f"{source_element} "
            f"tee name=t ! "
            # Reduce max-size-buffers from 20 to 3 to prevent display lag
            f"queue name=bypass_q max-size-buffers=3 leaky=no ! "
            f"hmux.sink_0 "
            f"t. ! "
            f"queue name=inference_input_q ! "
            f"videoconvert n-threads=2 ! "
            f"hailonet hef-path={self.hef_path} batch-size={self.batch_size} {self.thresholds_str} force-writable=true ! "
            f"queue name=inference_output_q ! "
            f"hailofilter so-path={self.default_postprocess_so} {self.labels_config} qos=false ! "
            f"queue name=mux_input_q ! "
            f"hmux.sink_1 "
            f"hmux. ! "
            f"queue name=hailo_python_q ! "
            f"queue name=user_callback_q ! "
            f"identity name=identity_callback ! "
            f"queue name=overlay_q ! "
            f"hailooverlay ! "
            f"queue name=display_q ! "
            f"videoconvert ! "
            f"fpsdisplaysink video-sink=autovideosink name=hailo_display sync=false text-overlay=true"
        )
        print(f"DEBUG: Pipeline created with resolution {self.network_width}x{self.network_height}")
        return pipeline_string
        
# -----------------------------------------------------------------------------------------------
# 2. User Callback
# -----------------------------------------------------------------------------------------------
class UserCallback(app_callback_class):
    def __init__(self):
        super().__init__()
        self.frame_count = 0

def app_callback(pad, info, user_data):
    import hailo
    buffer = info.get_buffer()
    if buffer is None:
        return Gst.PadProbeReturn.OK

    roi = hailo.get_roi_from_buffer(buffer)
    detections = roi.get_objects_typed(hailo.HAILO_DETECTION)
    
    detection_str = ""
    if len(detections) > 0:
        for detection in detections:
            label = detection.get_label()
            confidence = detection.get_confidence()
            if confidence > 0.50:
                detection_str += f"[{label} {confidence:.1f}] "
        if detection_str:
            print(f"Target Found: {detection_str}")

    return Gst.PadProbeReturn.OK

# -----------------------------------------------------------------------------------------------
# 3. Main Execution
# -----------------------------------------------------------------------------------------------
if __name__ == "__main__":
    project_root = Path(__file__).parent.resolve()
    
    # We can try to set this, but since the file is missing, 
    # the hardcoded values in __init__ will save us.
    os.environ["HAILO_ENV_FILE"] = str(project_root / ".env") 
    
    user_data = UserCallback()
    app = UDPDetectionApp(app_callback, user_data)
    app.run()