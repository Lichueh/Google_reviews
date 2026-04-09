/**
 * service_worker.js — Manifest V3 background service worker
 *
 * Acts as message broker between content.js and popup.js.
 * Stores the current detected place in chrome.storage.session.
 */

"use strict";

const API_BASE = "http://localhost:5002";

// -------------------------------------------------------------------------
// Message handling
// -------------------------------------------------------------------------

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.type) {
    case "PLACE_DETECTED":
      handlePlaceDetected(message, sender);
      sendResponse({ ok: true });
      break;

    case "NOT_A_PLACE_PAGE":
      chrome.storage.session.remove("currentPlace");
      sendResponse({ ok: true });
      break;

    case "GET_CURRENT_PLACE":
      chrome.storage.session.get("currentPlace", (result) => {
        sendResponse({ place: result.currentPlace || null });
      });
      return true; // keep channel open for async sendResponse

    case "START_SCRAPE":
      startScrapeJob(message.payload, sendResponse);
      return true;

    case "GET_STATUS":
      pollJobStatus(message.jobId, sendResponse);
      return true;

    case "GET_RESULTS":
      fetchJobResults(message.jobId, sendResponse);
      return true;

    default:
      sendResponse({ error: "Unknown message type" });
  }
});

// -------------------------------------------------------------------------
// Place detection
// -------------------------------------------------------------------------

function handlePlaceDetected(message, sender) {
  const place = {
    name: message.placeName,
    url: message.url,
    tabId: sender.tab?.id,
  };
  chrome.storage.session.set({ currentPlace: place });
  console.log("[SW] Place detected:", place.name);
}

// -------------------------------------------------------------------------
// API communication
// -------------------------------------------------------------------------

async function startScrapeJob(payload, sendResponse) {
  /**
   * payload: { mode: 'search'|'url', placeName?, url?, maxReviews }
   */
  const endpoint =
    payload.mode === "search"
      ? `${API_BASE}/api/scrape/search`
      : `${API_BASE}/api/scrape/url`;

  const body =
    payload.mode === "search"
      ? { place_name: payload.placeName, max_reviews: payload.maxReviews }
      : { url: payload.url, max_reviews: payload.maxReviews, place_name: payload.placeName || "" };

  try {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: res.statusText }));
      sendResponse({ error: err.error || "API error" });
      return;
    }

    const data = await res.json();
    sendResponse({ jobId: data.job_id, status: data.status });
  } catch (e) {
    sendResponse({ error: `Cannot reach backend: ${e.message}` });
  }
}

async function pollJobStatus(jobId, sendResponse) {
  try {
    const res = await fetch(`${API_BASE}/api/status/${jobId}`);
    const data = await res.json();
    sendResponse(data);
  } catch (e) {
    sendResponse({ error: `Status poll failed: ${e.message}` });
  }
}

async function fetchJobResults(jobId, sendResponse) {
  try {
    const res = await fetch(`${API_BASE}/api/results/${jobId}`);
    const data = await res.json();
    sendResponse(data);
  } catch (e) {
    sendResponse({ error: `Results fetch failed: ${e.message}` });
  }
}
