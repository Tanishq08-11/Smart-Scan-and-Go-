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

    # Force re-seed products to strictly match the 2 required items (bottle & banana)
    cursor.execute("DELETE FROM products")
    products = [
        ("Coca-Cola 500ml", "1111", 2.50, "bottle", 500.0, "Shelf-A1", "🥤"),
        ("Chiquita Banana", "0000", 0.50, "banana", 120.0, "Shelf-A2", "🍌"),
    ]
    cursor.executemany(
        "INSERT INTO products (name, barcode, price, cv_class, weight_g, shelf_slot, emoji) VALUES (?, ?, ?, ?, ?, ?, ?)",
        products
    )
    print("[DB] Seeded exactly 2 products: Bottle (1111) & Banana (0000).")

    conn.commit()
    conn.close()
    print("[DB] Database initialized successfully.")
