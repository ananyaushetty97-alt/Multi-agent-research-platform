// api.js: connects the UI to the real backend. Load it before app.js:
//   <script src="js/api.js"></script>
// Exposes one global object: RP

const RP = (() => {
  // Use "" when the page is served by the backend itself (same address).
  const API_BASE = "http://localhost:8000";
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

  // ---------- history, kept in this browser ----------
  const DEFAULT_CHATS = [
    {
      id: "microplastics",
      title: "Impact of microplastics on marine life",
      created: Date.now() - 3600000,
      updated: Date.now() - 1800000,
      turns: [{
        user: "Impact of microplastics on marine life",
        intent: "new_research",
        report: "# Impact of Microplastics on Marine Fauna and Pelagic Ecosystems\n\nMicroplastic particulates (<5 mm) have permeated every strata of the marine pelagic environment. Beyond passive ingestion, these non-biodegradable polymeric matrices function as vectors for persistent organic pollutants (POPs) while disrupting cellular biomechanics, gamete motility, and structural calcification across keystone marine taxa.",
        sources: [
          { n: 1, title: "NOAA Marine Debris Program — Benthic Studies", url: "https://marinedebris.noaa.gov" },
          { n: 2, title: "Nature Ecology & Evolution — Pelagic Ingestion Kinetics", url: "https://nature.com/articles/s41559-024" }
        ],
        cached: true,
        score: { overall: 9.6, relevance: 10, accuracy: 9, clarity: 10, comment: "Rigorous empirical synthesis strictly adhering to peer-reviewed evidence." },
        seconds: 3.8
      }]
    },
    {
      id: "quantum-error",
      title: "Quantum Error Mitigation Review",
      created: Date.now() - 7200000,
      updated: Date.now() - 7200000,
      turns: [{
        user: "Quantum Error Mitigation Review",
        intent: "new_research",
        report: "# Quantum Error Mitigation and Coherence Scaling\n\nProbabilistic error cancellation and Clifford randomized benchmarking provide fault-tolerant syndrome fidelity thresholds without requiring full physical qubit redundancy overhead.",
        sources: [
          { n: 1, title: "Physical Review Letters — Probabilistic Coherence", url: "https://journals.aps.org/prl" }
        ],
        cached: true,
        score: { overall: 9.8, relevance: 10, accuracy: 10, clarity: 9.5, comment: "Superb coverage of quantum mitigation schemes." },
        seconds: 4.1
      }]
    },
    {
      id: "crispr-analysis",
      title: "CRISPR Prime Editing Mechanisms",
      created: Date.now() - 86400000,
      updated: Date.now() - 86400000,
      turns: [{
        user: "CRISPR Prime Editing Mechanisms",
        intent: "new_research",
        report: "# CRISPR Prime Editing and Precision Genomic Substitutions\n\nPegRNA-engineered reverse transcriptase complexes enable double-strand break-free precision genomic substitutions across human somatic cell lineages.",
        sources: [
          { n: 1, title: "Cell Genomics — Prime Editing Benchmarks", url: "https://cell.com" }
        ],
        cached: true,
        score: { overall: 8.9, relevance: 9, accuracy: 9, clarity: 9, comment: "High accuracy and clear distinction of prime vs base editing." },
        seconds: 3.5
      }]
    }
  ];

  function load() {
    try {
      const saved = localStorage.getItem(KEY);
      if (saved !== null) return JSON.parse(saved) || [];
      persist(DEFAULT_CHATS);
      return DEFAULT_CHATS;
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
