import hashlib
import json
import os
import re
from datetime import datetime

from config import DATA_DIR


def _sanitize_filename(name: str) -> str:
    """Remove characters not safe for filenames."""
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = name.replace(" ", "_")
    return name[:80]  # cap length


def review_fingerprint(review: dict) -> str:
    """
    Stable unique key for a review: hash of (reviewer_name, date, rating).

    Google Maps exposes no public review ID in the DOM, so we derive one.
    Using a hash keeps the key short and safe for sets/dicts.
    """
    raw = f"{review.get('reviewer_name', '')}|{review.get('date', '')}|{review.get('rating', '')}"
    return hashlib.md5(raw.encode()).hexdigest()


def build_fingerprint_set(reviews: list[dict]) -> set[str]:
    """Return the set of fingerprints for a list of reviews."""
    return {review_fingerprint(r) for r in reviews}


def load_latest_for_place(place_name: str) -> dict | None:
    """
    Find and load the most recently saved JSON file for a given place name.
    Returns None if no prior data exists.
    """
    if not os.path.exists(DATA_DIR):
        return None

    safe_name = _sanitize_filename(place_name)
    candidates = [
        f for f in os.listdir(DATA_DIR)
        if f.startswith(safe_name) and f.endswith(".json")
    ]
    if not candidates:
        return None

    # Pick the most recently modified file
    candidates.sort(
        key=lambda f: os.path.getmtime(os.path.join(DATA_DIR, f)),
        reverse=True,
    )
    return load_reviews(os.path.join(DATA_DIR, candidates[0]))


def merge_reviews(existing: dict, new_reviews: list[dict]) -> tuple[dict, int]:
    """
    Merge new_reviews into existing place data, skipping duplicates.

    Returns (merged_record, added_count).
    The merged record keeps all existing reviews and appends only genuinely
    new ones (determined by fingerprint). scraped_at and total are updated.
    """
    known = build_fingerprint_set(existing.get("reviews", []))
    added = []
    for r in new_reviews:
        fp = review_fingerprint(r)
        if fp not in known:
            known.add(fp)
            added.append(r)

    merged_reviews = existing.get("reviews", []) + added
    merged = existing.copy()
    merged["reviews"] = merged_reviews
    merged["total_reviews_scraped"] = len(merged_reviews)
    merged["scraped_at"] = datetime.now().isoformat(timespec="seconds")
    return merged, len(added)


def save_reviews(data: dict, place_name: str) -> str:
    """
    Save scraped review data to a JSON file.

    Returns the file path where data was saved.
    """
    os.makedirs(DATA_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = _sanitize_filename(place_name)
    filename = f"{safe_name}_{timestamp}.json"
    file_path = os.path.join(DATA_DIR, filename)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return file_path


def load_reviews(file_path: str) -> dict:
    """Load review data from a JSON file."""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_review_files() -> list[dict]:
    """List all saved review files with metadata."""
    if not os.path.exists(DATA_DIR):
        return []

    files = []
    for fname in os.listdir(DATA_DIR):
        if fname.endswith(".json"):
            fpath = os.path.join(DATA_DIR, fname)
            stat = os.stat(fpath)
            files.append(
                {
                    "filename": fname,
                    "path": fpath,
                    "size_bytes": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                }
            )

    files.sort(key=lambda x: x["modified"], reverse=True)
    return files


def build_review_record(
    reviewer_name: str,
    rating: int | None,
    date: str | None,
    text: str | None,
    photos_count: int = 0,
    photo_urls: list[str] | None = None,
) -> dict:
    """
    Build a single review dict matching the schema.
    SQLite3-ready: maps to a flat 'reviews' table row.
    """
    return {
        "reviewer_name": reviewer_name,
        "rating": rating,
        "date": date,
        "text": text,
        "photos_count": photos_count,
        "photo_urls": photo_urls or [],
    }


def build_place_record(
    place_name: str,
    place_url: str,
    reviews: list[dict],
    place_id: str | None = None,
) -> dict:
    """
    Build the top-level place dict matching the schema.
    SQLite3-ready: maps to a 'places' table + 'reviews' table.
    """
    return {
        "place_id": place_id or "",
        "place_name": place_name,
        "place_url": place_url,
        "scraped_at": datetime.now().isoformat(timespec="seconds"),
        "total_reviews_scraped": len(reviews),
        "reviews": reviews,
    }
