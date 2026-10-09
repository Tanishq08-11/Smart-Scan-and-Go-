# backend/database.py
# Handles SQLite database creation and all DB operations

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "store.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Creates all tables and seeds the 10 shelf products."""
    conn = get_connection()
    cursor = conn.cursor()

    # --- Products Table ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            barcode     TEXT UNIQUE NOT NULL,
            price       REAL NOT NULL,
            cv_class    TEXT NOT NULL  -- The YOLOv8 class name this product maps to
        )
    """)

    # --- Sessions Table (represents one customer shopping trip) ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id          TEXT PRIMARY KEY,
            status      TEXT NOT NULL DEFAULT 'active',  -- active | checked_out
            created_at  TEXT NOT NULL
        )
    """)

    # --- Cart Items Table ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cart_items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT NOT NULL,
            product_id  INTEGER NOT NULL,
            quantity    INTEGER NOT NULL DEFAULT 1,
            added_at    TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)

    # --- CV Event Log Table (what the camera saw and when) ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cv_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT NOT NULL,
            cv_class    TEXT NOT NULL,   -- e.g., "bottle"
            event_type  TEXT NOT NULL,   -- "picked" or "returned"
            timestamp   TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    """)

    # --- Anomaly Log Table ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS anomaly_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      TEXT NOT NULL,
            picked_cv_class TEXT,        -- what camera saw
            scanned_barcode TEXT,        -- what was scanned
            timestamp       TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    """)

    # --- Seed 10 Products (only if table is empty) ---
    cursor.execute("SELECT COUNT(*) FROM products")
    if cursor.fetchone()[0] == 0:
        products = [
            ("Coca-Cola 500ml",    "1111", 2.50, "bottle"),
            ("Fresh Apple",        "2222", 0.80, "apple"),
            ("Store Coffee Mug",   "3333", 5.99, "cup"),
            ("Notebook",           "4444", 3.50, "book"),
            ("Smartphone Case",    "5555", 15.00, "cell phone"),
            ("Wireless Mouse",     "6666", 25.00, "mouse"),
            ("Crafting Scissors",  "7777", 4.25, "scissors"),
            ("Oral-B Toothbrush",  "8888", 2.99, "toothbrush"),
            ("Fresh Orange",       "9999", 0.75, "orange"),
            ("Chiquita Banana",    "0000", 0.50, "banana"),
        ]
        cursor.executemany(
            "INSERT INTO products (name, barcode, price, cv_class) VALUES (?, ?, ?, ?)",
            products
        )
        print("[DB] Seeded 10 products into the database.")

    conn.commit()
    conn.close()
    print("[DB] Database initialized successfully.")
