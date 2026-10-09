import cv2
import threading
import time
from ultralytics import YOLO
from mock_database import PRODUCTS, get_product_by_barcode

# Global variable to store the item currently seen by the camera
currently_picked_cv_class = None
lock = threading.Lock()

def cv_camera_thread():
    global currently_picked_cv_class
    
    # Load the pre-trained YOLOv8 model
    print("[SYSTEM] Loading YOLOv8 model...")
    try:
        model = YOLO('yolov8n.pt') # Using the nano model for speed
    except Exception as e:
        print(f"[ERROR] Failed to load model: {e}")
        return

    # Start webcam capture
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[ERROR] Could not open webcam.")
        return

    print("[SYSTEM] Camera started. Press 'q' in the video window to exit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Run YOLOv8 inference on the frame
        results = model(frame, stream=True, verbose=False)

        detected_classes = []
        
        for r in results:
            boxes = r.boxes
            for box in boxes:
                # Get class name
                cls = int(box.cls[0])
                class_name = model.names[cls]
                
                # Check if it's one of our mock products
                if class_name in PRODUCTS:
                    detected_classes.append(class_name)
                    
                    # Draw bounding box on frame for visualization
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(frame, class_name, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

        # Update the currently picked item (taking the first detected for simplicity)
        with lock:
            if detected_classes:
                currently_picked_cv_class = detected_classes[0]
            else:
                currently_picked_cv_class = None

        # Display the frame
        cv2.imshow('Shelf Camera View', frame)

        # Exit on 'q' press
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()


def scanner_terminal_thread():
    global currently_picked_cv_class
    
    time.sleep(3) # Wait for camera to initialize
    print("\n" + "="*50)
    print("🛒 VIRTUAL SCANNER READY")
    print("Type a barcode and press Enter to scan.")
    print("Valid barcodes: 1111 (Coke/Bottle), 2222 (Apple), 3333 (Cup)")
    print("="*50 + "\n")

    while True:
        barcode = input("Scan Barcode > ").strip()
        
        if barcode.lower() == 'quit' or barcode.lower() == 'q':
            print("Exiting scanner...")
            break

        cv_class, product_details = get_product_by_barcode(barcode)

        if not product_details:
            print(f"[❌ ERROR] Barcode {barcode} not found in database.\n")
            continue

        print(f"\n-> You scanned: {product_details['name']}")

        # Retrieve the currently detected item safely
        with lock:
            current_camera_item = currently_picked_cv_class

        print(f"-> Camera detects: {current_camera_item if current_camera_item else 'Nothing'}")

        # The Anomaly Check Logic
        if current_camera_item == cv_class:
            print(f"[✅ SUCCESS] Match! {product_details['name']} added to cart.\n")
        else:
            print(f"[🚨 ANOMALY DETECTED!] You picked up '{current_camera_item}' but scanned a '{product_details['name']}'.")
            print("[❌ ACTION] Item NOT added to cart. Please scan the correct item.\n")


if __name__ == '__main__':
    # Start the camera in a separate thread so it doesn't block the terminal input
    cam_thread = threading.Thread(target=cv_camera_thread, daemon=True)
    cam_thread.start()

    # Run the scanner in the main thread
    scanner_terminal_thread()
