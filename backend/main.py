# backend/main.py
# FastAPI backend — the central brain of the Scan & Go system.
#
# Endpoints:
#   POST /session/new          — Start a new shopping session
#   POST /cv/pick-event        — CV Node reports what item was picked up
#   POST /app/scan             — App sends a scanned barcode
#   GET  /app/cart/{session_id}— App retrieves the virtual cart
#   POST /app/checkout         — Checkout and finalize the cart
#   GET  /products             — List all products in the database

import sys
import io

# Force UTF-8 output on Windows to prevent emoji/unicode encoding crashes
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from datetime import datetime
import uuid
import sqlite3
import os

from database import init_db, get_connection

# --- App Setup ---
app = FastAPI(title="Scan & Go API", version="1.0.0")

# Allow requests from the web app (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the web app frontend from the /app folder
app_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app")
if os.path.exists(app_dir):
    app.mount("/ui", StaticFiles(directory=app_dir, html=True), name="frontend")

# Initialize DB on startup
@app.on_event("startup")
def startup():
    init_db()
    print("[SERVER] Scan & Go API is running.")

# --- Request Models ---
class CVPickEvent(BaseModel):
    session_id: str
    cv_class: str          # e.g., "bottle"
    event_type: str        # "picked" or "returned"

class ScanRequest(BaseModel):
    session_id: str
    barcode: str

# --- Helper ---
ANOMALY_WINDOW_SECONDS = 20  # How long (in seconds) to look back for a CV event

def get_recent_cv_event(session_id: str, conn: sqlite3.Connection):
    """Returns the most recent 'picked' CV event within the time window."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT cv_class, timestamp FROM cv_events
        WHERE session_id = ? AND event_type = 'picked'
        ORDER BY timestamp DESC LIMIT 1
    """, (session_id,))
    row = cursor.fetchone()
    if not row:
        return None
    event_time = datetime.fromisoformat(row["timestamp"])
    seconds_ago = (datetime.now() - event_time).total_seconds()
    if seconds_ago <= ANOMALY_WINDOW_SECONDS:
        return row["cv_class"]
    return None  # Too old to be relevant

# =============================================================================
# ENDPOINTS
# =============================================================================

@app.get("/")
def root():
    return {"message": "Scan & Go API is running! Visit /docs for API explorer."}

@app.get("/products")
def list_products():
    """Returns all products in the shelf database."""
    conn = get_connection()
    products = conn.execute("SELECT * FROM products").fetchall()
    conn.close()
    return [dict(p) for p in products]

# --- Session Management ---
@app.post("/session/new")
def new_session():
    """Creates a new shopping session for a customer."""
    session_id = str(uuid.uuid4())[:8].upper()
    conn = get_connection()
    conn.execute(
        "INSERT INTO sessions (id, status, created_at) VALUES (?, 'active', ?)",
        (session_id, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    print(f"[SESSION] New session started: {session_id}")
    return {"session_id": session_id, "status": "active"}

# --- CV Node Endpoint ---
@app.post("/cv/pick-event")
def cv_pick_event(event: CVPickEvent):
    """
    Called by the CV Node (camera) when it detects an item being picked up.
    Logs this event so the anomaly checker can use it.
    """
    conn = get_connection()
    session = conn.execute("SELECT id FROM sessions WHERE id = ?", (event.session_id,)).fetchone()
    if not session:
        conn.close()
        raise HTTPException(status_code=404, detail="Session not found.")

    conn.execute(
        "INSERT INTO cv_events (session_id, cv_class, event_type, timestamp) VALUES (?, ?, ?, ?)",
        (event.session_id, event.cv_class, event.event_type, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    print(f"[CV EVENT] Session {event.session_id}: {event.event_type} -> {event.cv_class}")
    return {"status": "logged", "cv_class": event.cv_class, "event_type": event.event_type}

# --- App Scan Endpoint ---
@app.post("/app/scan")
def scan_item(req: ScanRequest):
    """
    Called by the mobile app when the customer scans a barcode.
    Performs anomaly detection by comparing with the last CV event.
    If valid, adds the item to the virtual cart.
    """
    conn = get_connection()

    # 1. Validate session
    session = conn.execute("SELECT * FROM sessions WHERE id = ?", (req.session_id,)).fetchone()
    if not session:
        conn.close()
        raise HTTPException(status_code=404, detail="Session not found.")
    if session["status"] != "active":
        conn.close()
        raise HTTPException(status_code=400, detail="Session is already checked out.")

    # 2. Look up the barcode in the database
    product = conn.execute("SELECT * FROM products WHERE barcode = ?", (req.barcode,)).fetchone()
    if not product:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Barcode '{req.barcode}' not found.")

    product = dict(product)

    # 3. Get the most recent CV event (what the camera saw)
    recent_cv_class = get_recent_cv_event(req.session_id, conn)

    # 4. Anomaly Detection
    if recent_cv_class is None:
        conn.execute(
            "INSERT INTO anomaly_log (session_id, picked_cv_class, scanned_barcode, timestamp) VALUES (?, ?, ?, ?)",
            (req.session_id, None, req.barcode, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
        print(f"[ANOMALY] Session {req.session_id}: No camera event before scan of '{req.barcode}'")
        return {
            "status": "anomaly",
            "reason": "No item pick detected by camera before scan.",
            "scanned": product["name"],
            "camera_saw": None
        }

    if recent_cv_class != product["cv_class"]:
        conn.execute(
            "INSERT INTO anomaly_log (session_id, picked_cv_class, scanned_barcode, timestamp) VALUES (?, ?, ?, ?)",
            (req.session_id, recent_cv_class, req.barcode, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
        print(f"[ANOMALY] Session {req.session_id}: Camera={recent_cv_class}, Scan={product['cv_class']}")
        return {
            "status": "anomaly",
            "reason": f"Camera saw '{recent_cv_class}' but you scanned '{product['name']}'",
            "scanned": product["name"],
            "camera_saw": recent_cv_class
        }

    # 5. All clear — add to cart
    existing = conn.execute(
        "SELECT id, quantity FROM cart_items WHERE session_id = ? AND product_id = ?",
        (req.session_id, product["id"])
    ).fetchone()

    if existing:
        conn.execute("UPDATE cart_items SET quantity = quantity + 1 WHERE id = ?", (existing["id"],))
    else:
        conn.execute(
            "INSERT INTO cart_items (session_id, product_id, quantity, added_at) VALUES (?, ?, 1, ?)",
            (req.session_id, product["id"], datetime.now().isoformat())
        )

    conn.commit()
    conn.close()
    print(f"[ADDED] Session {req.session_id}: {product['name']} added to cart.")
    return {
        "status": "success",
        "message": f"{product['name']} added to cart!",
        "product": product
    }

# --- Get Cart ---
@app.get("/app/cart/{session_id}")
def get_cart(session_id: str):
    """Returns the full virtual cart for a session."""
    conn = get_connection()
    session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not session:
        conn.close()
        raise HTTPException(status_code=404, detail="Session not found.")

    items = conn.execute("""
        SELECT p.name, p.price, p.barcode, ci.quantity,
               (p.price * ci.quantity) as subtotal
        FROM cart_items ci
        JOIN products p ON ci.product_id = p.id
        WHERE ci.session_id = ?
    """, (session_id,)).fetchall()

    cart = [dict(i) for i in items]
    total = sum(i["subtotal"] for i in cart)
    conn.close()
    return {"session_id": session_id, "items": cart, "total": round(total, 2), "status": session["status"]}

# --- Checkout ---
@app.post("/app/checkout")
def checkout(req: dict):
    """Finalizes the cart and marks the session as checked out."""
    session_id = req.get("session_id")
    conn = get_connection()
    session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not session:
        conn.close()
        raise HTTPException(status_code=404, detail="Session not found.")

    items = conn.execute("""
        SELECT p.name, p.price, ci.quantity, (p.price * ci.quantity) as subtotal
        FROM cart_items ci JOIN products p ON ci.product_id = p.id
        WHERE ci.session_id = ?
    """, (session_id,)).fetchall()

    cart = [dict(i) for i in items]
    total = sum(i["subtotal"] for i in cart)

    conn.execute("UPDATE sessions SET status = 'checked_out' WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()
    print(f"[CHECKOUT] Session {session_id} checked out. Total: ${total:.2f}")
    return {"status": "checked_out", "session_id": session_id, "items": cart, "total": round(total, 2)}
