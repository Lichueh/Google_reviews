"""
Flask REST API server for the Google Reviews scraper.

Endpoints:
  POST /api/scrape/search   - Start a scrape job by place name
  POST /api/scrape/url      - Start a scrape job by Google Maps URL
  GET  /api/status/<job_id> - Poll job status
  GET  /api/results/<job_id>- Get scraped data when complete
"""

import json
import logging
import os
import threading
import uuid
from datetime import datetime

from flask import Flask, jsonify, render_template, request

import config
from scraper.analyzer import analyze_place
from scraper.db import get_place_data, import_json_files, init_db, list_places, upsert_place
from nlp.pipeline import get_pipeline, clear_cache
from scraper.google_maps_scraper import GoogleMapsScraper
from scraper.data_manager import (
    build_fingerprint_set,
    load_latest_for_place,
    merge_reviews,
    save_reviews,
)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True  # always serve latest template files

# Initialise SQLite3 and import any existing JSON files on startup
_db_conn = init_db(config.DB_PATH)
_imported = import_json_files(_db_conn, config.DATA_DIR)
if _imported:
    logger.info("Imported %d existing JSON files into SQLite3 DB", _imported)


@app.after_request
def add_cors_headers(response):
    """Manually inject CORS headers — works without flask-cors installed."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.route("/", defaults={"path": ""}, methods=["OPTIONS"])
@app.route("/<path:path>", methods=["OPTIONS"])
def handle_preflight(path):
    """Handle CORS preflight requests for all routes."""
    return "", 204

# In-memory job store: { job_id: {...} }
jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Job helpers
# ---------------------------------------------------------------------------

def _create_job(job_type: str, params: dict) -> str:
    job_id = str(uuid.uuid4())
    with jobs_lock:
        jobs[job_id] = {
            "id": job_id,
            "type": job_type,
            "params": params,
            "status": "queued",   # queued | running | done | error
            "progress": 0,
            "total": params.get("max_reviews", config.MAX_REVIEWS) or 0,  # 0 = unknown until detected
            "created_at": datetime.now().isoformat(),
            "result": None,
            "file_path": None,
            "error": None,
        }
    return job_id


def _update_job(job_id: str, **kwargs):
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id].update(kwargs)


def _run_scrape_job(job_id: str):
    """Background thread target: runs the scraper and updates job state."""
    job = jobs.get(job_id)
    if not job:
        return

    _update_job(job_id, status="running")
    params = job["params"]
    max_reviews = params.get("max_reviews", config.MAX_REVIEWS)
    update_mode = params.get("update", False)

    def on_progress(current, total):
        _update_job(job_id, progress=current, total=total)

    def on_checkpoint(place_name, place_url, place_id, batch):
        """Flush a batch of reviews to DB incrementally (every 50 reviews)."""
        partial_data = {
            "place_name": place_name,
            "place_url": place_url,
            "place_id": place_id,
            "reviews": batch,
        }
        upsert_place(_db_conn, partial_data)
        logger.info("Checkpoint saved %d reviews for '%s'", len(batch), place_name)

    try:
        # --- Update mode: load existing data and build fingerprint set ---
        existing_data = None
        existing_fingerprints = None
        if update_mode:
            place_name_hint = params.get("place_name", "")
            existing_data = load_latest_for_place(place_name_hint) if place_name_hint else None
            if existing_data:
                existing_fingerprints = build_fingerprint_set(existing_data.get("reviews", []))
                logger.info(
                    "Update mode: found %d existing reviews for '%s'",
                    len(existing_fingerprints),
                    place_name_hint,
                )

        with GoogleMapsScraper(headless=config.HEADLESS, progress_callback=on_progress,
                               cookie_file=config.COOKIE_FILE,
                               checkpoint_callback=on_checkpoint, checkpoint_every=50) as scraper:
            if job["type"] == "search":
                data = scraper.search_place(
                    params["place_name"],
                    max_reviews=max_reviews,
                    existing_fingerprints=existing_fingerprints,
                )
            else:  # url
                data = scraper.scrape_from_url(
                    url=params["url"],
                    max_reviews=max_reviews,
                    place_name=params.get("place_name", ""),
                    existing_fingerprints=existing_fingerprints,
                )

        # --- Merge with existing if in update mode ---
        added_count = data.get("total_reviews_scraped", 0)
        if update_mode and existing_data:
            data, added_count = merge_reviews(existing_data, data.get("reviews", []))
            logger.info("Merged: %d new reviews added", added_count)
            _update_job(job_id, new_reviews_added=added_count)

        file_path = save_reviews(data, data.get("place_name", "unknown"))
        upsert_place(_db_conn, data)
        _update_job(
            job_id,
            status="done",
            progress=data.get("total_reviews_scraped", 0),
            total=data.get("total_reviews_scraped", 0),
            new_reviews_added=added_count,
            result=data,
            file_path=file_path,
        )
        logger.info("Job %s done. Saved to %s", job_id, file_path)

    except Exception as e:
        logger.exception("Job %s failed: %s", job_id, e)
        _update_job(job_id, status="error", error=str(e))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/api/scrape/search", methods=["POST"])
def scrape_search():
    """Start a scrape job by place name.

    Body: {
      "place_name": str,
      "max_reviews": int  (optional, default 100),
      "update": bool      (optional, default false — skip already-known reviews)
    }
    """
    body = request.get_json(silent=True) or {}
    place_name = body.get("place_name", "").strip()
    if not place_name:
        return jsonify({"error": "place_name is required"}), 400

    max_reviews = int(body.get("max_reviews", config.MAX_REVIEWS))
    max_reviews = max(0, max_reviews)  # 0 = scrape all
    update = bool(body.get("update", False))

    job_id = _create_job("search", {"place_name": place_name, "max_reviews": max_reviews, "update": update})
    threading.Thread(target=_run_scrape_job, args=(job_id,), daemon=True).start()

    logger.info("Created search job %s for '%s' (max=%d, update=%s)", job_id, place_name, max_reviews, update)
    return jsonify({"job_id": job_id, "status": "queued"}), 202


@app.route("/api/scrape/url", methods=["POST"])
def scrape_url():
    """Start a scrape job by Google Maps URL.

    Body: {
      "url": str,
      "max_reviews": int   (optional),
      "place_name": str    (optional),
      "update": bool       (optional, default false)
    }
    """
    body = request.get_json(silent=True) or {}
    url = body.get("url", "").strip()
    if not url:
        return jsonify({"error": "url is required"}), 400
    if "google.com/maps" not in url and "maps.google.com" not in url:
        return jsonify({"error": "url must be a Google Maps URL"}), 400

    max_reviews = int(body.get("max_reviews", config.MAX_REVIEWS))
    max_reviews = max(0, max_reviews)  # 0 = scrape all
    place_name = body.get("place_name", "").strip()
    update = bool(body.get("update", False))

    job_id = _create_job("url", {"url": url, "max_reviews": max_reviews, "place_name": place_name, "update": update})
    threading.Thread(target=_run_scrape_job, args=(job_id,), daemon=True).start()

    logger.info("Created URL job %s (max=%d, update=%s)", job_id, max_reviews, update)
    return jsonify({"job_id": job_id, "status": "queued"}), 202


@app.route("/api/status/<job_id>", methods=["GET"])
def get_status(job_id):
    """Return job status and progress."""
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404

    return jsonify({
        "job_id": job["id"],
        "status": job["status"],
        "progress": job["progress"],
        "total": job["total"],
        "new_reviews_added": job.get("new_reviews_added"),
        "error": job.get("error"),
    })


@app.route("/api/results/<job_id>", methods=["GET"])
def get_results(job_id):
    """Return full scraped data for a completed job."""
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404

    if job["status"] != "done":
        return jsonify({"error": f"job is not done (status: {job['status']})"}), 409

    return jsonify({
        "job_id": job["id"],
        "file_path": job["file_path"],
        "data": job["result"],
    })


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "jobs": len(jobs)})


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.route("/api/places", methods=["GET"])
def api_list_places():
    """List all places with aggregate stats from SQLite3."""
    return jsonify(list_places(_db_conn))


@app.route("/api/places/<path:place_name>", methods=["GET"])
def api_get_place(place_name):
    """Return merged reviews + analysis for a place."""
    data = get_place_data(_db_conn, place_name)
    if not data:
        return jsonify({"error": "place not found"}), 404
    return jsonify(analyze_place(data, place_type=data.get("place_type", "general")))


@app.route("/api/places/<path:place_name>/type", methods=["POST"])
def api_set_place_type(place_name):
    """Update the place type (affects which alert keywords are used)."""
    from scraper.analyzer import PLACE_TYPE_LABELS
    body = request.get_json(silent=True) or {}
    place_type = body.get("place_type", "general")
    if place_type not in PLACE_TYPE_LABELS:
        return jsonify({"error": f"unknown place_type: {place_type}"}), 400
    _db_conn.execute(
        "UPDATE places SET place_type = ? WHERE place_name = ?",
        (place_type, place_name),
    )
    _db_conn.commit()
    return jsonify({"ok": True, "place_type": place_type})


@app.route("/api/review-files", methods=["GET"])
def list_review_files():
    """List all saved JSON review files in DATA_DIR."""
    files = []
    if os.path.exists(config.DATA_DIR):
        for fname in sorted(os.listdir(config.DATA_DIR), reverse=True):
            if fname.endswith(".json"):
                fpath = os.path.join(config.DATA_DIR, fname)
                stat = os.stat(fpath)
                files.append({
                    "filename": fname,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
    return jsonify(files)


@app.route("/api/review-files/<filename>", methods=["GET"])
def get_review_file(filename):
    """Return a single review file with analysis results."""
    if not filename.endswith(".json") or "/" in filename or ".." in filename:
        return jsonify({"error": "invalid filename"}), 400
    fpath = os.path.join(config.DATA_DIR, filename)
    if not os.path.exists(fpath):
        return jsonify({"error": "file not found"}), 404
    with open(fpath, encoding="utf-8") as f:
        place_data = json.load(f)
    return jsonify(analyze_place(place_data))


# ---------------------------------------------------------------------------
# Yuqing (輿情) Analysis Routes
# ---------------------------------------------------------------------------

@app.route("/yuqing")
def yuqing_dashboard():
    return render_template("yuqing.html")


@app.route("/methodology")
def methodology():
    return render_template("methodology.html")


@app.route("/api/yuqing/venues", methods=["GET"])
def yuqing_venues():
    """List venues with review counts for yuqing analysis."""
    places = list_places(_db_conn)
    return jsonify(places)


def _get_venue_pipeline(venue_name: str):
    """Helper: load venue data and get/create pipeline."""
    data = get_place_data(_db_conn, venue_name)
    if not data or not data.get("reviews"):
        return None
    return get_pipeline(venue_name, data["reviews"])


@app.route("/api/yuqing/tokenize", methods=["POST"])
def yuqing_tokenize():
    """Run tokenization and return stats."""
    body = request.get_json(silent=True) or {}
    venue = body.get("venue", "").strip()
    if not venue:
        return jsonify({"error": "venue is required"}), 400

    pipeline = _get_venue_pipeline(venue)
    if not pipeline:
        return jsonify({"error": f"venue '{venue}' not found or has no reviews"}), 404

    return jsonify(pipeline.token_stats())


@app.route("/api/yuqing/collocation", methods=["POST"])
def yuqing_collocation():
    """Compute collocations with given parameters."""
    body = request.get_json(silent=True) or {}
    venue = body.get("venue", "").strip()
    if not venue:
        return jsonify({"error": "venue is required"}), 400

    pipeline = _get_venue_pipeline(venue)
    if not pipeline:
        return jsonify({"error": f"venue '{venue}' not found"}), 404

    window = body.get("window", 5)
    if window != "sentence":
        window = int(window)
    measure = body.get("measure", "llr")
    min_freq = int(body.get("min_freq", 3))
    min_score = float(body.get("min_score", 0))
    top_n = int(body.get("top_n", 100))

    result = pipeline.collocation(
        window=window, measure=measure,
        min_freq=min_freq, min_score=min_score, top_n=top_n
    )
    return jsonify(result)


@app.route("/api/yuqing/network", methods=["POST"])
def yuqing_network():
    """Build semantic network and return vis.js JSON."""
    body = request.get_json(silent=True) or {}
    venue = body.get("venue", "").strip()
    if not venue:
        return jsonify({"error": "venue is required"}), 400

    pipeline = _get_venue_pipeline(venue)
    if not pipeline:
        return jsonify({"error": f"venue '{venue}' not found"}), 404

    window = body.get("window", 5)
    if window != "sentence":
        window = int(window)
    measure = body.get("measure", "llr")
    min_freq = int(body.get("min_freq", 3))
    min_score = float(body.get("min_score", 0))
    top_n = int(body.get("top_n", 80))

    result = pipeline.network(
        window=window, measure=measure,
        min_freq=min_freq, min_score=min_score, top_n=top_n
    )
    return jsonify(result)


@app.route("/api/yuqing/kwic", methods=["POST"])
def yuqing_kwic():
    """KWIC concordance search — supports single or dual term co-occurrence."""
    body = request.get_json(silent=True) or {}
    venue = body.get("venue", "").strip()
    term1 = body.get("term1", "").strip()
    term2 = body.get("term2", "").strip()
    if not venue or not term1:
        return jsonify({"error": "venue and term1 are required"}), 400

    pipeline = _get_venue_pipeline(venue)
    if not pipeline:
        return jsonify({"error": f"venue '{venue}' not found"}), 404

    window = max(10, min(int(body.get("window", 80)), 500))
    results = pipeline.concordance_search(term1, term2, window)
    return jsonify({
        "venue": venue, "term1": term1, "term2": term2,
        "total": len(results), "matches": results,
    })


@app.route("/api/yuqing/pos-collocates", methods=["POST"])
def yuqing_pos_collocates():
    """POS-based collocation analysis for a keyword."""
    body = request.get_json(silent=True) or {}
    venue = body.get("venue", "").strip()
    keyword = body.get("keyword", "").strip()
    if not venue or not keyword:
        return jsonify({"error": "venue and keyword are required"}), 400

    pipeline = _get_venue_pipeline(venue)
    if not pipeline:
        return jsonify({"error": f"venue '{venue}' not found"}), 404

    window = int(body.get("window", 5))
    result = pipeline.pos_collocation(keyword, window=window)
    return jsonify({"keyword": keyword, "venue": venue, "pos_collocates": result})


@app.route("/api/yuqing/vocabulary", methods=["POST"])
def yuqing_vocabulary():
    """Get vocabulary for autocomplete."""
    body = request.get_json(silent=True) or {}
    venue = body.get("venue", "").strip()
    if not venue:
        return jsonify({"error": "venue is required"}), 400

    pipeline = _get_venue_pipeline(venue)
    if not pipeline:
        return jsonify({"error": f"venue '{venue}' not found"}), 404

    min_freq = int(body.get("min_freq", 3))
    vocab = pipeline.vocabulary(min_freq=min_freq)
    return jsonify({"venue": venue, "vocabulary": vocab[:200]})


@app.route("/api/yuqing/compare", methods=["POST"])
def yuqing_compare():
    """Compare multiple venues with same parameters."""
    body = request.get_json(silent=True) or {}
    venues = body.get("venues", [])
    if not venues or len(venues) < 2:
        return jsonify({"error": "at least 2 venues required"}), 400

    window = body.get("window", 5)
    if window != "sentence":
        window = int(window)
    measure = body.get("measure", "llr")
    min_freq = int(body.get("min_freq", 3))
    min_score = float(body.get("min_score", 0))
    top_n = int(body.get("top_n", 80))

    results = []
    for venue in venues:
        pipeline = _get_venue_pipeline(venue)
        if not pipeline:
            continue
        net = pipeline.network(
            window=window, measure=measure,
            min_freq=min_freq, min_score=min_score, top_n=top_n
        )
        results.append(net)

    return jsonify({"comparison": results, "params": {
        "window": window, "measure": measure,
        "min_freq": min_freq, "min_score": min_score, "top_n": top_n,
    }})


@app.route("/api/yuqing/clear-cache", methods=["POST"])
def yuqing_clear_cache():
    """Clear NLP pipeline cache."""
    body = request.get_json(silent=True) or {}
    venue = body.get("venue")
    clear_cache(venue)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    os.makedirs(config.DATA_DIR, exist_ok=True)
    logger.info("Starting API server on port %d", config.API_PORT)
    app.run(host=config.API_HOST, port=config.API_PORT, debug=False, threaded=True)
