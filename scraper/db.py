"""SQLite3 storage layer for Google Maps reviews."""

import json
import os
import sqlite3
from datetime import datetime

from scraper.data_manager import review_fingerprint


def get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(db_path: str) -> sqlite3.Connection:
    """Create tables if they don't exist and return a connection."""
    conn = get_conn(db_path)
    # Migrate: add place_type column to existing DBs (safe no-op if already exists)
    try:
        conn.execute("ALTER TABLE places ADD COLUMN place_type TEXT DEFAULT 'general'")
        conn.commit()
    except Exception:
        pass  # column already exists

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS places (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            place_name       TEXT NOT NULL,
            place_id         TEXT DEFAULT '',
            place_url        TEXT DEFAULT '',
            place_type       TEXT DEFAULT 'general',
            first_scraped_at TEXT,
            last_scraped_at  TEXT
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_places_name ON places(place_name);

        CREATE TABLE IF NOT EXISTS reviews (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            place_db_id   INTEGER NOT NULL REFERENCES places(id),
            fingerprint   TEXT    NOT NULL UNIQUE,
            reviewer_name TEXT,
            rating        INTEGER,
            date          TEXT,
            text          TEXT,
            photos_count  INTEGER DEFAULT 0,
            photo_urls    TEXT    DEFAULT '[]',
            scraped_at    TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_reviews_place ON reviews(place_db_id);
    """)
    conn.commit()
    return conn


def upsert_place(conn: sqlite3.Connection, place_data: dict) -> int:
    """Insert or update a place record and its reviews. Returns place DB id."""
    name = place_data.get("place_name", "").strip()
    if not name:
        return -1

    now = datetime.now().isoformat(timespec="seconds")
    place_id = place_data.get("place_id", "")
    place_url = place_data.get("place_url", "")
    scraped_at = place_data.get("scraped_at", now)

    # Upsert place row
    conn.execute("""
        INSERT INTO places (place_name, place_id, place_url, first_scraped_at, last_scraped_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(place_name) DO UPDATE SET
            place_url       = excluded.place_url,
            last_scraped_at = excluded.last_scraped_at
    """, (name, place_id, place_url, scraped_at, scraped_at))
    conn.commit()

    place_db_id = conn.execute(
        "SELECT id FROM places WHERE place_name = ?", (name,)
    ).fetchone()["id"]

    # Batch insert reviews (IGNORE duplicates via fingerprint UNIQUE)
    reviews = place_data.get("reviews", [])
    rows = []
    for r in reviews:
        fp = review_fingerprint(r)
        rows.append((
            place_db_id,
            fp,
            r.get("reviewer_name"),
            r.get("rating"),
            r.get("date"),
            r.get("text"),
            r.get("photos_count", 0),
            json.dumps(r.get("photo_urls", []), ensure_ascii=False),
            scraped_at,
        ))

    conn.executemany("""
        INSERT OR IGNORE INTO reviews
            (place_db_id, fingerprint, reviewer_name, rating, date, text,
             photos_count, photo_urls, scraped_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()
    return place_db_id


def list_places(conn: sqlite3.Connection) -> list[dict]:
    """Return all places with aggregate stats."""
    rows = conn.execute("""
        SELECT
            p.place_name,
            p.place_url,
            p.last_scraped_at,
            COUNT(r.id)                                      AS total_reviews,
            ROUND(AVG(CAST(r.rating AS REAL)), 1)            AS avg_rating,
            SUM(CASE WHEN r.rating <= 2 THEN 1 ELSE 0 END)  AS alert_count
        FROM places p
        LEFT JOIN reviews r ON r.place_db_id = p.id
        GROUP BY p.id
        ORDER BY p.last_scraped_at DESC
    """).fetchall()
    return [dict(r) for r in rows]


def get_place_data(conn: sqlite3.Connection, place_name: str) -> dict | None:
    """Return a place dict compatible with analyzer.analyze_place()."""
    place_row = conn.execute(
        "SELECT * FROM places WHERE place_name = ?", (place_name,)
    ).fetchone()
    if not place_row:
        return None

    review_rows = conn.execute(
        "SELECT * FROM reviews WHERE place_db_id = ? ORDER BY id",
        (place_row["id"],),
    ).fetchall()

    reviews = []
    for r in review_rows:
        reviews.append({
            "reviewer_name": r["reviewer_name"],
            "rating": r["rating"],
            "date": r["date"],
            "text": r["text"],
            "photos_count": r["photos_count"],
            "photo_urls": json.loads(r["photo_urls"] or "[]"),
        })

    return {
        "place_id":   place_row["place_id"],
        "place_name": place_row["place_name"],
        "place_url":  place_row["place_url"],
        "place_type": place_row["place_type"] or "general",
        "scraped_at": place_row["last_scraped_at"],
        "total_reviews_scraped": len(reviews),
        "reviews": reviews,
    }


def import_json_files(conn: sqlite3.Connection, data_dir: str):
    """One-time migration: import all existing JSON files in data_dir into DB."""
    if not os.path.exists(data_dir):
        return 0
    imported = 0
    for fname in os.listdir(data_dir):
        if not fname.endswith(".json"):
            continue
        try:
            fpath = os.path.join(data_dir, fname)
            with open(fpath, encoding="utf-8") as f:
                place_data = json.load(f)
            if place_data.get("place_name") and place_data.get("reviews") is not None:
                upsert_place(conn, place_data)
                imported += 1
        except Exception:
            pass
    return imported
