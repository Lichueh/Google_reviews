import logging
import random
import re
import time
import urllib.parse

from seleniumbase import SB

import config
from scraper.human_behavior import (
    human_type,
    occasional_pause,
    pre_click_behavior,
    random_sleep,
)
from scraper.data_manager import build_place_record, build_review_record, review_fingerprint

logger = logging.getLogger(__name__)

# CSS selectors for Google Maps reviews (2025-2026 layout)
SEL_REVIEW_CONTAINER = "div.m6QErb.DxyBCb.kA9KIf.dS8AEf"  # scrollable panel
SEL_REVIEW_ITEM = "div.jftiEf"                               # individual review card
SEL_REVIEWER_NAME = "div.d4r55"
SEL_RATING = "span.kvMYJc"                                   # aria-label="X stars"
SEL_DATE = "span.rsqaWe"
SEL_REVIEW_TEXT = "span.wiI7pd"
SEL_MORE_BTN = "button.w8nwRe"                               # "More" expand button
SEL_SORT_BTN = "button[data-value='Sort']"
SEL_SORT_NEWEST = "div[data-index='1']"                      # Newest option in sort menu
SEL_REVIEWS_TAB = "button[aria-label*='review'], button[data-tab-index='1']"


class GoogleMapsScraper:
    """
    Google Maps review scraper using SeleniumBase UC Mode.

    UC Mode patches ChromeDriver to bypass Google's bot-detection
    (navigator.webdriver removal, fingerprint randomisation, etc.).
    """

    EARLY_STOP_STREAK = 5
    MAX_STALLS = 20

    def __init__(self, headless: bool = True, progress_callback=None, cookie_file: str = "",
                 checkpoint_callback=None, checkpoint_every: int = 50):
        self.headless = headless
        self.progress_callback = progress_callback
        self.cookie_file = cookie_file
        self.checkpoint_callback = checkpoint_callback   # callable(place_name, place_url, place_id, batch)
        self.checkpoint_every = checkpoint_every
        self._sb_cm = None   # SB() instance (owns __exit__)
        self._driver = None  # BaseCase returned by __enter__

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self):
        # UC Mode: uc=True bypasses Selenium detection
        # Keep reference to SB instance for __exit__; __enter__ returns BaseCase
        self._sb_cm = SB(uc=True, headless=self.headless, test=False)
        self._driver = self._sb_cm.__enter__()
        logger.info("SeleniumBase UC Mode started (headless=%s)", self.headless)
        if self.cookie_file:
            self._load_cookies_from_file(self.cookie_file)
        return self

    def __exit__(self, *args):
        if self._sb_cm:
            self._sb_cm.__exit__(*args)

    # ------------------------------------------------------------------
    # Cookie injection
    # ------------------------------------------------------------------

    def _load_cookies_from_file(self, cookie_file: str):
        """Parse a Netscape cookies.txt and inject google.com cookies into the browser."""
        import os
        if not os.path.exists(cookie_file):
            logger.warning("Cookie file not found: %s", cookie_file)
            return

        # Must be on google.com before setting cookies
        self._driver.uc_open_with_reconnect("https://www.google.com", reconnect_time=3)
        random_sleep(2, 3)

        loaded = 0
        with open(cookie_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) < 7:
                    continue
                domain, _, path, secure, expiry, name, value = (
                    parts[0], parts[1], parts[2], parts[3], parts[4], parts[5], "\t".join(parts[6:])
                )
                if "google.com" not in domain:
                    continue
                cookie: dict = {"name": name, "value": value, "path": path, "secure": secure == "TRUE"}
                try:
                    expiry_int = int(expiry)
                    if expiry_int > 0:
                        cookie["expiry"] = expiry_int
                except ValueError:
                    pass
                try:
                    self._driver.add_cookie(cookie)
                    loaded += 1
                except Exception as e:
                    logger.debug("Skipped cookie %s: %s", name, e)

        logger.info("Injected %d Google cookies from %s", loaded, cookie_file)
        self._driver.refresh()
        random_sleep(2, 3)

    # ------------------------------------------------------------------
    # Public scrape methods
    # ------------------------------------------------------------------

    def search_place(self, name: str, max_reviews: int = None, existing_fingerprints: set = None) -> dict:
        """Search Google Maps for a place by name and scrape reviews."""
        if max_reviews is None:
            max_reviews = config.MAX_REVIEWS
        logger.info("Searching for place: %s (max=%d)", name, max_reviews)

        search_url = f"https://www.google.com/maps/search/{urllib.parse.quote(name)}"
        self._driver.uc_open_with_reconnect(search_url, reconnect_time=5)
        random_sleep(3, 5)

        # If results list appears, click the first result
        try:
            self._driver.click(".Nv2PK:first-child", timeout=6)
            random_sleep(2, 4)
        except Exception:
            pass  # Navigated directly to place page

        return self._scrape_current_place(
            max_reviews=max_reviews,
            place_name=name,
            existing_fingerprints=existing_fingerprints,
        )

    def scrape_from_url(self, url: str, max_reviews: int = None, place_name: str = "",
                        existing_fingerprints: set = None) -> dict:
        """Navigate directly to a Google Maps URL and scrape reviews."""
        if max_reviews is None:
            max_reviews = config.MAX_REVIEWS

        logger.info("Scraping from URL: %s", url)
        self._driver.uc_open_with_reconnect(url, reconnect_time=3)
        random_sleep(3, 5)

        return self._scrape_current_place(
            max_reviews=max_reviews,
            place_name=place_name,
            existing_fingerprints=existing_fingerprints,
        )

    # ------------------------------------------------------------------
    # Core scraping logic
    # ------------------------------------------------------------------

    def _scrape_current_place(self, max_reviews: int, place_name: str = "",
                               existing_fingerprints: set = None) -> dict:
        # Always try to extract the real place name from the page;
        # fall back to the caller-provided name only if extraction fails.
        extracted = self._extract_place_name()
        if extracted:
            place_name = extracted
        elif not place_name:
            place_name = "unknown"

        place_url = self._driver.get_current_url()
        place_id = self._extract_place_id(place_url)
        logger.info("Place: %s  id=%s", place_name, place_id)

        # Detect total review count from reviews tab aria-label
        total_on_page = self._extract_total_review_count()
        if total_on_page:
            logger.info("Total reviews on page: %d", total_on_page)

        # max_reviews=0 means "scrape all" — use detected count or just scroll to the end
        if max_reviews <= 0:
            max_reviews = total_on_page if total_on_page else 99999
            logger.info("Scrape-all mode: target set to %d", max_reviews)

        self._open_reviews_tab()
        random_sleep(1.5, 2.5)
        self._sort_by_newest()
        random_sleep(1.5, 2.5)

        # Build checkpoint closure with place context baked in
        checkpoint_fn = None
        if self.checkpoint_callback:
            _pname, _purl, _pid = place_name, place_url, place_id
            def checkpoint_fn(batch):
                self.checkpoint_callback(_pname, _purl, _pid, batch)

        reviews_data = self.load_all_reviews(
            max_reviews, existing_fingerprints=existing_fingerprints,
            checkpoint_fn=checkpoint_fn,
        )

        return build_place_record(
            place_name=place_name,
            place_url=place_url,
            reviews=reviews_data,
            place_id=place_id,
        )

    def _extract_place_name(self) -> str:
        try:
            name = self._driver.get_text("h1.DUwDvf")
            if name:
                return name
        except Exception:
            pass
        title = self._driver.get_title()
        # Strip common Google Maps suffixes
        for suffix in [" - Google Maps", " - Google 地圖", " – Google Maps", " – Google 地圖"]:
            title = title.replace(suffix, "")
        return title.strip()

    def _extract_place_id(self, url: str) -> str:
        match = re.search(r"!1s(ChIJ[^!]+)", url)
        if match:
            return match.group(1)
        match = re.search(r"place/[^/]+/([^/?]+)", url)
        if match:
            return match.group(1)
        return ""

    def _extract_total_review_count(self) -> int | None:
        """Extract total review count from the page using aria-label on the reviews tab."""
        # Only use the reviews tab aria-label — it's the most reliable source.
        # e.g. aria-label="評論，1,036 則" or "Reviews, 1,036"
        try:
            for sel in ['button[aria-label*="評論"]', 'button[aria-label*="review" i]']:
                try:
                    el = self._driver.find_element("css selector", sel)
                    label = el.get_attribute("aria-label") or ""
                    # Extract all digit groups, pick the largest
                    nums = re.findall(r"[\d,]+", label)
                    for n in nums:
                        val = int(n.replace(",", ""))
                        if val > 10:
                            logger.info("Review count from tab aria-label '%s': %d", label, val)
                            return val
                except Exception:
                    continue
        except Exception:
            pass
        return None

    def _open_reviews_tab(self):
        """Click the Reviews tab (handles English, Chinese, and food-ordering layouts)."""
        selectors = [
            'button[aria-label*="評論"]',                      # Chinese tab: 評論
            'button[aria-label*="review" i]',                  # English tab: Reviews
            'button[aria-label*="所有評論"]',                   # "所有評論" button
            'button[aria-label*="all review" i]',              # "See all reviews"
            'div.F7nice',                                       # Star rating summary (click → jumps to reviews)
            'span.ceNzKf[aria-label*="顆星"]',                  # Star icon
            'button[data-tab-index="1"]',                       # Generic tab index fallback
        ]
        for sel in selectors:
            try:
                self._driver.click(sel, timeout=5)
                logger.debug("Reviews tab clicked via: %s", sel)
                random_sleep(1.0, 2.0)
                return
            except Exception:
                continue
        logger.debug("Reviews tab not found; assuming already visible")

    def _sort_by_newest(self):
        """Sort reviews by newest first so incremental updates stop early.

        Critical for scraping all reviews — the default 'Most relevant' sort
        only lazy-loads ~200 items, while 'Newest' loads all.
        """
        sort_btn_selectors = [
            SEL_SORT_BTN,                                      # button[data-value='Sort']
            'button[aria-label*="排序"]',                       # Chinese: 排序
            'button[aria-label*="sort" i]',                     # English: Sort
            'button[aria-label*="Sort reviews"]',               # English variant
        ]
        # Also try XPath for text-based matching
        sort_btn_xpaths = [
            '//button[contains(@aria-label, "排序")]',
            '//button[.//span[text()="排序"]]',
            '//button[.//span[text()="Sort"]]',
        ]

        clicked = False
        for sel in sort_btn_selectors:
            try:
                self._driver.click(sel, timeout=4)
                clicked = True
                logger.debug("Sort button clicked via CSS: %s", sel)
                break
            except Exception:
                continue

        if not clicked:
            for xp in sort_btn_xpaths:
                try:
                    el = self._driver.find_element("xpath", xp)
                    self._driver.execute_script("arguments[0].click();", el)
                    clicked = True
                    logger.debug("Sort button clicked via XPath: %s", xp)
                    break
                except Exception:
                    continue

        if not clicked:
            logger.warning("Sort button not found — will use default sort (may limit results)")
            return

        random_sleep(0.8, 1.5)

        # Click "Newest" option in the dropdown
        newest_selectors = [
            SEL_SORT_NEWEST,                                   # div[data-index='1']
            'div[role="menuitemradio"][data-index="1"]',        # menuitem variant
        ]
        newest_xpaths = [
            '//div[@role="menuitemradio" and contains(., "最新")]',
            '//div[@role="menuitemradio" and contains(., "Newest")]',
            '//div[@data-index="1"]',
        ]

        for sel in newest_selectors:
            try:
                self._driver.click(sel, timeout=4)
                logger.debug("Sorted by newest via CSS: %s", sel)
                random_sleep(1.0, 2.0)
                return
            except Exception:
                continue

        for xp in newest_xpaths:
            try:
                el = self._driver.find_element("xpath", xp)
                self._driver.execute_script("arguments[0].click();", el)
                logger.debug("Sorted by newest via XPath: %s", xp)
                random_sleep(1.0, 2.0)
                return
            except Exception:
                continue

        logger.warning("Newest sort option not found")

    # ------------------------------------------------------------------
    # Review loading (scrolling)
    # ------------------------------------------------------------------

    def load_all_reviews(self, max_reviews: int, existing_fingerprints: set = None,
                         checkpoint_fn=None) -> list:
        logger.info(
            "Loading up to %d reviews (update_mode=%s, checkpoint_every=%d)...",
            max_reviews,
            existing_fingerprints is not None,
            self.checkpoint_every if checkpoint_fn else 0,
        )

        stall_count = 0
        MAX_STALLS = self.MAX_STALLS
        known_streak = 0
        dom_count = 0          # last seen DOM element count
        parsed_reviews = []    # accumulate parsed dicts incrementally
        last_checkpoint = 0    # index into parsed_reviews at last flush

        while stall_count < MAX_STALLS:
            self._expand_more_buttons()
            self._scroll_reviews_panel()

            raw_items = self._get_review_items()
            current_count = len(raw_items)

            if current_count > dom_count:
                stall_count = 0

                # Parse only the newly visible items
                for item in raw_items[dom_count:current_count]:
                    parsed = self._parse_item(item)
                    if not parsed:
                        continue

                    # Update-mode early stop: track consecutive known reviews
                    if existing_fingerprints is not None:
                        if review_fingerprint(parsed) in existing_fingerprints:
                            known_streak += 1
                        else:
                            known_streak = 0

                    parsed_reviews.append(parsed)

                dom_count = current_count
                logger.debug("Loaded %d / %d (parsed %d)", dom_count, max_reviews, len(parsed_reviews))

                if self.progress_callback:
                    self.progress_callback(min(len(parsed_reviews), max_reviews), max_reviews)

                # Checkpoint flush every N parsed reviews
                if checkpoint_fn and len(parsed_reviews) - last_checkpoint >= self.checkpoint_every:
                    batch = parsed_reviews[last_checkpoint:]
                    try:
                        checkpoint_fn(batch)
                        logger.info("Checkpoint: flushed %d reviews (total parsed %d)",
                                    len(batch), len(parsed_reviews))
                    except Exception as cp_err:
                        logger.warning("Checkpoint failed: %s", cp_err)
                    last_checkpoint = len(parsed_reviews)

                if existing_fingerprints is not None and known_streak >= self.EARLY_STOP_STREAK:
                    logger.info("Early stop: %d consecutive known reviews", known_streak)
                    break

                if len(parsed_reviews) >= max_reviews:
                    break
            else:
                stall_count += 1

            random_sleep(config.MIN_DELAY, config.MAX_DELAY)
            occasional_pause()

            if self._reached_end():
                logger.info("Reached end of reviews")
                break

        # Final checkpoint for any remaining unpersisted reviews
        if checkpoint_fn and len(parsed_reviews) > last_checkpoint:
            batch = parsed_reviews[last_checkpoint:]
            try:
                checkpoint_fn(batch)
                logger.info("Final checkpoint: flushed %d reviews", len(batch))
            except Exception as cp_err:
                logger.warning("Final checkpoint failed: %s", cp_err)

        return parsed_reviews[:max_reviews]

    def _get_review_items(self) -> list:
        """Return raw text blocks for each review card."""
        try:
            return self._driver.find_elements("css selector", SEL_REVIEW_ITEM)
        except Exception:
            return []

    def _scroll_reviews_panel(self):
        """Trigger Google Maps lazy-load with a trusted browser wheel action.

        Synthetic JS WheelEvents have isTrusted=false and are ignored by Google Maps.
        Selenium 4 ActionChains.scroll_from_origin() goes through the WebDriver
        protocol and produces isTrusted=true events that Google Maps accepts.
        """
        from selenium.webdriver import ActionChains
        from selenium.webdriver.common.actions.wheel_input import ScrollOrigin

        try:
            items = self._driver.find_elements("css selector", SEL_REVIEW_ITEM)
            if items:
                last = items[-1]
                # Scroll the last item into view first so the wheel origin is visible
                self._driver.execute_script(
                    "arguments[0].scrollIntoView({behavior: 'instant', block: 'center'});",
                    last,
                )
                time.sleep(0.3)
                origin = ScrollOrigin.from_element(last)
                ActionChains(self._driver.driver).scroll_from_origin(
                    origin, 0, 600
                ).perform()
                logger.debug("ActionChains wheel scroll on item #%d", len(items))
                time.sleep(random.uniform(2.0, 3.0))
                return
        except Exception as e:
            logger.debug("ActionChains scroll failed: %s", e)

        self._driver.execute_script("window.scrollBy(0, 800);")

    def _expand_more_buttons(self):
        """Click all 'More' buttons to expand truncated review text."""
        try:
            btns = self._driver.find_elements("css selector", SEL_MORE_BTN)
            for btn in btns:
                try:
                    self._driver.execute_script("arguments[0].click();", btn)
                    time.sleep(random.uniform(0.05, 0.15))
                except Exception:
                    pass
        except Exception:
            pass

    def _reached_end(self) -> bool:
        try:
            page_src = self._driver.get_page_source()
            return (
                "You've seen all the reviews" in page_src
                or "No more reviews" in page_src
                or "沒有更多評論" in page_src
            )
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Review parsing
    # ------------------------------------------------------------------

    def _parse_item(self, el) -> dict | None:
        """Extract fields from a single review Selenium element."""
        try:
            # Reviewer name
            name = self._el_text(el, SEL_REVIEWER_NAME)
            if not name:
                return None

            # Rating: aria-label="X stars"
            rating = None
            try:
                star_el = el.find_element("css selector", SEL_RATING)
                aria = star_el.get_attribute("aria-label") or ""
                m = re.search(r"(\d+)", aria)
                if m:
                    rating = int(m.group(1))
            except Exception:
                pass

            # Date
            date = self._el_text(el, SEL_DATE)

            # Review text
            text = self._el_text(el, SEL_REVIEW_TEXT)

            # Photos
            photo_els = el.find_elements("css selector", "button.Tya61d img, .KtCyie img")
            photo_urls = []
            for img in photo_els:
                src = img.get_attribute("src") or ""
                if src.startswith("http"):
                    photo_urls.append(src)

            return build_review_record(
                reviewer_name=name,
                rating=rating,
                date=date,
                text=text,
                photos_count=len(photo_urls),
                photo_urls=photo_urls,
            )
        except Exception:
            return None

    def _el_text(self, parent, selector: str) -> str | None:
        try:
            el = parent.find_element("css selector", selector)
            t = el.text.strip()
            return t if t else None
        except Exception:
            return None
