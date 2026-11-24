// api.js: connects the UI to the real backend. Load it before app.js:
//   <script src="js/api.js"></script>
// Exposes one global object: RP

const RP = (() => {
  // Dynamically use current origin when served by FastAPI, or fallback for direct file preview
  const API_BASE = (typeof window !== "undefined" && window.location.origin && window.location.origin.startsWith("http"))
    ? window.location.origin
    : "http://127.0.0.1:8000";

  let sessionId = null;
  let currentUser = null; // null if guest/unauthenticated, or user object { id, email, full_name, ... }

  // ---------- namespaced chat storage keys ----------
  function getChatsKey() {
    const id = (currentUser && currentUser.id) ? currentUser.id : "guest";
    return `research_platform_chats_v1_${id}`;
  }

  function getLastActiveKey() {
    const id = (currentUser && currentUser.id) ? currentUser.id : "guest";
    return `rp_last_active_chat_id_${id}`;
  }

  // Gracefully migrate legacy un-namespaced chats to guest namespace once
  (function migrateLegacyStorage() {
    try {
      if (typeof localStorage === "undefined") return;
      const legacyKey1 = "research_platform_chats_v1";
      const legacyKey2 = "rp_history_v1";
      const legacyActiveKey = "rp_last_active_chat_id";
      const guestKey = "research_platform_chats_v1_guest";
      const guestActiveKey = "rp_last_active_chat_id_guest";

      if (!localStorage.getItem(guestKey)) {
        const legacyData = localStorage.getItem(legacyKey1) || localStorage.getItem(legacyKey2);
        if (legacyData) {
          localStorage.setItem(guestKey, legacyData);
        }
      }
      if (!localStorage.getItem(guestActiveKey)) {
        const legacyActive = localStorage.getItem(legacyActiveKey);
        if (legacyActive) {
          localStorage.setItem(guestActiveKey, legacyActive);
        }
      }
      localStorage.removeItem(legacyKey1);
      localStorage.removeItem(legacyKey2);
      localStorage.removeItem(legacyActiveKey);
    } catch (e) { }
  })();

  // ---------- backend call ----------
  async function generate(text, signal) {
    let res;
    try {
      res = await fetch(API_BASE + "/generate", {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest"
        },
        body: JSON.stringify({ topic: text, session_id: sessionId }),
        signal,
      });
    } catch (e) {
      if (e.name === "AbortError") throw e;
      throw Object.assign(new Error("Can\u2019t reach the server."), { status: 0 });
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      let msg = typeof data.detail === "string" ? data.detail : "Something went wrong. Please try again.";
      if (res.status === 503 && !data.detail) msg = "The AI service is temporarily unavailable. Please try again.";
      throw Object.assign(new Error(msg), { status: res.status });
    }
    sessionId = data.session_id;
    saveTurn(text, data);
    return data; // { session_id, intent, report, sources, cached, score, seconds }
  }

  async function health() {
    try { return (await fetch(API_BASE + "/health")).ok; } catch (e) { return false; }
  }

  // ---------- chats ----------
  function newChat() { sessionId = null; }
  function openChat(id) { sessionId = id; }

  // ---------- history, kept in this browser namespaced by user ----------
  function load() {
    try {
      const saved = localStorage.getItem(getChatsKey());
      if (saved !== null) return JSON.parse(saved) || [];
      return [];
    } catch (e) { return []; }
  }

  function persist(chats) {
    try { localStorage.setItem(getChatsKey(), JSON.stringify(chats)); } catch (e) { }
  }

  function saveTurn(userText, data) {
    const chats = load();
    let chat = chats.find(c => c.id === data.session_id);
    if (!chat) {
      chat = { id: data.session_id, title: userText.slice(0, 80), created: Date.now(), updated: 0, turns: [] };
      chats.unshift(chat);
    }
    chat.updated = Date.now();
    chat.turns.push({ user: userText, intent: data.intent, report: data.report, sources: data.sources || [], cached: !!data.cached, score: data.score || null, seconds: data.seconds });
    persist(chats);
  }

  function listChats() { return load().sort((a, b) => b.updated - a.updated); }
  function getChat(id) { return load().find(c => c.id === id) || null; }
  function renameChat(id, title) {
    const c = load();
    const x = c.find(i => i.id === id);
    if (x) {
      x.title = title;
      persist(c);
    } else {
      c.unshift({ id, title, created: Date.now(), updated: Date.now(), turns: [] });
      persist(c);
    }
    if (currentUser && currentUser.id) {
      _fetchAuth(`/api/chats/${encodeURIComponent(id)}`, "PUT", { title }).catch(() => {});
    }
  }

  function deleteChat(id) {
    persist(load().filter(c => c.id !== id));
    if (sessionId === id) sessionId = null;
    if (currentUser && currentUser.id) {
      _fetchAuth(`/api/chats/${encodeURIComponent(id)}`, "DELETE").catch(() => {});
    }
  }

  // Active chat id helpers (namespaced)
  function getLastActiveChatId() {
    try { return localStorage.getItem(getLastActiveKey()); } catch (e) { return null; }
  }

  function setLastActiveChatId(id) {
    try { localStorage.setItem(getLastActiveKey(), id); } catch (e) { }
  }

  function removeLastActiveChatId() {
    try { localStorage.removeItem(getLastActiveKey()); } catch (e) { }
  }

  // Switch active user & reset in-memory state
  function switchUser(user) {
    currentUser = user || null;
    sessionId = null;
    return listChats();
  }

  function getCurrentUser() {
    return currentUser;
  }

  // searches titles and report text; returns [{chat, snippet}]
  function search(query) {
    const q = query.trim().toLowerCase();
    if (!q) return listChats().slice(0, 10).map(chat => ({ chat, snippet: "" }));
    const out = [];
    for (const chat of listChats()) {
      let snippet = null;
      if (chat.title.toLowerCase().includes(q)) snippet = chat.title;
      for (const t of chat.turns) {
        const text = (t.report || "").replace(/\s+/g, " ");
        const i = text.toLowerCase().indexOf(q);
        if (i >= 0) { snippet = (i > 40 ? "\u2026" : "") + text.slice(Math.max(0, i - 40), i + 100) + "\u2026"; break; }
      }
      if (snippet) out.push({ chat, snippet });
    }
    return out;
  }

  // ---------- helpers for the Sources panel ----------
  function sourceInfo(s) {
    let domain = "";
    try { domain = new URL(s.url).hostname.replace(/^www\./, ""); } catch (e) { }
    return { ...s, domain, favicon: domain ? "https://www.google.com/s2/favicons?domain=" + domain + "&sz=32" : "" };
  }

  function citationCount(report, n) {
    return (String(report).split("\n## Sources")[0].match(new RegExp("\\[" + n + "\\]", "g")) || []).length;
  }

  // ---------- RP.auth: User Authentication APIs ----------
  async function _fetchAuth(endpoint, method, body = null) {
    const opts = {
      method,
      credentials: "include",
      headers: {
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json"
      }
    };
    if (body) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }

    let resp;
    try {
      resp = await fetch(API_BASE + endpoint, opts);
    } catch (e) {
      throw Object.assign(new Error("Cannot reach authentication server. Please check your network connection."), { status: 0 });
    }

    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      let msg = "Authentication failed. Please try again.";
      if (resp.status === 400) {
        msg = (typeof data.detail === "string") ? data.detail : "Invalid request parameters.";
      } else if (resp.status === 401) {
        msg = (typeof data.detail === "string") ? data.detail : "Invalid email or password.";
      } else if (resp.status === 403) {
        msg = (typeof data.detail === "string") ? data.detail : "Account is deactivated or access is denied.";
      } else if (resp.status === 409) {
        msg = "An account with this email already exists. Try signing in.";
      } else if (resp.status === 422) {
        if (Array.isArray(data.detail)) {
          msg = data.detail.map(d => d.msg || (typeof d === "string" ? d : JSON.stringify(d))).join("; ");
        } else if (typeof data.detail === "string") {
          msg = data.detail;
        } else {
          msg = "Validation failed. Please verify your inputs.";
        }
      } else if (resp.status === 429) {
        msg = (typeof data.detail === "string") ? data.detail : "Too many requests. Please wait a minute and try again.";
      } else if (resp.status === 503) {
        msg = "Authentication service is temporarily unavailable. Please try again later.";
      } else if (typeof data.detail === "string") {
        msg = data.detail;
      }
      throw Object.assign(new Error(msg), { status: resp.status, detail: data.detail });
    }
    return data;
  }

  const auth = {
    async config() {
      try {
        const res = await _fetchAuth("/api/auth/config", "GET");
        return res;
      } catch (e) {
        return { google_client_id: null };
      }
    },
    async register({ name, email, password, confirm_password }) {
      const res = await _fetchAuth("/api/auth/register", "POST", { name, email, password, confirm_password });
      currentUser = res;
      sessionId = null;
      return res;
    },
    async login({ email, password }) {
      const res = await _fetchAuth("/api/auth/login", "POST", { email, password });
      currentUser = res;
      sessionId = null;
      return res;
    },
    async logout() {
      try {
        await _fetchAuth("/api/auth/logout", "POST");
      } catch (e) {
        // Local logout proceeds even if network error
      }
      currentUser = null;
      sessionId = null;
      try {
        sessionStorage.removeItem("admin_access_token");
        localStorage.removeItem("admin_access_token");
      } catch (e) { }
      return { status: "ok" };
    },
    async me() {
      try {
        const res = await _fetchAuth("/api/auth/me", "GET");
        currentUser = res;
        return res;
      } catch (e) {
        if (e.status === 401 || e.status === 403) {
          currentUser = null;
          return null;
        }
        throw e;
      }
    },
    async google(credential) {
      const res = await _fetchAuth("/api/auth/google", "POST", { credential });
      currentUser = res;
      sessionId = null;
      return res;
    },
    async verifyOtp({ email, otp }) {
      const res = await _fetchAuth("/api/auth/verify-otp", "POST", { email, otp });
      if (currentUser && currentUser.email === email) {
        currentUser.email_verified = true;
      }
      return res;
    },
    async resendOtp({ email }) {
      return await _fetchAuth("/api/auth/resend-otp", "POST", { email });
    },
    async forgotPassword({ email }) {
      return await _fetchAuth("/api/auth/forgot-password", "POST", { email });
    },
    async resetPassword({ token, password, confirm_password }) {
      return await _fetchAuth("/api/auth/reset-password", "POST", { token, password, confirm_password });
    }
  };

  // ---------- RP.reviews: Report Review & Feedback APIs ----------
  const reviews = {
    async submit(reportId, rating, comment = null, topic = null, sId = null) {
      return await _fetchAuth("/api/reviews", "POST", {
        report_id: reportId,
        relevance: rating.relevance,
        accuracy: rating.accuracy,
        clarity: rating.clarity,
        comment: comment || null,
        topic: topic || null,
        session_id: sId || sessionId || null
      });
    },
    async getMine() {
      return await _fetchAuth("/api/reviews/mine", "GET");
    },
    async getForReport(reportId) {
      try {
        return await _fetchAuth("/api/reviews/" + encodeURIComponent(reportId), "GET");
      } catch (e) {
        if (e.status === 404) return null;
        throw e;
      }
    }
  };

  // Sync server-side chats when logged in
  async function syncServerChats() {
    if (!currentUser || !currentUser.id) return listChats();
    try {
      const serverChats = await _fetchAuth("/api/chats", "GET");
      if (Array.isArray(serverChats)) {
        const localChats = load();
        for (const sc of serverChats) {
          const match = localChats.find(lc => lc.id === sc.id);
          if (!match) {
            localChats.push({
              id: sc.id,
              title: sc.title,
              created: new Date(sc.created_at).getTime(),
              updated: new Date(sc.updated_at).getTime(),
              turns: []
            });
          } else {
            match.title = sc.title;
            match.updated = new Date(sc.updated_at).getTime();
          }
        }
        persist(localChats);
      }
    } catch (e) { }
    return listChats();
  }

  // Reconstruct UI turns from server chat messages
  function turnsFromMessages(messages) {
    const turns = [];
    let currentUserText = "";
    for (const m of (messages || [])) {
      if (m.role === "user") {
        currentUserText = m.content || "";
      } else if (m.role === "assistant" || m.role === "report" || m.role === "answer") {
        turns.push({
          user: currentUserText || "Research Inquiry",
          intent: m.intent || "research",
          report: m.content || "",
          sources: m.search_results || [],
          cached: !!m.cached,
          score: m.score || null,
          seconds: m.seconds || 0
        });
        currentUserText = "";
      }
    }
    return turns;
  }

  // Fetch full turn history from server for a specific chat
  async function fetchChatDetails(id) {
    if (!currentUser || !currentUser.id) return null;
    try {
      const data = await _fetchAuth(`/api/chats/${encodeURIComponent(id)}`, "GET");
      if (data && Array.isArray(data.messages)) {
        const localChats = load();
        let chat = localChats.find(c => c.id === id);
        if (!chat) {
          chat = {
            id,
            title: data.title || "Research Topic",
            created: new Date(data.created_at).getTime(),
            updated: new Date(data.updated_at).getTime(),
            turns: []
          };
          localChats.unshift(chat);
        }
        chat.turns = turnsFromMessages(data.messages);
        persist(localChats);
        return chat;
      }
    } catch (e) {
      console.warn("Could not fetch server chat details:", e);
    }
    return null;
  }

  return {
    baseUrl: API_BASE,
    currentId: () => sessionId,
    generate,
    health,
    newChat,
    openChat,
    listChats,
    getChat,
    fetchChatDetails,
    renameChat,
    deleteChat,
    search,
    sourceInfo,
    citationCount,
    auth,
    reviews,
    syncServerChats,
    switchUser,
    getCurrentUser,
    getLastActiveChatId,
    setLastActiveChatId,
    removeLastActiveChatId
  };
})();
