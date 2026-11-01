# 🎛️ Multi-Agent Research Platform — Admin UI

A clean, modular, high-density scientific observability dashboard tailored specifically to the backend architecture of the **Multi-Agent Research Platform** (`admin_backend/`).

---

## 📁 Clean, Modular Architecture

The previous scattered directories have been restructured into an efficient, modular layout:

```
ui/admin ui/
├── index.html                 # Unified Master SPA Dashboard (all tabs in one cohesive experience)
├── views/                     # Modular standalone view pages
│   ├── overview-health.html   # Subsystem Verifications & Service Reachability Probes
│   ├── metrics-latency.html   # End-to-End Synthesis Latency Distribution & Throughput
│   ├── agent-traces.html      # LangGraph 4-Agent Pipeline Waterfall & Latency Inspector
│   ├── quality-judge.html     # LLM-as-a-Judge Evaluation Scores & Human Review Calibration
│   ├── safety-red-team.html   # Guardrail Blocks Telemetry & PyRIT Red-Team Benchmarks
│   ├── memory-cache.html      # PostgreSQL pgvector LTM & Redis Semantic Cache Controls
│   ├── audit-config.html      # Append-Only Audit Journal & Runtime Configuration Blueprint
│   ├── overview-summary.html  # Executive Health Telemetry & Probe Summary
│   └── sign-in.html           # Admin Session Lock & Re-Authentication Screen
├── js/
│   └── admin-app.js           # Client-side state manager, routing, live API client, modals, and charts
├── css/
│   └── admin-style.css        # Academic Editorial Metrology styling tokens and animations
└── README.md                  # Admin dashboard documentation
```

---

## 🚀 Instant Offline Access

This UI is **100% self-contained and decoupled from the backend**. It requires no build step, no npm packages, and no running backend server.

### How to Run:
1. **Directly in Browser (Master Unified Dashboard):**
   Double-click `ui/admin ui/index.html` or open in any modern browser:
   ```
   file:///c:/Projects/Multi-agent-research-platform/ui/admin%20ui/index.html
   ```
2. **Open Individual Standalone Views:**
   You can also directly open any modular file in `views/` (e.g. `views/agent-traces.html` or `views/overview-health.html`). All cross-navigation links seamlessly route between views and link back to `../index.html`.
3. **Via Local Static Server:**
   ```bash
   cd "c:\Projects\Multi-agent-research-platform\ui\admin ui"
   python -m http.server 3001
   ```
   Then navigate to `http://localhost:3001`.

---

## 🛡️ Interactive Safeguards & Features

- **Master SPA Navigation:** Instant client-side tab switching without full page reloads.
- **Synthetic Probes:** Click `"Trigger Synthetic Probe"` to simulate real-time socket pings and micro-jitter across all 5 substrates (Redis, Postgres, Groq, Ollama, Tavily).
- **Trace Waterfall:** Click any row in the Traces table to open the slide-out waterfall inspector showing step-by-step agent timings.
- **Double-Confirmation Modal:** Destructive actions (cache wipe, LTM report deletion) strictly require typing `"CONFIRM"` before execution, logging immutable audit events.
- **Human Expert Reviews:** Submit ground-truth ratings (1-10) with notes to compare against automated judge scores.
- **Export Registry:** Download real `.csv` or `.json` datasets directly in your browser.
- **Lock Console:** Click the lock icon in the top header to trigger the Admin Sign-In overlay (`admin` / `admin123`).
