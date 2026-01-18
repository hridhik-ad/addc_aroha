import cv2
import numpy as np

# --- 1. The GStreamer Pipeline (MKV for safety) ---
GST_PIPELINE = (
    "udpsrc port=5600 buffer-size=0 ! "
    "application/x-rtp, payload=96 ! "
    "rtph264depay ! h264parse config-interval=1 ! tee name=t "
    "! queue max-size-buffers=100 ! "
    "matroskamux ! filesink location=sitl_flight.mkv "
    "t. ! queue max-size-buffers=1 leaky=downstream ! "
    "avdec_h264 ! videoconvert ! "
    "video/x-raw, format=BGR ! "
    "appsink drop=1 sync=false"
)

def process_frame_for_squares(frame):
    """
    Detects squares/rectangles in the frame and draws a bounding box.
    """
    # A. Preprocessing
    # Convert to Grayscale (easier for computer to see shapes)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    # Blur slightly to remove "noise" (like grass texture) that looks like edges
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # B. Edge Detection
    # Canny is a popular edge detector. 50 and 150 are threshold values.
    # You might need to tune these if the camera is very bright or dark.
    edges = cv2.Canny(blur, 50, 150)
    
    # C. Find Contours (Shapes)
    # RETR_EXTERNAL = only find outer shapes (ignore shapes inside shapes)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    for cnt in contours:
        # Ignore tiny specks (noise)
        area = cv2.contourArea(cnt)
        if area < 1000:  # If area is less than 1000 pixels, skip it
            continue
            
        # D. Polygon Approximation (The Magic Step)
        # This simplifies a jagged shape into a clean polygon.
        # 0.02 is the precision (2% error allowed).
        perimeter = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * perimeter, True)
        
        # E. Check for 4 Corners
        if len(approx) == 4:
            # Get the bounding rectangle coordinates
            x, y, w, h = cv2.boundingRect(approx)
            
            # Optional: Check if it's actually a SQUARE (Aspect Ratio ~ 1)
            aspect_ratio = float(w) / h
            if 0.9 <= aspect_ratio <= 1.1:
                label = "Square"
                color = (0, 255, 0) # Green
            else:
                label = "Rectangle"
                color = (0, 0, 255) # Red
                
            # Draw the box and text
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 3)
            cv2.putText(frame, label, (x, y - 10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
            
    return frame

def main():
    print(f"Opening Pipeline:\n{GST_PIPELINE}")
    cap = cv2.VideoCapture(GST_PIPELINE, cv2.CAP_GSTREAMER)

    if not cap.isOpened():
        print("Error: Pipeline failed to open.")
        return

    print("Success! Recording and Streaming...")
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Frame capture failed (Stream ended?)")
                break

            # --- PROCESS THE FRAME ---
            processed_frame = process_frame_for_squares(frame)

            # Display the processed frame
            cv2.imshow("SITL Camera", processed_frame)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
                
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("Stopped. Video saved to 'sitl_flight.mkv'")

if __name__ == "__main__":
    main()