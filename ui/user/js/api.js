// api.js: connects the UI to the real backend. Load it before app.js:
//   <script src="js/api.js"></script>
// Exposes one global object: RP

const RP = (() => {
  // Dynamically use current origin when served by FastAPI, or fallback for direct file preview
  const API_BASE = (typeof window !== "undefined" && window.location.origin && window.location.origin.startsWith("http"))
    ? window.location.origin
    : "http://127.0.0.1:8000";
  const KEY = "rp_history_v1";
  let sessionId = null;

  // ---------- backend call ----------
  async function generate(text, signal) {
    let res;
    try {
      res = await fetch(API_BASE + "/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic: text, session_id: sessionId }),
        signal,
      });
    } catch (e) {
      if (e.name === "AbortError") throw e;
      throw Object.assign(new Error("Can\u2019t reach the server."), { status: 0 });
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      let msg = "Something went wrong. Please try again.";
      if (res.status === 503) msg = "The AI service is temporarily unavailable. Please try again.";
      else if ((res.status === 400 || res.status === 422) && typeof data.detail === "string") msg = data.detail;
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
  function openChat(id) { sessionId = id; } // follow-ups only work while the server session is alive (about 1 hour)

  // ---------- history, kept in this browser (from live user research) ----------
  function load() {
    try {
      const saved = localStorage.getItem(KEY);
      if (saved !== null) return JSON.parse(saved) || [];
      return [];
    } catch (e) { return []; }
  }
  function persist(chats) {
    try { localStorage.setItem(KEY, JSON.stringify(chats)); } catch (e) {}
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
  }
  function deleteChat(id) {
    persist(load().filter(c => c.id !== id));
    if (sessionId === id) sessionId = null;
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
    try { domain = new URL(s.url).hostname.replace(/^www\./, ""); } catch (e) {}
    return { ...s, domain, favicon: domain ? "https://www.google.com/s2/favicons?domain=" + domain + "&sz=32" : "" };
  }
  function citationCount(report, n) {
    return (String(report).split("\n## Sources")[0].match(new RegExp("\\[" + n + "\\]", "g")) || []).length;
  }

  return { baseUrl: API_BASE, currentId: () => sessionId, generate, health, newChat, openChat, listChats, getChat, renameChat, deleteChat, search, sourceInfo, citationCount };
})();
