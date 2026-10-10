# cv_node.py
# Smart Shelf Computer Vision Node — Autonomous AI Object Discovery & Pick Detector
# Dynamically identifies ANY physical objects placed on desk/shelf in real-time.
# Zero hardcoded restrictions — detects bottles, phones, books, cups, laptops, fruits, etc.

import cv2
import sys
import time
import requests
from ultralytics import YOLO

# --- Config ---
BACKEND_URL = "http://127.0.0.1"
MIN_CONFIDENCE = 0.35          # Responsive detection confidence threshold
FRAMES_TO_CONFIRM_PICK = 3     # Continuous absent frames to confirm physical pickup
FRAMES_TO_CONFIRM_RETURN = 5   # Continuous stable frames back on desk to confirm return

# Classes to exclude from desk inventory (people, furniture background)
EXCLUDED_CLASSES = {"person", "chair", "sofa", "bed", "dining table", "tv"}

# Emoji map helper for detected object classes
EMOJI_MAP = {
    "bottle": "🥤", "cell phone": "📱", "book": "📖", "cup": "☕",
    "laptop": "💻", "mouse": "🖱️", "keyboard": "⌨️", "banana": "🍌",
    "apple": "🍎", "orange": "🍊", "scissors": "✂️", "clock": "⏰",
    "backpack": "🎒", "umbrella": "☂️", "vase": "🏺", "bowl": "🥣",
    "sports ball": "⚽", "teddy bear": "🧸"
}

def get_emoji(cv_class: str) -> str:
    return EMOJI_MAP.get(cv_class.lower(), "📦")

def send_shelf_state(items_with_qty: list, picked_items: list):
    """Sends current live resting inventory with quantities and active picked items to backend API."""
    try:
        requests.post(f"{BACKEND_URL}/cv/shelf-state", json={
            "items_with_qty": items_with_qty,
            "picked_items": picked_items
        }, timeout=1)
    except Exception:
        pass

def send_pick_event(cv_class: str, event_type: str, confidence: float = 1.0):
    """Sends pick or return event to central backend API (broadcasts to active sessions)."""
    display_label = cv_class.upper()
    try:
        r = requests.post(f"{BACKEND_URL}/cv/pick-event", json={
            "session_id": "LATEST",
            "cv_class": cv_class,
            "confidence": confidence,
            "event_type": event_type,
            "shelf_slot": "Desk-Zone",
            "weight_delta_g": 200.0
        }, timeout=2)
        
        if r.status_code == 200:
            if event_type == "picked":
                print("\n" + "========================================================================")
                print(f"[SHELF CAMERA] 👆 Object picked by customer: {display_label}")
                print(f"[API BROADCAST] ✅ Pick event for '{display_label}' sent to active session! App scan UNLOCKED.")
                print("========================================================================\n")
            else:
                print("\n" + "========================================================================")
                print(f"[SHELF CAMERA] ↩️ Object returned to desk by customer: {display_label}")
                print(f"[API BROADCAST] Return event for '{display_label}' processed.")
                print("========================================================================\n")
        else:
            print(f"[API ERROR] HTTP {r.status_code}: {r.text}")
    except Exception as e:
        print(f"[API WARNING] Could not reach backend API at {BACKEND_URL}: {e}")

def run():
    print("=" * 78)
    print("🛒 SMART SHELF VISION NODE — DYNAMIC AI OBJECT DISCOVERY ENGINE")
    print("Zero Hardcoded Data: Dynamically identifies any objects placed on desk/shelf!")
    print("Real-Time Inventory & Quantity Tracker Active")
    print("=" * 78)
    print("[CV NODE] Initializing YOLOv8 Neural Network...")
    model = YOLO('yolov8n.pt')

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[CV NODE] ❌ Camera index 0 could not be opened.")
        return

    print("[CV NODE] ✅ Desk camera active. Place any items on desk. Press 'q' to quit.")

    # Tracking states per discovered object class name
    desk_qty = {}           # Resting quantity on desk per class
    picked_qty = {}         # Quantity picked off desk per class
    absent_counters = {}
    present_counters = {}
    last_state_time = 0
    known_classes = set()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        h, w, _ = frame.shape
        rack_top = int(h * 0.10)
        rack_bottom = int(h * 0.95)

        results = model(frame, stream=True, verbose=False)

        frame_counts = {}
        frame_confs = {}

        for r in results:
            for box in r.boxes:
                cls_name = model.names[int(box.cls[0])]
                conf = float(box.conf[0])

                if cls_name not in EXCLUDED_CLASSES and conf >= MIN_CONFIDENCE:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    cy = (y1 + y2) // 2

                    if rack_top <= cy <= rack_bottom:
                        frame_counts[cls_name] = frame_counts.get(cls_name, 0) + 1
                        frame_confs[cls_name] = max(frame_confs.get(cls_name, 0.0), conf)

                        color = (34, 197, 94) # Emerald Green for resting on desk
                        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                        label = f"{get_emoji(cls_name)} {cls_name.upper()} ({conf:.2f})"
                        cv2.putText(frame, label, (x1, max(y1 - 10, 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

        # Register newly discovered object classes dynamically
        for c in frame_counts:
            if c not in known_classes:
                known_classes.add(c)
                desk_qty[c] = 0
                picked_qty[c] = 0
                absent_counters[c] = 0
                present_counters[c] = 0

        # State machine update for all discovered object classes
        for c in list(known_classes):
            current_in_frame = frame_counts.get(c, 0)
            target_resting = current_in_frame

            # Case A: Object detected resting on desk
            if current_in_frame > 0:
                absent_counters[c] = 0
                present_counters[c] += 1

                if present_counters[c] >= FRAMES_TO_CONFIRM_RETURN:
                    if picked_qty.get(c, 0) > 0:
                        send_pick_event(c, "returned", frame_confs.get(c, 1.0))
                        picked_qty[c] = max(0, picked_qty[c] - 1)

                    if desk_qty.get(c, 0) != target_resting:
                        desk_qty[c] = target_resting
                        print("========================================================================")
                        print(f"[SHELF CAMERA] 📦 Object in the rack: {c.upper()} (Desk Qty: {target_resting})")
                        print("========================================================================")

            # Case B: Object count decreased (lifted off desk)
            else:
                present_counters[c] = 0
                if desk_qty.get(c, 0) > 0 and picked_qty.get(c, 0) == 0:
                    absent_counters[c] += 1
                    if absent_counters[c] >= FRAMES_TO_CONFIRM_PICK:
                        send_pick_event(c, "picked", 1.0)
                        picked_qty[c] = picked_qty.get(c, 0) + 1
                        desk_qty[c] = max(0, desk_qty[c] - 1)
                        absent_counters[c] = 0

        # Broadcast live inventory state (items with quantities) every 1.5 seconds
        if time.time() - last_state_time > 1.5:
            items_with_qty = [
                {"cv_class": c, "name": c.capitalize(), "qty": desk_qty[c], "emoji": get_emoji(c)}
                for c in known_classes if desk_qty.get(c, 0) > 0
            ]
            picked_items = [
                {"cv_class": c, "name": c.capitalize(), "qty": picked_qty[c], "emoji": get_emoji(c)}
                for c in known_classes if picked_qty.get(c, 0) > 0
            ]
            send_shelf_state(items_with_qty, picked_items)
            last_state_time = time.time()

        # HUD Overlay Banner
        cv2.rectangle(frame, (0, 0), (w, 45), (18, 19, 31), -1)
        resting_str = ", ".join([f"{c.upper()} x{desk_qty[c]}" for c in known_classes if desk_qty.get(c, 0) > 0])
        picked_str = ", ".join([f"{c.upper()} x{picked_qty[c]}" for c in known_classes if picked_qty.get(c, 0) > 0])

        if picked_str:
            hud_msg = f"PICKED: 👆 {picked_str} | ON DESK: 📦 {resting_str if resting_str else 'EMPTY'}"
        elif resting_str:
            hud_msg = f"ON DESK: 📦 {resting_str}"
        else:
            hud_msg = f"STATE: 🔍 WAITING FOR OBJECTS ON DESK"

        cv2.putText(frame, hud_msg, (15, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (226, 232, 240), 2)
        cv2.imshow('Smart Dynamic AI Desk Vision Feed', frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("[CV NODE] Camera node stopped.")

if __name__ == '__main__':
    run()
