/**
 * popup.js — UI logic for the Reviews Scraper popup
 *
 * Flow:
 *  1. On open: check backend health, ask SW for current detected place
 *  2. User clicks Scrape → SW starts job via Flask API
 *  3. Poll /api/status every 2s → update progress bar
 *  4. On done → show Download JSON button
 */

"use strict";

const API_BASE = "http://localhost:5002";
const POLL_INTERVAL_MS = 2000;

// -------------------------------------------------------------------------
// DOM refs
// -------------------------------------------------------------------------

const backendBadge     = document.getElementById("backend-status");
const detectedDiv      = document.getElementById("detected-place");
const detectedName     = document.getElementById("detected-place-name");
const placeInput       = document.getElementById("place-input");
const maxReviewsInput  = document.getElementById("max-reviews");
const scrapeBtn        = document.getElementById("scrape-btn");
const progressSection  = document.getElementById("progress-section");
const progressText     = document.getElementById("progress-text");
const progressCount    = document.getElementById("progress-count");
const progressBar      = document.getElementById("progress-bar");
const resultSection    = document.getElementById("result-section");
const resultSummary    = document.getElementById("result-summary");
const downloadBtn      = document.getElementById("download-btn");
const errorSection     = document.getElementById("error-section");
const errorMsg         = document.getElementById("error-msg");

// -------------------------------------------------------------------------
// State
// -------------------------------------------------------------------------

let currentJobId    = null;
let pollTimer       = null;
let currentPlace    = null;   // { name, url } from service worker
let resultData      = null;   // full scraped JSON

// -------------------------------------------------------------------------
// Initialisation
// -------------------------------------------------------------------------

(async function init() {
  await checkBackendHealth();
  await loadCurrentPlace();
  scrapeBtn.addEventListener("click", onScrapeClick);
  downloadBtn.addEventListener("click", onDownloadClick);
  placeInput.addEventListener("input", () => enableScrapeIfReady());
})();

// -------------------------------------------------------------------------
// Backend health
// -------------------------------------------------------------------------

async function checkBackendHealth() {
  try {
    const res = await fetch(`${API_BASE}/api/health`, { signal: AbortSignal.timeout(3000) });
    if (res.ok) {
      setBadge("online", "Backend online");
      scrapeBtn.disabled = false;
    } else {
      setBadge("offline", "Backend error");
    }
  } catch {
    setBadge("offline", "Backend offline");
    showError("Cannot reach backend. Start the server with: python api_server.py");
  }
}

function setBadge(state, text) {
  backendBadge.textContent = text;
  backendBadge.className = `badge badge-${state}`;
}

// -------------------------------------------------------------------------
// Place detection
// -------------------------------------------------------------------------

async function loadCurrentPlace() {
  try {
    const response = await chrome.runtime.sendMessage({ type: "GET_CURRENT_PLACE" });
    if (response?.place) {
      currentPlace = response.place;
      detectedName.textContent = currentPlace.name;
      detectedDiv.classList.remove("hidden");
      placeInput.value = currentPlace.name;
      placeInput.placeholder = "Auto-detected (override below)";
    }
  } catch (e) {
    // Service worker may not be ready yet; that's fine
    console.warn("Could not load current place:", e);
  }
}

function enableScrapeIfReady() {
  const val = placeInput.value.trim();
  scrapeBtn.disabled = val.length === 0;
}

// -------------------------------------------------------------------------
// Scrape action
// -------------------------------------------------------------------------

async function onScrapeClick() {
  const input = placeInput.value.trim();
  const maxReviews = parseInt(maxReviewsInput.value, 10) || 0;  // 0 = scrape all
  const updateMode = document.getElementById("update-mode").checked;

  if (!input) return;

  // Reset UI
  hideAll();
  progressSection.classList.remove("hidden");
  scrapeBtn.disabled = true;
  setProgress(0, maxReviews, "Starting scraper...");

  // Determine mode: URL vs search
  const isUrl = input.includes("google.com/maps") || input.includes("maps.google.com");

  const payload = isUrl
    ? { mode: "url", url: input, placeName: currentPlace?.name || "", maxReviews, update: updateMode }
    : { mode: "search", placeName: input, maxReviews, update: updateMode };

  try {
    const response = await chrome.runtime.sendMessage({ type: "START_SCRAPE", payload });

    if (response?.error) {
      showError(response.error);
      scrapeBtn.disabled = false;
      return;
    }

    currentJobId = response.jobId;
    startPolling();
  } catch (e) {
    showError(`Failed to start scrape: ${e.message}`);
    scrapeBtn.disabled = false;
  }
}

// -------------------------------------------------------------------------
// Polling
// -------------------------------------------------------------------------

function startPolling() {
  clearInterval(pollTimer);
  pollTimer = setInterval(pollStatus, POLL_INTERVAL_MS);
}

async function pollStatus() {
  if (!currentJobId) return;

  try {
    const status = await chrome.runtime.sendMessage({
      type: "GET_STATUS",
      jobId: currentJobId,
    });

    if (status?.error) {
      stopPolling();
      showError(status.error);
      scrapeBtn.disabled = false;
      return;
    }

    const { progress, total, status: jobStatus } = status;

    switch (jobStatus) {
      case "queued":
        setProgress(0, total, "Queued...");
        break;

      case "running":
        setProgress(progress, total, "Scraping reviews...");
        break;

      case "done":
        stopPolling();
        setProgress(total, total, "Done!");
        await fetchAndShowResults();
        break;

      case "error":
        stopPolling();
        showError(status.error || "Unknown scrape error");
        scrapeBtn.disabled = false;
        break;
    }
  } catch (e) {
    console.error("Poll error:", e);
  }
}

function stopPolling() {
  clearInterval(pollTimer);
  pollTimer = null;
}

// -------------------------------------------------------------------------
// Results
// -------------------------------------------------------------------------

async function fetchAndShowResults() {
  try {
    const response = await chrome.runtime.sendMessage({
      type: "GET_RESULTS",
      jobId: currentJobId,
    });

    if (response?.error) {
      showError(response.error);
      return;
    }

    resultData = response.data;
    const count = resultData?.total_reviews_scraped ?? 0;
    const name  = resultData?.place_name ?? "Unknown place";

    resultSummary.textContent = `✓ ${count} reviews scraped for "${name}"`;
    resultSection.classList.remove("hidden");
    scrapeBtn.disabled = false;
  } catch (e) {
    showError(`Could not fetch results: ${e.message}`);
  }
}

// -------------------------------------------------------------------------
// Download
// -------------------------------------------------------------------------

function onDownloadClick() {
  if (!resultData) return;

  const blob = new Blob([JSON.stringify(resultData, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${sanitizeFilename(resultData.place_name)}_reviews.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function sanitizeFilename(name = "reviews") {
  return name.replace(/[^a-z0-9_\-]/gi, "_").slice(0, 60);
}

// -------------------------------------------------------------------------
// UI helpers
// -------------------------------------------------------------------------

function setProgress(current, total, label) {
  if (total > 0) {
    const pct = Math.min(100, Math.round((current / total) * 100));
    progressBar.style.width = `${pct}%`;
    progressCount.textContent = `${current} / ${total}`;
  } else {
    // Unknown total (scrape-all mode before detection)
    progressBar.style.width = current > 0 ? "50%" : "0%";
    progressCount.textContent = current > 0 ? `${current} loaded...` : "";
  }
  progressText.textContent = label;
}

function showError(message) {
  errorMsg.textContent = message;
  errorSection.classList.remove("hidden");
}

function hideAll() {
  progressSection.classList.add("hidden");
  resultSection.classList.add("hidden");
  errorSection.classList.add("hidden");
}
