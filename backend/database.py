# backend/database.py
# Handles SQLite database creation and schema migrations for Scan & Go

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "store.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Creates all tables and seeds the 2 target shelf products (Bottle & Banana)."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            barcode     TEXT UNIQUE NOT NULL,
            price       REAL NOT NULL,
            cv_class    TEXT NOT NULL,
            weight_g    REAL DEFAULT 250.0,
            shelf_slot  TEXT DEFAULT 'Shelf-A1',
            emoji       TEXT DEFAULT '📦'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id               TEXT PRIMARY KEY,
            person_track_id  TEXT,
            preauth_status   TEXT DEFAULT 'AUTHORIZED',
            payment_method   TEXT DEFAULT 'UPI / Card Pre-Auth',
            trust_score      INTEGER DEFAULT 100,
            status           TEXT NOT NULL DEFAULT 'active',
            created_at       TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cart_items (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id          TEXT NOT NULL,
            product_id          INTEGER NOT NULL,
            quantity            INTEGER NOT NULL DEFAULT 1,
            verification_status TEXT DEFAULT 'VERIFIED',
            added_at            TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cv_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT NOT NULL,
            cv_class    TEXT NOT NULL,
            confidence  REAL NOT NULL DEFAULT 1.0,
            event_type  TEXT NOT NULL, -- 'picked', 'returned', 'reconciled'
            timestamp   TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS anomaly_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      TEXT NOT NULL,
            picked_cv_class TEXT,
            scanned_barcode TEXT,
            anomaly_type    TEXT NOT NULL DEFAULT 'UNKNOWN',
            reason          TEXT,
            timestamp       TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    """)

    # Clear stale historical events & carts to ensure clean 0 initial pick count on startup
    cursor.execute("DELETE FROM cv_events")
    cursor.execute("DELETE FROM cart_items")
    cursor.execute("DELETE FROM anomaly_log")
    cursor.execute("UPDATE sessions SET status = 'completed' WHERE status = 'active'")

    # Seed products table with target items (Bottle, Phone, Book)
    cursor.execute("DELETE FROM products")
    products = [
        ("Water Bottle 500ml", "1111", 2.50, "bottle", 500.0, "Shelf-A1", "🥤"),
        ("Smartphone Pro", "2222", 699.00, "cell phone", 200.0, "Shelf-A2", "📱"),
        ("Hardcover Book", "3333", 15.00, "book", 450.0, "Shelf-A3", "📖"),
    ]
    cursor.executemany(
        "INSERT INTO products (name, barcode, price, cv_class, weight_g, shelf_slot, emoji) VALUES (?, ?, ?, ?, ?, ?, ?)",
        products
    )
    print("[DB] Seeded 3 target products: Bottle (1111), Phone (2222), Book (3333).")
    print("[DB] Cleared historical cv_events and cart logs for clean initial 0 pick count.")

    conn.commit()
    conn.close()
    print("[DB] Database initialized successfully.")
