import cv2
import threading
import numpy as np
import time

class VisionSystem:
    def __init__(self):
        self.target_detected = False
        self.err_x = 0.0 
        self.err_y = 0.0 
        self.running = False
        self._thread = None
        self._lock = threading.Lock()

        self.pipeline = (
            "udpsrc port=5600 buffer-size=0 ! "
            "application/x-rtp, payload=96 ! "
            "rtph264depay ! h264parse config-interval=1 ! "
            "avdec_h264 ! videoconvert ! "
            "video/x-raw, format=BGR ! "
            "appsink drop=1 sync=false"
        )

    def start(self):
        if self.running: return
        self.running = True
        self._thread = threading.Thread(target=self._update_loop)
        self._thread.daemon = True
        self._thread.start()
        print("[Vision] Thread Started.")

    def stop(self):
        self.running = False
        if self._thread: self._thread.join()
        print("[Vision] Thread Stopped.")

    def get_target_data(self):
        with self._lock:
            return self.target_detected, self.err_x, self.err_y

    def _update_loop(self):
        cap = cv2.VideoCapture(self.pipeline, cv2.CAP_GSTREAMER)
        if not cap.isOpened():
            self.running = False
            return

        while self.running:
            ret, frame = cap.read()
            if not ret: continue

            # --- PRE-PROCESSING ---
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            # Slightly stronger blur to smooth out pixelated arcs
            blur = cv2.GaussianBlur(gray, (9, 9), 2) 
            edges = cv2.Canny(blur, 40, 100)
            
            # Dilate to connect broken arc segments
            kernel = np.ones((3,3), np.uint8)
            edges = cv2.dilate(edges, kernel, iterations=1)
            
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            
            detected = False
            curr_err_x = 0.0
            curr_err_y = 0.0
            
            h, w = frame.shape[:2]
            center_x, center_y = w // 2, h // 2

            # Sort by Arc Length (prefer longer curves)
            contours = sorted(contours, key=lambda x: cv2.arcLength(x, False), reverse=True)

            for cnt in contours:
                # 1. Filter tiny noise (too small to judge curvature)
                if cv2.arcLength(cnt, False) < 50:
                    continue

                # 2. Fit the "Theoretical" Circle
                # minEnclosingCircle works even on partial arcs
                (mx, my), radius = cv2.minEnclosingCircle(cnt)
                
                # Sanity check: Radius shouldn't be impossibly huge (e.g., fitting a straight line)
                if radius > w * 2 or radius < 10:
                    continue

                # 3. RADIAL CONSISTENCY CHECK (The Logic Fix)
                # We calculate how well the points actually fit that circle.
                
                # Get all points in the contour
                pts = cnt.squeeze() # Shape (N, 2)
                if pts.ndim < 2: continue # Handle edge case of single point
                
                # Calculate distance of every point from the center (mx, my)
                # formula: sqrt((x-mx)^2 + (y-my)^2)
                distances = np.linalg.norm(pts - [mx, my], axis=1)
                
                # Calculate the deviation from the radius
                # If it's a perfect arc, abs(distance - radius) should be 0 for all points.
                errors = np.abs(distances - radius)
                
                # We use Mean Absolute Error (MAE) normalized by the radius
                # e.g., 0.05 means the average point is within 5% of the radius ring
                consistency_score = np.mean(errors) / radius

                # Thresholds:
                # < 0.10: Very Clean Circle/Arc
                # 0.10 - 0.20: Distorted Circle (Angled view)
                # > 0.25: Square or irregular blob (Corners pull the average up)
                if consistency_score < 0.15:
                    
                    target_x = int(mx)
                    target_y = int(my)

                    # 4. NAVIGATION LOGIC
                    # Even if target_x is -500 (off screen), this math works.
                    # It creates a strong vector pulling the drone toward the virtual center.
                    curr_err_x = (target_x - center_x) / (w / 2)
                    curr_err_y = (target_y - center_y) / (h / 2)
                    
                    detected = True

                    # --- VISUALIZATION ---
                    # Draw the "Theoretical" Full Circle (Green)
                    cv2.circle(frame, (target_x, target_y), int(radius), (0, 255, 0), 2)
                    
                    # Draw the center (which might be off-screen, but we try)
                    if 0 <= target_x < w and 0 <= target_y < h:
                         cv2.circle(frame, (target_x, target_y), 5, (0, 0, 255), -1)
                         cv2.putText(frame, "CENTER", (target_x+10, target_y), 
                                     cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
                    
                    # Draw the detected Arc segment (Red) to show what we actually see
                    cv2.drawContours(frame, [cnt], -1, (0, 0, 255), 2)
                    
                    # Debug info
                    cv2.putText(frame, f"Error: {consistency_score:.3f}", (10, 30), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                    
                    break # Locked onto the best arc

            with self._lock:
                self.target_detected = detected
                self.err_x = curr_err_x
                self.err_y = curr_err_y

            cv2.imshow("Drone Vision", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                self.running = False

        cap.release()
        cv2.destroyAllWindows()