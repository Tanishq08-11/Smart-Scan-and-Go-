# cv_node.py
# Smart Shelf Computer Vision Node — Live Shelf State & Physical Pickup Detector
# Tracks physical pickup off shelf:
#   1. Object resting on shelf  -> Camera sees object (ON_SHELF) -> Logs "Object in the rack"
#   2. Customer lifts object off shelf -> Object disappears from shelf view -> Fire PICKED event! Logs "Object picked by customer"
#   3. Customer puts object back on shelf -> Object settles back on shelf -> Fire RETURNED event! Logs "Object returned to rack"

import cv2
import sys
import time
import requests
from ultralytics import YOLO

# --- Config ---
BACKEND_URL = "http://127.0.0.1:8000"
MIN_CONFIDENCE = 0.40          # Responsive confidence threshold for target shelf items
FRAMES_TO_CONFIRM_PICK = 3     # Continuous absent frames to confirm customer physical pickup
FRAMES_TO_CONFIRM_RETURN = 6   # Continuous stable frames back in rack to confirm return to shelf

# Targeted catalog items to monitor on shelf
PRODUCTS = {
    "bottle": {"name": "Coca-Cola 500ml", "barcode": "1111", "price": 2.50, "slot": "Shelf-A1"},
    "banana": {"name": "Chiquita Banana",  "barcode": "0000", "price": 0.50, "slot": "Shelf-A2"},
}

def send_shelf_state(detected_items: list):
    """Sends current live shelf inventory state to backend API."""
    try:
        requests.post(f"{BACKEND_URL}/cv/shelf-state", json={"items": detected_items}, timeout=1)
    except Exception:
        pass

def send_pick_event(cv_class: str, event_type: str, confidence: float = 1.0):
    """Sends pick or return event to central backend API (broadcasts to active sessions)."""
    product_name = PRODUCTS.get(cv_class, {}).get("name", cv_class.capitalize())
    try:
        r = requests.post(f"{BACKEND_URL}/cv/pick-event", json={
            "session_id": "LATEST",
            "cv_class": cv_class,
            "confidence": confidence,
            "event_type": event_type,
            "shelf_slot": PRODUCTS.get(cv_class, {}).get("slot", "Shelf-A1"),
            "weight_delta_g": PRODUCTS.get(cv_class, {}).get("price", 1.0) * 200
        }, timeout=2)
        
        if r.status_code == 200:
            if event_type == "picked":
                print("\n" + "========================================================================")
                print(f"[SHELF CAMERA] 👆 Object picked by customer: {cv_class.upper()} ({product_name})")
                print(f"[API BROADCAST] ✅ Pick event for '{cv_class.upper()}' sent to active session! App scan is NOW UNLOCKED.")
                print("========================================================================\n")
            else:
                print("\n" + "========================================================================")
                print(f"[SHELF CAMERA] ↩️ Object returned to rack by customer: {cv_class.upper()} ({product_name})")
                print(f"[API BROADCAST] Return event for '{cv_class.upper()}' processed.")
                print("========================================================================\n")
        else:
            print(f"[API ERROR] HTTP {r.status_code}: {r.text}")
    except Exception as e:
        print(f"[API WARNING] Could not reach backend API at {BACKEND_URL}: {e}")

def run():
    print("=" * 76)
    print("🛒 SMART SHELF VISION NODE — DYNAMIC INVENTORY & PICK DETECTOR")
    print("Monitored Shelf Items: BOTTLE (Coca-Cola 500ml) & BANANA (Chiquita Banana)")
    print("Terminal Status Monitor: Active ('Object in the rack' vs 'Object picked by customer')")
    print("=" * 76)
    print("[CV NODE] Initializing YOLOv8 Object Detection Neural Network...")
    model = YOLO('yolov8n.pt')

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[CV NODE] ❌ Camera index 0 could not be opened.")
        return

    print("[CV NODE] ✅ Shelf camera feed active. Place object on shelf. Press 'q' to quit.")

    object_on_shelf = None
    absent_counter = 0
    present_counter = 0
    item_currently_picked = False
    picked_item_class = None
    last_conf = 1.0
    last_state_time = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        h, w, _ = frame.shape
        # Define rack detection zone (middle to lower frame area)
        rack_top = int(h * 0.15)
        rack_bottom = int(h * 0.95)

        results = model(frame, stream=True, verbose=False)

        detected_class = None
        detected_conf = 0.0

        for r in results:
            for box in r.boxes:
                cls_name = model.names[int(box.cls[0])]
                conf = float(box.conf[0])

                # SMART FILTERING: Strict Whitelist for Target Products (Bottle & Banana)
                # Ignores extraneous environment objects (person, phone, cup, chair, etc.)
                if cls_name in PRODUCTS and conf >= MIN_CONFIDENCE:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    cy = (y1 + y2) // 2

                    # Only count as resting on rack if y-center is within rack zone
                    if rack_top <= cy <= rack_bottom:
                        detected_class = cls_name
                        detected_conf = conf

                        color = (34, 197, 94) # Emerald Green for resting on rack
                        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                        label = f"Object in rack: {PRODUCTS[cls_name]['name']} ({conf:.2f})"
                        cv2.putText(frame, label, (x1, max(y1 - 10, 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                        break

        # Broadcast live shelf state to API every 1.5 seconds
        if time.time() - last_state_time > 1.5:
            current_list = [detected_class] if detected_class else []
            send_shelf_state(current_list)
            last_state_time = time.time()

        # --- SHELF PICKUP / RETURN STATE MACHINE WITH STABILITY HYSTERESIS ---
        if detected_class:
            absent_counter = 0
            present_counter += 1

            # Require continuous stability back on rack to confirm return (prevents false triggers while holding/scanning)
            if present_counter >= FRAMES_TO_CONFIRM_RETURN:
                if item_currently_picked and picked_item_class == detected_class:
                    send_pick_event(detected_class, "returned", detected_conf)
                    item_currently_picked = False
                    picked_item_class = None

                if object_on_shelf != detected_class:
                    object_on_shelf = detected_class
                    product_name = PRODUCTS[detected_class]['name']
                    print(f"========================================================================")
                    print(f"[SHELF CAMERA] 📦 Object in the rack: {detected_class.upper()} ({product_name})")
                    print(f"========================================================================")

                last_conf = detected_conf

        else:
            present_counter = 0
            if object_on_shelf is not None and not item_currently_picked:
                absent_counter += 1
                if absent_counter >= FRAMES_TO_CONFIRM_PICK:
                    send_pick_event(object_on_shelf, "picked", last_conf)
                    picked_item_class = object_on_shelf
                    item_currently_picked = True
                    object_on_shelf = None
                    absent_counter = 0

        # HUD Overlay
        cv2.rectangle(frame, (0, 0), (w, 45), (18, 19, 31), -1)
        if item_currently_picked:
            hud_msg = f"STATE: 👆 {picked_item_class.upper()} PICKED BY CUSTOMER (Available for App Scan)"
        elif object_on_shelf:
            hud_msg = f"STATE: 📦 Object in the rack: {object_on_shelf.upper()}"
        else:
            hud_msg = f"STATE: 🔍 RACK EMPTY"

        cv2.putText(frame, hud_msg, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (226, 232, 240), 2)
        cv2.imshow('Smart Shelf Vision Feed (Bottle / Banana Detector)', frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("[CV NODE] Camera node stopped.")

if __name__ == '__main__':
    run()
