// Easybase Browser Extension — Content Script
// Injected into AI chat pages (ChatGPT, Claude.ai, Gemini).
// Adds a floating button that loads and injects Easybase context.

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
