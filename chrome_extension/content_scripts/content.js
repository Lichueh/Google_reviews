/**
 * content.js — runs on https://www.google.com/maps/*
 *
 * Detects when the user is viewing a specific place page, extracts
 * the place name and URL, then notifies the service worker.
 */

(function () {
  "use strict";

  const PLACE_URL_PATTERN = /\/maps\/place\//;

  function isPlacePage(url) {
    return PLACE_URL_PATTERN.test(url);
  }

  function extractPlaceName() {
    // Try the main heading first
    const heading = document.querySelector("h1.DUwDvf, h1.fontHeadlineLarge");
    if (heading && heading.textContent.trim()) {
      return heading.textContent.trim();
    }

    // Fall back to document title: "Place Name - Google Maps"
    const title = document.title;
    if (title.includes(" - Google Maps")) {
      return title.replace(" - Google Maps", "").trim();
    }

    return "";
  }

  function safeSendMessage(msg) {
    // Guard against "Extension context invalidated" after extension reload
    try {
      if (chrome.runtime?.id) {
        chrome.runtime.sendMessage(msg).catch(() => {});
      }
    } catch (_) {}
  }

  function notifyServiceWorker(placeName, url) {
    safeSendMessage({
      type: "PLACE_DETECTED",
      placeName: placeName,
      url: url,
    });
  }

  function checkAndNotify() {
    const url = window.location.href;
    if (isPlacePage(url)) {
      const placeName = extractPlaceName();
      if (placeName) {
        notifyServiceWorker(placeName, url);
      }
    } else {
      safeSendMessage({ type: "NOT_A_PLACE_PAGE" });
    }
  }

  // Run on initial load
  checkAndNotify();

  // Watch for SPA navigation (Google Maps is a single-page app)
  let lastUrl = window.location.href;
  const observer = new MutationObserver(() => {
    const currentUrl = window.location.href;
    if (currentUrl !== lastUrl) {
      lastUrl = currentUrl;
      // Give the page a moment to update the DOM
      setTimeout(checkAndNotify, 1200);
    }
  });

  observer.observe(document.body, { childList: true, subtree: true });
})();
