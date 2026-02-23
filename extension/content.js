// Easybase Browser Extension — Content Script
// Injected into AI chat pages (ChatGPT, Claude.ai, Gemini).
// Adds a floating button that loads and injects Easybase context.
// Auto-captures AI responses and sends them to the local server.

(function () {
  "use strict";

  // Detect which AI platform we're on
  function detectPlatform() {
    const host = window.location.hostname;
    if (host.includes("chatgpt.com") || host.includes("chat.openai.com"))
      return "chatgpt";
    if (host.includes("claude.ai")) return "claude";
    if (host.includes("gemini.google.com") || host.includes("aistudio.google.com"))
      return "gemini";
    return null;
  }

  // Find the chat input element for each platform
  // These selectors may need updates as platforms change their UI
  function getInputElement(platform) {
    const selectors = {
      chatgpt: [
        'div#prompt-textarea[contenteditable="true"]',
        'textarea#prompt-textarea',
        'div[contenteditable="true"][data-placeholder]',
      ],
      claude: [
        'div[contenteditable="true"].ProseMirror',
        'div[contenteditable="true"][translate="no"]',
      ],
      gemini: [
        'div.ql-editor[contenteditable="true"]',
        'div[contenteditable="true"][aria-label]',
      ],
    };

    const platformSelectors = selectors[platform] || [];
    for (const sel of platformSelectors) {
      const el = document.querySelector(sel);
      if (el) return el;
    }
    return null;
  }

  // Set text in the input element
  function setInputText(element, text) {
    element.focus();

    if (element.tagName === "TEXTAREA") {
      // Standard textarea
      const nativeSetter = Object.getOwnPropertyDescriptor(
        window.HTMLTextAreaElement.prototype, "value"
      ).set;
      nativeSetter.call(element, text);
      element.dispatchEvent(new Event("input", { bubbles: true }));
    } else {
      // Contenteditable div
      // Create a paragraph with the text
      element.innerHTML = "";
      const p = document.createElement("p");
      p.textContent = text;
      element.appendChild(p);
      element.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }

  // Get current text from input element
  function getInputText(element) {
    if (element.tagName === "TEXTAREA") {
      return element.value;
    }
    return element.textContent || "";
  }

  const platform = detectPlatform();
  if (!platform) return;

  // --- Auto-capture: detect AI responses ---

  // Track whether we injected context (only capture responses after injection)
  let contextInjected = false;
  // Track captured responses to avoid duplicates
  let lastCapturedText = "";
  // Debounce timer for response completion detection
  let captureTimer = null;

  // Selectors for AI response messages on each platform
  function getResponseSelectors(platform) {
    return {
      chatgpt: {
        // ChatGPT: assistant messages contain markdown content
        container: '[data-message-author-role="assistant"]',
        content: ".markdown",
        // The streaming indicator (stop button visible = still streaming)
        streaming: 'button[aria-label="Stop streaming"]',
      },
      claude: {
        // Claude.ai: assistant messages
        container: '[data-is-streaming]',
        content: ".font-claude-message",
        streaming: '[data-is-streaming="true"]',
      },
      gemini: {
        // Gemini: model response turns
        container: "model-response",
        content: ".model-response-text",
        streaming: ".loading-indicator",
      },
    }[platform];
  }

  // Extract the last AI response text
  function getLastResponseText() {
    const sel = getResponseSelectors(platform);
    if (!sel) return null;

    const messages = document.querySelectorAll(sel.container);
    if (messages.length === 0) return null;

    const lastMsg = messages[messages.length - 1];
    const contentEl = sel.content
      ? lastMsg.querySelector(sel.content) || lastMsg
      : lastMsg;

    return contentEl.textContent?.trim() || null;
  }

  // Check if the AI is still streaming
  function isStreaming() {
    const sel = getResponseSelectors(platform);
    if (!sel || !sel.streaming) return false;
    return document.querySelector(sel.streaming) !== null;
  }

  // Send captured response to server
  function captureResponse(text) {
    if (!text || text === lastCapturedText || text.length < 10) return;
    lastCapturedText = text;

    chrome.runtime.sendMessage(
      { action: "respond", text: text },
      (response) => {
        if (chrome.runtime.lastError) return;
        // Silent capture — no UI feedback needed
      }
    );
  }

  // Attempt to capture after streaming stops
  function tryCapture() {
    if (!contextInjected) return;
    if (isStreaming()) {
      // Still streaming, check again later
      clearTimeout(captureTimer);
      captureTimer = setTimeout(tryCapture, 1000);
      return;
    }

    const text = getLastResponseText();
    if (text) {
      captureResponse(text);
    }
  }

  // Set up MutationObserver to watch for new AI responses
  function startResponseObserver() {
    const observer = new MutationObserver((mutations) => {
      if (!contextInjected) return;

      // When DOM changes, debounce and check for completed response
      clearTimeout(captureTimer);
      captureTimer = setTimeout(tryCapture, 2000);
    });

    // Observe the main chat area for child changes
    observer.observe(document.body, {
      childList: true,
      subtree: true,
    });
  }

  startResponseObserver();

  // --- UI: Floating button and panel ---

  // Create floating button
  const btn = document.createElement("div");
  btn.id = "easybase-fab";
  btn.textContent = "EB";
  btn.title = "Load Easybase Context";
  document.body.appendChild(btn);

  // Create panel
  const panel = document.createElement("div");
  panel.id = "easybase-panel";
  panel.innerHTML = `
    <div class="eb-panel-header">
      <span>Easybase</span>
      <span id="eb-status-dot" class="eb-dot eb-dot-unknown"></span>
      <button id="eb-close" class="eb-close-btn">&times;</button>
    </div>
    <div class="eb-panel-body">
      <input type="text" id="eb-query" placeholder="Enter your query..." />
      <button id="eb-load-btn" class="eb-action-btn">Load Context</button>
      <div id="eb-message" class="eb-message"></div>
    </div>
  `;
  document.body.appendChild(panel);

  // State
  let panelOpen = false;

  // Toggle panel
  btn.addEventListener("click", () => {
    panelOpen = !panelOpen;
    panel.style.display = panelOpen ? "block" : "none";
    if (panelOpen) {
      checkStatus();
      document.getElementById("eb-query").focus();
    }
  });

  // Close button
  document.getElementById("eb-close").addEventListener("click", () => {
    panelOpen = false;
    panel.style.display = "none";
  });

  // Check server status
  function checkStatus() {
    chrome.runtime.sendMessage({ action: "status" }, (response) => {
      const dot = document.getElementById("eb-status-dot");
      if (response && response.ok) {
        dot.className = "eb-dot eb-dot-ok";
        dot.title = `Connected (${response.chunks} chunks)`;
      } else {
        dot.className = "eb-dot eb-dot-error";
        dot.title = "Server not reachable";
      }
    });
  }

  // Load context
  document.getElementById("eb-load-btn").addEventListener("click", () => {
    const queryInput = document.getElementById("eb-query");
    const query = queryInput.value.trim();
    const msgEl = document.getElementById("eb-message");

    if (!query) {
      msgEl.textContent = "Enter a query first.";
      msgEl.className = "eb-message eb-error";
      return;
    }

    msgEl.textContent = "Loading...";
    msgEl.className = "eb-message eb-loading";

    chrome.runtime.sendMessage(
      { action: "load", query: query },
      (response) => {
        if (response && response.error) {
          msgEl.textContent = response.error;
          msgEl.className = "eb-message eb-error";
          return;
        }

        if (response && response.context) {
          // Inject into chat input
          const input = getInputElement(platform);
          if (input) {
            const existing = getInputText(input);
            const combined = response.context + "\n\n" + existing;
            setInputText(input, combined);
            msgEl.textContent = "Context injected into chat input.";
            msgEl.className = "eb-message eb-success";
            // Mark context as injected — enable auto-capture
            contextInjected = true;
            lastCapturedText = "";
            // Close panel after success
            setTimeout(() => {
              panelOpen = false;
              panel.style.display = "none";
            }, 1500);
          } else {
            msgEl.textContent = "Could not find chat input field. Try clicking in the chat box first.";
            msgEl.className = "eb-message eb-error";
          }
        }
      }
    );
  });

  // Enter key to load
  document.getElementById("eb-query").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      document.getElementById("eb-load-btn").click();
    }
  });
})();
