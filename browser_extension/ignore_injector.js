// Runs in MAIN world. Patches both window.fetch and XMLHttpRequest so the page's
// own network calls go through this wrapper. sessionStorage is shared between
// ISOLATED and MAIN worlds, so when toast_inject.js sets zt_ignore_pending='1'
// this wrapper injects X-ZT-Ignore-Token: 1 into the next matching chat POST.
// NOTE: Gemini uses XMLHttpRequest (goog.net.XhrIo), not fetch — both must be patched.
(() => {
  try { if (window.__ZT_IGNORE_INJECTOR__) return; window.__ZT_IGNORE_INJECTOR__ = true; } catch(_) {}

  const CHAT_RE = /(conversation|messages|completions|generate|append|\/v1\/)/i;

  // --- Patch fetch (ChatGPT, Claude, etc.) ---
  const _f = window.fetch;
  window.fetch = async function(input, init) {
    try {
      const url = typeof input === 'string' ? input : (input && input.url) || '';
      const method = ((init && init.method) || 'GET').toUpperCase();
      const isChat = method === 'POST' && CHAT_RE.test(url);
      const pending = sessionStorage.getItem('zt_ignore_pending');
      if (isChat) console.info('[ZTProxy][ignore_injector] fetch chat POST', url, 'pending=', pending);
      if (isChat && pending === '1') {
        sessionStorage.removeItem('zt_ignore_pending');
        const m = Object.assign({}, init || {});
        const h = new Headers(m.headers || {});
        h.set('X-ZT-Ignore-Token', '1');
        m.headers = h;
        console.info('[ZTProxy][ignore_injector] ✅ X-ZT-Ignore-Token injected via fetch');
        return _f.apply(this, [input, m]);
      }
    } catch(e) {}
    return _f.apply(this, arguments);
  };

  // --- Patch XHR (Gemini uses goog.net.XhrIo / XMLHttpRequest, not fetch) ---
  const _open = XMLHttpRequest.prototype.open;
  const _send = XMLHttpRequest.prototype.send;
  const _setHeader = XMLHttpRequest.prototype.setRequestHeader;

  XMLHttpRequest.prototype.open = function(method, url) {
    try { this.__zt_method = method; this.__zt_url = url; } catch(_) {}
    return _open.apply(this, arguments);
  };

  XMLHttpRequest.prototype.send = function(body) {
    try {
      const method = (this.__zt_method || '').toUpperCase();
      const url = this.__zt_url || '';
      const isChat = method === 'POST' && CHAT_RE.test(url);
      const pending = sessionStorage.getItem('zt_ignore_pending');
      if (isChat) console.info('[ZTProxy][ignore_injector] XHR chat POST', url, 'pending=', pending);
      if (isChat && pending === '1') {
        sessionStorage.removeItem('zt_ignore_pending');
        _setHeader.call(this, 'X-ZT-Ignore-Token', '1');
        console.info('[ZTProxy][ignore_injector] ✅ X-ZT-Ignore-Token injected via XHR');
      }
    } catch(e) {}
    return _send.apply(this, arguments);
  };

  // --- Patch WebSocket (Copilot uses WebSocket/SignalR, ChatGPT uses WebSocket) ---
  // This patch intercepts WebSocket messages with zt_blocked=true from proxy
  // and dispatches ztproxy-blocked event for the toast to catch
  try {
    const _WS = window.WebSocket;
    if (typeof _WS === 'function') {
      function ZTWebSocket(url, protocols) {
        const ws = (arguments.length >= 2) ? new _WS(url, protocols) : new _WS(url);

        // Add message listener in capture phase (before page's handlers)
        ws.addEventListener('message', function(evt) {
          try {
            if (typeof evt.data !== 'string') return;
            const d = JSON.parse(evt.data);

            // Check for proxy block notification
            if (d && d.zt_blocked === true) {
              evt.stopImmediatePropagation(); // Prevent page from seeing this message

              const reasonText = d.reason === 'pii_detected'
                ? 'PII detected — message blocked by ZeroTrusted.ai'
                : 'Blocked by ZeroTrusted.ai';

              // Check auth status from localStorage (set by background.js)
              let isAuth = false;
              try {
                const authStatus = localStorage.getItem('zt_auth_status');
                isAuth = authStatus === 'authenticated';
              } catch(_) {}

              // Dispatch event for toast with all details
              const detail = {
                reason: reasonText,
                url: location.href,
                mode: 'post-chat-pii',
                wsBlocked: true,
                masked: d.masked || '',  // PII details from proxy
                allowProceed: d.allowProceed || false,  // Show Ignore button
                auth: isAuth  // Auth status for button logic
              };
              const ev = new CustomEvent('ztproxy-blocked', { detail });
              window.dispatchEvent(ev);

              console.info('[ZTProxy][ignore_injector] WS block signal detected', d.reason, 'masked:', d.masked);
            }
          } catch(_) {}
        }, true); // capture phase

        return ws;
      }
      ZTWebSocket.prototype = _WS.prototype;
      Object.setPrototypeOf(ZTWebSocket, _WS); // Inherit static properties
      window.WebSocket = ZTWebSocket;
      console.info('[ZTProxy][ignore_injector] WebSocket patched');
    }
  } catch(_) {}

  console.info('[ZTProxy][ignore_injector] installed (fetch + XHR + WebSocket patched)');
})();
