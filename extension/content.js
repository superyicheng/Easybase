// Easybase Browser Extension — Content Script
// Injected into AI chat pages (ChatGPT, Claude.ai, Gemini).
// Fully automatic: injects Easybase context into every message
// and stores all AI responses as searchable knowledge.

(function () {
  "use strict";

  // --- Platform Detection ---

  function detectPlatform() {
    const host = window.location.hostname;
    if (host.includes("chatgpt.com") || host.includes("chat.openai.com"))
      return "chatgpt";
    if (host.includes("claude.ai")) return "claude";
    if (host.includes("gemini.google.com") || host.includes("aistudio.google.com"))
      return "gemini";
    return null;
  }

  const platform = detectPlatform();
  if (!platform) return;

  // --- Input Element Helpers ---

  function getInputElement() {
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

    for (const sel of selectors[platform] || []) {
      const el = document.querySelector(sel);
      if (el) return el;
    }
    return null;
  }

  function getInputText(element) {
    if (element.tagName === "TEXTAREA") {
      return element.value;
    }
    return element.textContent || "";
  }

  function setInputText(element, text) {
    element.focus();

    if (element.tagName === "TEXTAREA") {
      const nativeSetter = Object.getOwnPropertyDescriptor(
        window.HTMLTextAreaElement.prototype,
        "value"
      ).set;
      nativeSetter.call(element, text);
      element.dispatchEvent(new Event("input", { bubbles: true }));
    } else {
      // Select all existing content then replace via execCommand
      // This works with ProseMirror (Claude) and React contenteditable (ChatGPT)
      const selection = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(element);
      selection.removeAllRanges();
      selection.addRange(range);
      document.execCommand("insertText", false, text);
    }
  }

  function getSendButton() {
    const selectors = {
      chatgpt: [
        'button[data-testid="send-button"]',
        'button[aria-label="Send prompt"]',
        'button[aria-label="Send"]',
      ],
      claude: [
        'button[aria-label="Send Message"]',
        'button[aria-label="Send message"]',
      ],
      gemini: [
        'button.send-button',
        'button[aria-label="Send message"]',
      ],
    };

    for (const sel of selectors[platform] || []) {
      const el = document.querySelector(sel);
      if (el) return el;
    }
    return null;
  }

  // --- DOM Message Selectors ---

  function getUserMessageSelector() {
    return {
      chatgpt: '[data-message-author-role="user"]',
      claude: '[data-testid="user-message"]',
      gemini: ".query-text, .user-query",
    }[platform];
  }

  function getResponseSelectors() {
    return {
      chatgpt: {
        container: '[data-message-author-role="assistant"]',
        content: ".markdown",
        streaming: 'button[aria-label="Stop streaming"]',
      },
      claude: {
        container: "[data-is-streaming]",
        content: ".font-claude-message",
        streaming: '[data-is-streaming="true"]',
      },
      gemini: {
        container: "model-response",
        content: ".model-response-text",
        streaming: ".loading-indicator",
      },
    }[platform];
  }

  function getLastUserMessageFromDOM() {
    const sel = getUserMessageSelector();
    if (!sel) return null;
    const messages = document.querySelectorAll(sel);
    if (messages.length === 0) return null;
    return messages[messages.length - 1].textContent?.trim() || null;
  }

  function getLastResponseText() {
    const sel = getResponseSelectors();
    if (!sel) return null;
    const messages = document.querySelectorAll(sel.container);
    if (messages.length === 0) return null;
    const lastMsg = messages[messages.length - 1];
    const contentEl = sel.content
      ? lastMsg.querySelector(sel.content) || lastMsg
      : lastMsg;
    return contentEl.textContent?.trim() || null;
  }

  function isStreaming() {
    const sel = getResponseSelectors();
    if (!sel || !sel.streaming) return false;
    return document.querySelector(sel.streaming) !== null;
  }

  // --- State ---

  let isLoadingContext = false;
  let lastUserMessage = "";
  let lastCapturedResponse = "";
  let captureTimer = null;
  let userMessageCount = 0;

  // --- Status Indicator (minimal, unobtrusive) ---

  function ensureIndicator() {
    let el = document.getElementById("easybase-indicator");
    if (el) return el;
    el = document.createElement("div");
    el.id = "easybase-indicator";
    el.textContent = "EB";
    el.title = "Easybase active";
    document.body.appendChild(el);
    return el;
  }

  ensureIndicator();

  function showLoading() {
    const el = ensureIndicator();
    el.textContent = "EB \u231B";
    el.title = "Loading Easybase context...";
    el.classList.add("eb-loading");
  }

  function hideLoading() {
    const el = ensureIndicator();
    el.textContent = "EB";
    el.title = "Easybase active";
    el.classList.remove("eb-loading");
  }

  // --- Send Interception ---

  function shouldIntercept() {
    if (isLoadingContext) return false;
    const input = getInputElement();
    if (!input) return false;
    const text = getInputText(input).trim();
    if (!text) return false;
    return { input, text };
  }

  function handleInterceptedSend(input, text) {
    isLoadingContext = true;
    showLoading();
    lastUserMessage = text;

    chrome.runtime.sendMessage(
      { action: "load", query: text, mode: "web" },
      (response) => {
        if (chrome.runtime.lastError) {
          // Extension error — send without context
          finishSend(input, text);
          return;
        }

        if (response && response.context && response.context.trim()) {
          const ctx = response.context.trim();
          const combined =
            "[Easybase Context]\n" +
            ctx +
            "\n[/Easybase Context]\n\n" +
            text;
          finishSend(input, combined);
        } else if (response && response.error) {
          // Server error — send without context
          finishSend(input, text);
        } else {
          finishSend(input, text);
        }
      }
    );
  }

  function finishSend(input, finalText) {
    setInputText(input, finalText);
    hideLoading();

    // Small delay for the framework to process input change
    setTimeout(() => {
      const sendBtn = getSendButton();
      if (sendBtn) {
        sendBtn.click();
      } else {
        // Fallback: dispatch Enter key
        input.dispatchEvent(
          new KeyboardEvent("keydown", {
            key: "Enter",
            code: "Enter",
            keyCode: 13,
            which: 13,
            bubbles: true,
            cancelable: true,
          })
        );
      }
      // Keep isLoadingContext true briefly so our interceptors don't re-catch
      setTimeout(() => {
        isLoadingContext = false;
      }, 300);
    }, 100);
  }

  // Intercept Enter key on chat input (capture phase — runs before platform handlers)
  document.addEventListener(
    "keydown",
    (e) => {
      if (e.key !== "Enter" || e.shiftKey || e.ctrlKey || e.altKey || e.metaKey)
        return;

      const result = shouldIntercept();
      if (!result) return;

      const input = result.input;
      if (!input.contains(e.target) && e.target !== input) return;

      e.preventDefault();
      e.stopImmediatePropagation();
      handleInterceptedSend(input, result.text);
    },
    true
  );

  // Intercept send button click (capture phase)
  document.addEventListener(
    "click",
    (e) => {
      const sendBtn = getSendButton();
      if (!sendBtn) return;
      if (!sendBtn.contains(e.target) && e.target !== sendBtn) return;

      const result = shouldIntercept();
      if (!result) return;

      e.preventDefault();
      e.stopImmediatePropagation();
      handleInterceptedSend(result.input, result.text);
    },
    true
  );

  // --- Auto-capture: detect new user messages and store exchanges ---

  function checkForNewUserMessage() {
    const sel = getUserMessageSelector();
    if (!sel) return;
    const messages = document.querySelectorAll(sel);
    if (messages.length > userMessageCount) {
      userMessageCount = messages.length;
      const text = messages[messages.length - 1].textContent?.trim();
      if (text && text.length > 0) {
        lastUserMessage = text;
      }
    }
  }

  function storeExchange(query, responseText) {
    if (!responseText || responseText === lastCapturedResponse) return;
    if (responseText.length < 50) return;
    lastCapturedResponse = responseText;

    chrome.runtime.sendMessage(
      { action: "exchange", query: query || "", response: responseText },
      () => {
        if (chrome.runtime.lastError) return;
      }
    );
  }

  function tryCapture() {
    if (isStreaming()) {
      clearTimeout(captureTimer);
      captureTimer = setTimeout(tryCapture, 1000);
      return;
    }

    const responseText = getLastResponseText();
    if (responseText && responseText !== lastCapturedResponse) {
      const query = lastUserMessage || getLastUserMessageFromDOM() || "";
      storeExchange(query, responseText);
    }
  }

  // --- MutationObserver: watch for chat changes ---

  const observer = new MutationObserver(() => {
    ensureIndicator();
    checkForNewUserMessage();
    clearTimeout(captureTimer);
    captureTimer = setTimeout(tryCapture, 2000);
  });

  observer.observe(document.body, {
    childList: true,
    subtree: true,
  });
})();
