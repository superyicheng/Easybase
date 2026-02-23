// Easybase Browser Extension — Service Worker
// Handles communication between content scripts and the local HTTP server.

const DEFAULT_URL = "http://127.0.0.1:8372";

async function getServerUrl() {
  const result = await chrome.storage.local.get(["serverUrl"]);
  return result.serverUrl || DEFAULT_URL;
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "load") {
    handleLoad(message.query, message.top_k).then(sendResponse);
    return true;
  }
  if (message.action === "search") {
    handleSearch(message.query).then(sendResponse);
    return true;
  }
  if (message.action === "respond") {
    handleRespond(message.text).then(sendResponse);
    return true;
  }
  if (message.action === "status") {
    handleStatus().then(sendResponse);
    return true;
  }
});

async function handleLoad(query, topK = 10) {
  try {
    const url = await getServerUrl();
    const params = new URLSearchParams({ query, top_k: topK });
    const resp = await fetch(`${url}/api/load?${params}`);
    if (!resp.ok) {
      const text = await resp.text();
      return { error: text };
    }
    return { context: await resp.text() };
  } catch (e) {
    return {
      error: "Cannot reach Easybase server.\n\nMake sure http_server.py is running:\n  python3 http_server.py"
    };
  }
}

async function handleSearch(query) {
  try {
    const url = await getServerUrl();
    const params = new URLSearchParams({ query });
    const resp = await fetch(`${url}/api/search?${params}`);
    return await resp.json();
  } catch (e) {
    return { error: e.message };
  }
}

async function handleRespond(text) {
  try {
    const url = await getServerUrl();
    const resp = await fetch(`${url}/api/respond`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    return await resp.json();
  } catch (e) {
    return { error: e.message };
  }
}

async function handleStatus() {
  try {
    const url = await getServerUrl();
    const resp = await fetch(`${url}/api/status`);
    return await resp.json();
  } catch (e) {
    return { ok: false, error: "Server not reachable" };
  }
}
