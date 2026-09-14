"""SQLite persistence for the SIH prototype."""

from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DEFAULT_DB = DATA_DIR / "kabadiwala.db"

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS kabadiwalas (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    area TEXT NOT NULL,
    phone TEXT NOT NULL,
    rating REAL NOT NULL,
    pin TEXT NOT NULL,
    verified INTEGER NOT NULL DEFAULT 1,
    lat REAL,
    lng REAL
);

CREATE TABLE IF NOT EXISTS catalog_items (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    rate_per_kg REAL NOT NULL,
    icon TEXT NOT NULL,
    category TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kabadiwala_rates (
    kabadiwala_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    rate_per_kg REAL NOT NULL,
    PRIMARY KEY (kabadiwala_id, item_id),
    FOREIGN KEY (kabadiwala_id) REFERENCES kabadiwalas(id),
    FOREIGN KEY (item_id) REFERENCES catalog_items(id)
);

CREATE TABLE IF NOT EXISTS pickups (
    id INTEGER PRIMARY KEY,
    tracking_code TEXT NOT NULL UNIQUE,
    kabadiwala_id INTEGER NOT NULL,
    household_name TEXT NOT NULL,
    household_phone TEXT NOT NULL,
    address TEXT NOT NULL,
    area TEXT,
    preferred_time TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    estimated_total REAL NOT NULL DEFAULT 0,
    actual_payout REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (kabadiwala_id) REFERENCES kabadiwalas(id)
);

CREATE TABLE IF NOT EXISTS pickup_items (
    id INTEGER PRIMARY KEY,
    pickup_id INTEGER NOT NULL,
    item_name TEXT NOT NULL,
    weight_kg REAL NOT NULL,
    rate_per_kg REAL,
    is_custom INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (pickup_id) REFERENCES pickups(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS earnings_ledger (
    id INTEGER PRIMARY KEY,
    kabadiwala_id INTEGER NOT NULL,
    pickup_id INTEGER,
    amount REAL NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (kabadiwala_id) REFERENCES kabadiwalas(id),
    FOREIGN KEY (pickup_id) REFERENCES pickups(id)
);

CREATE TABLE IF NOT EXISTS staff (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    pin TEXT NOT NULL,
    role TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    subject_type TEXT NOT NULL,
    subject_id INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
"""


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DEFAULT_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    _seed_if_empty(conn)
    conn.commit()


def _seed_if_empty(conn: sqlite3.Connection) -> None:
    count = conn.execute("SELECT COUNT(*) AS n FROM kabadiwalas").fetchone()["n"]
    if count:
        return

    kabadiwalas = [
        (1, "Prince Kumar", "Sector 12", "9310176402", 4.6, "1234", 1, 28.5921, 77.3345),
        (2, "Jha Scrap Dealers", "Sector 9", "7079840944", 4.3, "1234", 1, 28.5872, 77.3410),
        (3, "Green Scrap Co.", "Block C", "9876543210", 4.8, "1234", 1, 28.5804, 77.3258),
    ]
    conn.executemany(
        """INSERT INTO kabadiwalas (id, name, area, phone, rating, pin, verified, lat, lng)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        kabadiwalas,
    )

    items = [
        (1, "Newspaper", 14, "📰", "paper"),
        (2, "Cardboard", 11, "📦", "paper"),
        (3, "Plastic Bottles", 22, "🧴", "plastic"),
        (4, "Iron Scrap", 28, "🔩", "metal"),
        (5, "Aluminum", 32, "🥫", "metal"),
        (6, "E-waste", 35, "🔌", "ewaste"),
        (7, "Glass Bottles", 8, "🍾", "glass"),
        (8, "Copper Wire", 55, "🧵", "metal"),
    ]
    conn.executemany(
        """INSERT INTO catalog_items (id, name, rate_per_kg, icon, category)
           VALUES (?, ?, ?, ?, ?)""",
        items,
    )

    # Small rate variation so judges can see per-collector pricing.
    overrides = [
        (1, 1, 15),
        (1, 8, 58),
        (2, 4, 26),
        (3, 6, 40),
        (3, 3, 24),
    ]
    conn.executemany(
        """INSERT INTO kabadiwala_rates (kabadiwala_id, item_id, rate_per_kg)
           VALUES (?, ?, ?)""",
        overrides,
    )

    conn.execute(
        "INSERT INTO staff (username, pin, role) VALUES (?, ?, ?)",
        ("ops", "admin123", "admin"),
    )
