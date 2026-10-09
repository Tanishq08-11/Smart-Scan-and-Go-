# cv_node.py
# The upgraded CV Node — runs YOLOv8 on the webcam and sends pick events
# to the central backend API via HTTP requests.
#
# HOW TO USE:
#   1. Start the backend first:  cd backend && uvicorn main:app --reload
#   2. Run this script:          python cv_node.py <session_id>
#   Example:                     python cv_node.py A3F9C2B1

import cv2
import sys
import time
import requests
from ultralytics import YOLO
from mock_database import PRODUCTS

# --- Config ---
BACKEND_URL = "http://127.0.0.1:8000"
# How many consecutive frames an object must disappear to be considered "put back"
FRAMES_UNTIL_GONE = 15

def send_pick_event(session_id: str, cv_class: str, event_type: str):
    """Sends a pick/return event to the backend API."""
    try:
        r = requests.post(f"{BACKEND_URL}/cv/pick-event", json={
            "session_id": session_id,
            "cv_class": cv_class,
            "event_type": event_type
        }, timeout=2)
        if r.status_code == 200:
            icon = "👆" if event_type == "picked" else "↩️"
            print(f"[CV -> API] {icon} {event_type.upper()}: {cv_class}")
        else:
            print(f"[CV -> API] Error: {r.status_code} {r.text}")
    except requests.exceptions.ConnectionError:
        print("[CV -> API] ⚠️  Cannot reach backend. Is it running?")

def run(session_id: str):
    print(f"[CV NODE] Starting for session: {session_id}")
    print("[CV NODE] Loading YOLOv8 model...")
    model = YOLO('yolov8n.pt')
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("[CV NODE] ❌ Could not open webcam.")
        return

    print("[CV NODE] ✅ Camera running. Press 'q' to quit.")

    # State tracking to avoid spamming the API
    last_detected = None        # Last class that was "in frame"
    frames_since_seen = 0       # Counter for how long it's been absent

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        results = model(frame, stream=True, verbose=False)

        detected_this_frame = None

        for r in results:
            for box in r.boxes:
                cls_name = model.names[int(box.cls[0])]
                if cls_name in PRODUCTS:
                    detected_this_frame = cls_name
                    # Draw bounding box
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    conf = float(box.conf[0])
                    color = (0, 255, 0)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    label = f"{cls_name} ({conf:.2f}) -> {PRODUCTS[cls_name]['name']}"
                    cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                    break  # Only track one item at a time for prototype simplicity

        # --- State Machine: Detect Pick and Return events ---
        if detected_this_frame:
            frames_since_seen = 0
            if detected_this_frame != last_detected:
                # New item appeared — fire "picked" event
                send_pick_event(session_id, detected_this_frame, "picked")
                last_detected = detected_this_frame
        else:
            if last_detected is not None:
                frames_since_seen += 1
                if frames_since_seen >= FRAMES_UNTIL_GONE:
                    # Item has been absent long enough — fire "returned" event
                    send_pick_event(session_id, last_detected, "returned")
                    last_detected = None
                    frames_since_seen = 0

        # HUD overlay
        cv2.putText(frame, f"Session: {session_id}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255,255,255), 2)
        cv2.putText(frame, f"Tracking: {last_detected or 'Nothing'}", (10, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,255), 2)
        cv2.imshow('Shelf Camera — CV Node', frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("[CV NODE] Stopped.")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python cv_node.py <session_id>")
        print("Example: python cv_node.py A3F9C2B1")
        print("\nTip: Start the backend first to get a session ID:")
        print("  cd backend && uvicorn main:app --reload")
        print("  Then POST to http://127.0.0.1:8000/session/new")
    else:
        run(sys.argv[1])
