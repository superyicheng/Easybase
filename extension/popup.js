// Easybase Browser Extension — Popup Script

const DEFAULT_URL = "http://127.0.0.1:8372";

document.addEventListener("DOMContentLoaded", () => {
  const urlInput = document.getElementById("server-url");
  const saveBtn = document.getElementById("save-btn");
  const testBtn = document.getElementById("test-btn");
  const statusDot = document.getElementById("status-dot");
  const statusText = document.getElementById("status-text");

  // Load saved URL
  chrome.storage.local.get(["serverUrl"], (result) => {
    urlInput.value = result.serverUrl || DEFAULT_URL;
  });

  // Check status on open
  checkStatus();

  // Save URL
  saveBtn.addEventListener("click", () => {
    const url = urlInput.value.trim() || DEFAULT_URL;
    chrome.storage.local.set({ serverUrl: url }, () => {
      statusText.textContent = "Saved.";
      checkStatus();
    });
  });

  // Test connection
  testBtn.addEventListener("click", () => {
    checkStatus();
  });

  function checkStatus() {
    statusText.textContent = "Checking...";
    statusDot.className = "dot dot-unknown";

    chrome.runtime.sendMessage({ action: "status" }, (response) => {
      if (chrome.runtime.lastError) {
        statusDot.className = "dot dot-error";
        statusText.textContent = "Extension error";
        return;
      }
      if (response && response.ok) {
        statusDot.className = "dot dot-ok";
        statusText.textContent = `Connected — ${response.chunks} chunks` +
          (response.name ? ` (${response.name})` : "");
      } else {
        statusDot.className = "dot dot-error";
        statusText.textContent = response?.error || "Server not reachable";
      }
    });
  }
});
