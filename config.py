import os

# Scraping limits
MAX_REVIEWS = 0  # 0 = scrape all reviews (auto-detect from page)

# Human behavior delay ranges (seconds)
MIN_DELAY = 0.5
MAX_DELAY = 3.0

# API config
API_PORT = 5002
API_HOST = "0.0.0.0"

# Data storage
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "results")
# Vercel's filesystem is read-only; use /tmp for the database
IS_VERCEL = os.environ.get("VERCEL", False)
DB_PATH  = "/tmp/reviews.db" if IS_VERCEL else os.path.join(BASE_DIR, "reviews.db")

# Selenium config
HEADLESS = False
PAGE_LOAD_TIMEOUT = 30
IMPLICIT_WAIT = 10

# Cookie injection: path to a Netscape cookies.txt exported from your browser
# Leave empty ("") to disable
COOKIE_FILE = "/Users/huanglijue/Downloads/cookies.txt"

# User agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]

# Common viewport sizes
VIEWPORT_SIZES = [
    (1920, 1080),
    (1440, 900),
    (1366, 768),
    (1280, 800),
    (1600, 900),
]
