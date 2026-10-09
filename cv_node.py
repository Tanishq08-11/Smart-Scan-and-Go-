# cv_node.py
# Smart Shelf Computer Vision Node — Live Shelf State & Physical Pickup Detector
# Tracks physical pickup off shelf:
#   1. Object resting on shelf  -> Camera sees object (ON_SHELF)
#   2. User lifts object off shelf -> Object disappears from shelf view -> Fire PICKED event!
#   3. User puts object back on shelf -> Object reappears on shelf view -> Fire RETURNED event!

import cv2
import sys
import time
import requests
from ultralytics import YOLO

# --- Config ---
BACKEND_URL = "http://127.0.0.1:8000"
MIN_CONFIDENCE = 0.45          # Responsive confidence threshold for webcams
FRAMES_TO_CONFIRM_PICK = 2     # Disappearance frames needed to confirm physical PICK
FRAMES_TO_CONFIRM_RETURN = 2   # Reappearance frames needed to confirm RETURN to shelf

PRODUCTS = {
    "bottle": {"name": "Coca-Cola 500ml", "barcode": "1111", "price": 2.50, "slot": "Shelf-A1"},
    "banana": {"name": "Chiquita Banana",  "barcode": "0000", "price": 0.50, "slot": "Shelf-A2"},
}

def send_shelf_state(detected_items: list):
    """Sends current live shelf inventory to backend API."""
    try:
        requests.post(f"{BACKEND_URL}/cv/shelf-state", json={"items": detected_items}, timeout=1)
    except Exception:
        pass

def send_pick_event(cv_class: str, event_type: str, confidence: float = 1.0):
    """Sends pick or return event to central backend API (broadcasts to active sessions)."""
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
                print("\n" + "🚨 " * 16)
                print(f"[SHELF PICK EVENT] 👆 {cv_class.upper()} WAS PICKED UP FROM THE SHELF!")
                print(f"[API BROADCAST] ✅ Pick event for '{cv_class.upper()}' sent to active sessions. App scan is NOW UNLOCKED!")
                print("🚨 " * 16 + "\n")
            else:
                print("\n" + "↩️ " * 16)
                print(f"[SHELF RETURN EVENT] ↩️ {cv_class.upper()} WAS PLACED BACK ON THE SHELF!")
                print(f"[API BROADCAST] Return event for '{cv_class.upper()}' processed.")
                print("↩️ " * 16 + "\n")
        else:
            print(f"[API ERROR] HTTP {r.status_code}: {r.text}")
    except requests.exceptions.ConnectionError:
        print("[API ERROR] ⚠️ Cannot connect to backend server at http://127.0.0.1:8000")

def run():
    print("=" * 72)
    print("🛒 SMART SHELF VISION NODE — DYNAMIC INVENTORY & PICK DETECTOR")
    print("Monitored Shelf Items: BOTTLE (Coca-Cola 500ml) & BANANA (Chiquita Banana)")
    print("=" * 72)
    print("[CV NODE] Initializing YOLOv8 Object Detection Neural Network...")
    model = YOLO('yolov8n.pt')

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[CV NODE] ❌ Camera index 0 could not be opened.")
        return

    print("[CV NODE] ✅ Shelf camera active. Position object on shelf. Press 'q' to quit.")

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

        results = model(frame, stream=True, verbose=False)

        detected_class = None
        detected_conf = 0.0

        for r in results:
            for box in r.boxes:
                cls_name = model.names[int(box.cls[0])]
                conf = float(box.conf[0])

                if cls_name in PRODUCTS and conf >= MIN_CONFIDENCE:
                    detected_class = cls_name
                    detected_conf = conf

                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    color = (34, 197, 94) # Emerald Green for on shelf
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    label = f"{PRODUCTS[cls_name]['name']} ON SHELF ({conf:.2f})"
                    cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                    break

        # Broadcast live shelf state every 1.5 seconds
        if time.time() - last_state_time > 1.5:
            current_list = [detected_class] if detected_class else []
            send_shelf_state(current_list)
            last_state_time = time.time()

        # --- SHELF PICKUP / RETURN STATE MACHINE ---
        if detected_class:
            absent_counter = 0
            present_counter += 1

            if present_counter >= FRAMES_TO_CONFIRM_RETURN:
                if item_currently_picked and picked_item_class == detected_class:
                    send_pick_event(detected_class, "returned", detected_conf)
                    item_currently_picked = False
                    picked_item_class = None

                if object_on_shelf != detected_class:
                    object_on_shelf = detected_class
                    print(f"[SHELF INVENTORY] 📦 Monitored Shelf Inventory: [{detected_class.upper()}] resting on shelf.")

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
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 45), (18, 19, 31), -1)
        if item_currently_picked:
            hud_msg = f"STATE: 🚨 {picked_item_class.upper()} PICKED OFF SHELF (Available for App Scan)"
        elif object_on_shelf:
            hud_msg = f"STATE: 📦 {object_on_shelf.upper()} RESTING ON SHELF"
        else:
            hud_msg = f"STATE: 🔍 SHELF EMPTY"

        cv2.putText(frame, hud_msg, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (226, 232, 240), 2)
        cv2.imshow('Smart Shelf Vision Feed (Bottle / Banana)', frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("[CV NODE] Camera node stopped.")

if __name__ == '__main__':
    run()
