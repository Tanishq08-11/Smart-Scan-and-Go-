# backend/main.py
# FastAPI backend — Real-Time Loss Prevention Engine for Scan & Go
# Features direct HTML file response for root '/' and '/ui' routes so app loads instantly on phone & PC!

import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
from datetime import datetime
import uuid
import sqlite3
import os

try:
    from database import init_db, get_connection
except ImportError:
    from backend.database import init_db, get_connection

# --- App Setup ---
app = FastAPI(title="Scan & Go Loss Prevention API", version="3.6.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app")
if os.path.exists(app_dir):
    app.mount("/ui", StaticFiles(directory=app_dir, html=True), name="frontend")

@app.on_event("startup")
def startup():
    init_db()
    print("[SERVER] Scan & Go Loss Prevention API v3.6 is running.")

# --- Direct UI Route Handlers (Foolproof Web Access) ---
@app.get("/")
def root():
    index_path = os.path.join(app_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Scan & Go Loss Prevention API v3.6 is running."}

@app.get("/ui")
def ui_root():
    index_path = os.path.join(app_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return RedirectResponse(url="/ui/")

# --- Live Camera Shelf State & Event Cache ---
current_shelf_inventory = {"items": [], "picked_items": [], "last_events": [], "updated_at": None}

# --- Models ---
class NewSessionRequest(BaseModel):
    payment_method: str = "UPI / Card Pre-Auth"

class CVPickEvent(BaseModel):
    session_id: str = "LATEST"
    cv_class: str
    confidence: float = 1.0
    event_type: str              # "picked" or "returned"
    shelf_slot: str = "Shelf-A1"
    weight_delta_g: float = 0.0

class ShelfStateRequest(BaseModel):
    items: list = []
    items_with_qty: list = []
    picked_items: list = []

class ScanRequest(BaseModel):
    session_id: str
    barcode: str

class RemoveCartItemRequest(BaseModel):
    session_id: str
    barcode: str

BARCODE_PRESETS = {
    "bottle": ("1111", 2.50, "🥤"),
    "cell phone": ("2222", 699.00, "📱"),
    "book": ("3333", 15.00, "📖"),
    "cup": ("4444", 4.50, "☕"),
    "laptop": ("5555", 999.00, "💻"),
    "mouse": ("6666", 25.00, "🖱️"),
    "keyboard": ("7777", 45.00, "⌨️"),
    "banana": ("8888", 0.50, "🍌"),
    "apple": ("9999", 1.00, "🍎")
}

def recalculate_trust_score(conn: sqlite3.Connection, session_id: str):
    """Calculates deterministic Trust Score based on active pick ledger and anomaly audit."""
    score = 100
    
    mismatches = conn.execute(
        "SELECT COUNT(*) FROM anomaly_log WHERE session_id = ? AND anomaly_type IN ('CLASS_MISMATCH', 'INVALID_PRODUCT', 'UNAUTHORIZED_CART_REMOVE')",
        (session_id,)
    ).fetchone()[0]
    score -= (mismatches * 20)

    # Check unreturned picks penalty if checking out
    session = conn.execute("SELECT created_at, status FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if session and session["status"] == "checked_out":
        created_at = session["created_at"]
        picks = conn.execute("SELECT COUNT(*) FROM cv_events WHERE session_id = ? AND timestamp >= ? AND event_type = 'picked'", (session_id, created_at)).fetchone()[0]
        returns = conn.execute("SELECT COUNT(*) FROM cv_events WHERE session_id = ? AND timestamp >= ? AND event_type = 'returned'", (session_id, created_at)).fetchone()[0]
        scans_row = conn.execute("SELECT SUM(quantity) FROM cart_items WHERE session_id = ?", (session_id,)).fetchone()[0]
        scans = scans_row if scans_row else 0

        unresolved_count = max(0, picks - returns - scans)
        score -= (unresolved_count * 50)

    score = max(0, min(100, score))
    conn.execute("UPDATE sessions SET trust_score = ? WHERE id = ?", (score, session_id))
    conn.commit()
    return score

def log_anomaly(conn, session_id, picked_cv_class, scanned_barcode, anomaly_type, reason):
    conn.execute(
        """INSERT INTO anomaly_log
           (session_id, picked_cv_class, scanned_barcode, anomaly_type, reason, timestamp)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (session_id, picked_cv_class, scanned_barcode, anomaly_type, reason, datetime.now().isoformat())
    )
    conn.commit()

# =============================================================================
# ENDPOINTS
# =============================================================================

@app.get("/products")
def list_products():
    """Returns products catalog (Bottle & Banana)."""
    conn = get_connection()
    products = conn.execute("SELECT * FROM products").fetchall()
    conn.close()
    return [dict(p) for p in products]

@app.get("/anomalies/{session_id}")
def get_anomalies(session_id: str):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM anomaly_log WHERE session_id = ? ORDER BY timestamp DESC",
        (session_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# --- 1. Session Entry QR Scan ---
@app.post("/session/new")
def new_session(req: NewSessionRequest = NewSessionRequest()):
    session_id = str(uuid.uuid4())[:8].upper()
    person_track_id = f"TRK-{uuid.uuid4().hex[:4].upper()}"
    created_at = datetime.now().isoformat()
    
    conn = get_connection()
    conn.execute("UPDATE sessions SET status = 'completed' WHERE status = 'active'")
    conn.execute("DELETE FROM cv_events")
    conn.execute("DELETE FROM cart_items")
    conn.execute("DELETE FROM anomaly_log")
    conn.execute(
        """INSERT INTO sessions 
           (id, person_track_id, preauth_status, payment_method, trust_score, status, created_at) 
           VALUES (?, ?, 'AUTHORIZED ($50 Hold)', ?, 100, 'active', ?)""",
        (session_id, person_track_id, req.payment_method, created_at)
    )
    conn.commit()
    conn.close()
    print(f"[SESSION] New Entry QR Scan: Session {session_id} bound to {person_track_id}")
    return {
        "session_id": session_id,
        "person_track_id": person_track_id,
        "preauth_status": "AUTHORIZED ($50 Hold)",
        "trust_score": 100,
        "status": "active"
    }

@app.get("/session/latest")
def get_latest_session():
    """Returns the most recent active session."""
    conn = get_connection()
    session = conn.execute("SELECT * FROM sessions WHERE status = 'active' ORDER BY created_at DESC LIMIT 1").fetchone()
    conn.close()
    if session:
        return dict(session)
    raise HTTPException(status_code=404, detail="No active session found.")

# --- 2. Live Camera Shelf State & Pick Event Broadcasting ---
@app.post("/cv/shelf-state")
def update_shelf_state(req: ShelfStateRequest):
    global current_shelf_inventory

    # Auto-seed dynamically discovered camera products into store database
    if req.items_with_qty:
        conn = get_connection()
        for item in req.items_with_qty:
            cv_cls = item["cv_class"]
            name = item["name"]
            emoji = item.get("emoji", "📦")
            
            existing = conn.execute("SELECT id FROM products WHERE cv_class = ?", (cv_cls,)).fetchone()
            if not existing:
                if cv_cls in BARCODE_PRESETS:
                    bc, pr, em = BARCODE_PRESETS[cv_cls]
                else:
                    count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
                    bc = f"{(count + 1) * 1111:04d}"[:4]
                    pr = 9.99
                    em = emoji

                conn.execute(
                    "INSERT OR IGNORE INTO products (name, barcode, price, cv_class, weight_g, shelf_slot, emoji) VALUES (?, ?, ?, ?, 200.0, 'Desk-Zone', ?)",
                    (f"{name}", bc, pr, cv_cls, em)
                )
        conn.commit()
        conn.close()

    current_shelf_inventory = {
        "items": [i["cv_class"] for i in req.items_with_qty] if req.items_with_qty else req.items,
        "items_with_qty": req.items_with_qty,
        "picked_items": req.picked_items,
        "last_events": current_shelf_inventory.get("last_events", []),
        "updated_at": datetime.now().isoformat()
    }
    return {"status": "updated", "items_with_qty": req.items_with_qty, "picked_items": req.picked_items}

@app.get("/cv/shelf-state")
def get_shelf_state():
    return current_shelf_inventory

@app.post("/cv/pick-event")
def cv_pick_event(event: CVPickEvent):
    """
    Ingests physical pick/return events.
    Automatically posts to ALL active shopping sessions!
    """
    conn = get_connection()
    active_sessions = conn.execute("SELECT id FROM sessions WHERE status = 'active'").fetchall()
    
    target_sessions = [s["id"] for s in active_sessions]
    if event.session_id and event.session_id != "LATEST" and event.session_id not in target_sessions:
        target_sessions.append(event.session_id)

    # Append to live event stream for UI display
    event_entry = {
        "cv_class": event.cv_class,
        "event_type": event.event_type,
        "timestamp": datetime.now().strftime("%I:%M:%S %p")
    }
    events_list = current_shelf_inventory.get("last_events", [])
    events_list.insert(0, event_entry)
    current_shelf_inventory["last_events"] = events_list[:5]

    if not target_sessions:
        conn.close()
        return {"status": "logged", "reason": "Camera event stream updated, no active sessions."}

    for sid in target_sessions:
        conn.execute(
            """INSERT INTO cv_events (session_id, cv_class, confidence, event_type, timestamp)
               VALUES (?, ?, ?, ?, ?)""",
            (sid, event.cv_class, event.confidence, event.event_type, datetime.now().isoformat())
        )
        recalculate_trust_score(conn, sid)

    conn.commit()
    conn.close()
    
    icon = "👆 PICKED OFF SHELF" if event.event_type == "picked" else "↩️ PUT BACK ON SHELF"
    print(f"[SHELF CAMERA API] Broadcast {icon} -> {event.cv_class.upper()} to Active Sessions: {target_sessions}")
    return {
        "status": "logged",
        "event_type": event.event_type,
        "cv_class": event.cv_class,
        "target_sessions": target_sessions
    }

# --- 3. App Barcode Scan Endpoint ---
@app.post("/app/scan")
def scan_item(req: ScanRequest):
    conn = get_connection()

    session = conn.execute("SELECT * FROM sessions WHERE id = ?", (req.session_id,)).fetchone()
    if not session:
        conn.close()
        raise HTTPException(status_code=404, detail="Session not found.")

    product = conn.execute("SELECT * FROM products WHERE barcode = ?", (req.barcode,)).fetchone()
    if not product:
        log_anomaly(conn, req.session_id, None, req.barcode,
                    "INVALID_PRODUCT", f"Barcode '{req.barcode}' does not exist in store.")
        conn.close()
        raise HTTPException(status_code=400, detail=f"Barcode '{req.barcode}' is invalid.")

    product = dict(product)
    expected_class = product["cv_class"]
    session_created = session["created_at"]

    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) FROM cv_events
        WHERE session_id = ? AND cv_class = ? AND event_type = 'picked' AND timestamp >= ?
    """, (req.session_id, expected_class, session_created))
    pick_count = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM cv_events
        WHERE session_id = ? AND cv_class = ? AND event_type = 'returned' AND timestamp >= ?
    """, (req.session_id, expected_class, session_created))
    return_count = cursor.fetchone()[0]

    cart_qty_row = conn.execute("""
        SELECT SUM(quantity) FROM cart_items ci
        JOIN products p ON ci.product_id = p.id
        WHERE ci.session_id = ? AND p.cv_class = ?
    """, (req.session_id, expected_class)).fetchone()[0]
    scanned_qty = cart_qty_row if cart_qty_row else 0

    available_unscanned_picks = pick_count - return_count - scanned_qty

    if available_unscanned_picks <= 0:
        # Check if customer picked a DIFFERENT item class off shelf
        other_pick = conn.execute("""
            SELECT cv_class FROM cv_events
            WHERE session_id = ? AND event_type = 'picked' AND cv_class != ? AND timestamp >= ?
            ORDER BY timestamp DESC LIMIT 1
        """, (req.session_id, expected_class, session_created)).fetchone()

        if other_pick:
            actual_picked_class = other_pick["cv_class"]
            err_msg = f"🚨 Security Alert: Class Mismatch! You physically picked '{actual_picked_class.upper()}' off the shelf, but scanned barcode for '{product['name']}'!"
            log_anomaly(conn, req.session_id, actual_picked_class, req.barcode, "CLASS_MISMATCH", err_msg)
        elif pick_count == 0:
            err_msg = f"Security Alert: No physical pickup detected for '{product['name']}'. Please lift the item off the shelf first!"
        else:
            err_msg = f"Notice: All picked '{product['name']}' items are already in your cart. Lift another item off the shelf to scan again."

        recalculate_trust_score(conn, req.session_id)
        conn.close()
        raise HTTPException(status_code=400, detail=err_msg)

    # Match confirmed — Add to cart as VERIFIED
    existing = conn.execute(
        "SELECT id, quantity FROM cart_items WHERE session_id = ? AND product_id = ?",
        (req.session_id, product["id"])
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE cart_items SET quantity = quantity + 1, verification_status = 'VERIFIED' WHERE id = ?",
            (existing["id"],)
        )
    else:
        conn.execute(
            """INSERT INTO cart_items 
               (session_id, product_id, quantity, verification_status, added_at) 
               VALUES (?, ?, 1, 'VERIFIED', ?)""",
            (req.session_id, product["id"], datetime.now().isoformat())
        )

    conn.commit()
    trust_score = recalculate_trust_score(conn, req.session_id)
    conn.close()

    print(f"[SCAN SUCCESS] Session {req.session_id}: {product['name']} (VERIFIED) | Trust Score: {trust_score}")
    return {
        "status": "success",
        "verification_status": "VERIFIED",
        "message": f"✅ {product['name']} verified and added to cart!",
        "product": product,
        "trust_score": trust_score
    }

# --- 3.5. Remove Item From Cart (Strict Condition: Item MUST be back on shelf!) ---
@app.post("/app/cart/remove")
def remove_cart_item(req: RemoveCartItemRequest):
    conn = get_connection()

    session = conn.execute("SELECT * FROM sessions WHERE id = ?", (req.session_id,)).fetchone()
    if not session:
        conn.close()
        raise HTTPException(status_code=404, detail="Session not found.")

    product = conn.execute("SELECT * FROM products WHERE barcode = ?", (req.barcode,)).fetchone()
    if not product:
        conn.close()
        raise HTTPException(status_code=404, detail="Product not found.")

    product = dict(product)
    cv_class = product["cv_class"]
    session_created = session["created_at"]

    # Check if item is currently on shelf or returned
    is_on_shelf = cv_class in current_shelf_inventory.get("items", [])
    
    recent_returns = conn.execute("""
        SELECT COUNT(*) FROM cv_events
        WHERE session_id = ? AND cv_class = ? AND event_type = 'returned' AND timestamp >= ?
    """, (req.session_id, cv_class, session_created)).fetchone()[0]

    recent_picks = conn.execute("""
        SELECT COUNT(*) FROM cv_events
        WHERE session_id = ? AND cv_class = ? AND event_type = 'picked' AND timestamp >= ?
    """, (req.session_id, cv_class, session_created)).fetchone()[0]

    # Item is considered returned to shelf if currently on shelf OR return events match pick events
    item_is_returned = is_on_shelf or (recent_returns >= recent_picks and recent_picks > 0)

    if not item_is_returned:
        log_anomaly(conn, req.session_id, cv_class, req.barcode,
                    "UNAUTHORIZED_CART_REMOVE",
                    f"Attempted to remove '{product['name']}' from cart while item is NOT resting on shelf.")
        conn.close()
        raise HTTPException(
            status_code=400,
            detail=f"Security Alert: Cannot remove '{product['name']}' from cart. Please place the item back on the shelf rack first!"
        )

    cart_item = conn.execute(
        "SELECT id, quantity FROM cart_items WHERE session_id = ? AND product_id = ?",
        (req.session_id, product["id"])
    ).fetchone()

    if not cart_item:
        conn.close()
        raise HTTPException(status_code=400, detail=f"'{product['name']}' is not in your cart.")

    if cart_item["quantity"] > 1:
        conn.execute("UPDATE cart_items SET quantity = quantity - 1 WHERE id = ?", (cart_item["id"],))
    else:
        conn.execute("DELETE FROM cart_items WHERE id = ?", (cart_item["id"],))

    conn.commit()
    trust_score = recalculate_trust_score(conn, req.session_id)
    conn.close()

    print(f"[CART REMOVE SUCCESS] Session {req.session_id}: {product['name']} returned to shelf & removed from cart!")
    return {
        "status": "success",
        "message": f"↩️ {product['name']} returned to shelf and removed from cart!",
        "trust_score": trust_score
    }

# --- 4. Get Cart State & Pick Ledger ---
@app.get("/app/cart/{session_id}")
def get_cart(session_id: str):
    conn = get_connection()
    session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not session:
        conn.close()
        raise HTTPException(status_code=404, detail="Session not found.")

    items = conn.execute("""
        SELECT p.name, p.price, p.barcode, p.emoji, ci.quantity, ci.verification_status,
               (p.price * ci.quantity) as subtotal
        FROM cart_items ci
        JOIN products p ON ci.product_id = p.id
        WHERE ci.session_id = ?
    """, (session_id,)).fetchall()

    cart = [dict(i) for i in items]
    total = sum(i["subtotal"] for i in cart)
    session_created = session["created_at"]
    
    # Audit Pick Ledger
    picks = conn.execute("SELECT COUNT(*) FROM cv_events WHERE session_id = ? AND timestamp >= ? AND event_type = 'picked'", (session_id, session_created)).fetchone()[0]
    returns = conn.execute("SELECT COUNT(*) FROM cv_events WHERE session_id = ? AND timestamp >= ? AND event_type = 'returned'", (session_id, session_created)).fetchone()[0]
    scans = sum(i["quantity"] for i in cart)
    
    unresolved_picks = max(0, picks - returns - scans)
    
    conn.close()
    return {
        "session_id": session_id,
        "person_track_id": session["person_track_id"],
        "preauth_status": session["preauth_status"],
        "trust_score": session["trust_score"],
        "items": cart,
        "total": round(total, 2),
        "ledger_audit": {
            "total_picks": picks,
            "total_returns": returns,
            "total_scans": scans,
            "unresolved_picks": unresolved_picks
        },
        "status": session["status"]
    }

# --- 5. Checkout & Exit Gate Audit ---
@app.post("/app/checkout")
def checkout(req: dict):
    session_id = req.get("session_id")
    conn = get_connection()
    session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not session:
        conn.close()
        raise HTTPException(status_code=404, detail="Session not found.")

    items = conn.execute("""
        SELECT p.name, p.price, ci.quantity, ci.verification_status, (p.price * ci.quantity) as subtotal
        FROM cart_items ci JOIN products p ON ci.product_id = p.id
        WHERE ci.session_id = ?
    """, (session_id,)).fetchall()

    cart = [dict(i) for i in items]
    total = sum(i["subtotal"] for i in cart)
    session_created = session["created_at"]

    picks = conn.execute("SELECT COUNT(*) FROM cv_events WHERE session_id = ? AND timestamp >= ? AND event_type = 'picked'", (session_id, session_created)).fetchone()[0]
    returns = conn.execute("SELECT COUNT(*) FROM cv_events WHERE session_id = ? AND timestamp >= ? AND event_type = 'returned'", (session_id, session_created)).fetchone()[0]
    scans = sum(i["quantity"] for i in cart)
    
    unresolved_picks = max(0, picks - returns - scans)
    trust_score = session["trust_score"]

    if unresolved_picks == 0 and trust_score >= 80:
        gate_decision = "GATE_OPEN_AUTOMATIC"
        gate_status_msg = "🟢 Exit Gate Released — Pre-Authorized Card Charged Automatically"
    else:
        gate_decision = "GATE_LOCKED_SECURITY_AUDIT"
        gate_status_msg = f"🔴 Automated Security Hold — Unresolved Shelf Picks: {unresolved_picks}, Trust Score: {trust_score}"

    conn.execute("UPDATE sessions SET status = 'checked_out' WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()

    print(f"[EXIT RECONCILIATION] Session {session_id} -> Gate: {gate_decision}")
    return {
        "status": "checked_out",
        "session_id": session_id,
        "person_track_id": session["person_track_id"],
        "payment_receipt": {
            "amount_charged": round(total, 2),
            "payment_status": "PAID via Pre-Authorized Card/UPI",
            "transaction_id": f"TXN-{uuid.uuid4().hex[:8].upper()}"
        },
        "trust_score": trust_score,
        "unresolved_picks": unresolved_picks,
        "gate_decision": gate_decision,
        "gate_status_msg": gate_status_msg,
        "items": cart
    }
