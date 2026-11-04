# 🔎 Multi-Agent Research Platform — UI Layer

A modular, standalone scholarly web interface built using the **Academic Editorial Intelligence** design system, tailored specifically to mirror the platform's multi-agent backend architecture.

---

## 📁 Clean Separated Architecture

The UI is cleanly decoupled into modular, professional web standards without external build dependencies or bulky CDN runtime engines:

```
ui/
├── index.html         # Semantic HTML markup (3 core views, modals, and drawers)
├── css/
│   └── style.css      # Vanilla CSS stylesheet based on DESIGN.md design tokens
├── js/
│   ├── api.js         # Real FastAPI backend client (`/generate`, `/scores`, `/health`, local persistence)
│   └── app.js         # Interactive client-side UI controller (Search modal, drawer, citations, pipeline coordinator)
└── README.md          # Documentation & usage guide
```

---

## 🎨 Design System & Theme Continuity

Faithfully maintains the **Academic Editorial Intelligence** design language:
- **Color Palette:**
  - Academic Teal (`#005151` / `#0f6b6b`) for primary triggers, active badges, and verified citations
  - Scholarly Slate (`#4f6070` / `#5a6c7c`) for secondary metadata and hairlines
  - Burnt Orange (`#852802` / `#c2542d`) for epistemic divergence warnings and pending peer-reviews
  - Parchment Surface (`#f7f9ff`, `#edf4ff`, `#dde9f9`) for calm, fatigue-free reading
- **Typography:**
  - `Inter` for functional apparatus, chrome, inputs, and citation numbers
  - `Newsreader` for editorial research monographs, executive syntheses, and analysis
- **3-Tier Layout:**
  1. **Left Rail (270px):** Inquiry history, corpus stats, and new inquiry launcher
  2. **Center Canvas (Max ~768px reading column):** Synthesized monographs, visual abstracts, and scorecards
  3. **Right Inspector Drawer (360px):** Interactive citations provenance, 4-agent trace, and memory tier status

---

## 🧠 Backend-Aligned Features

The UI is customized to reflect every component in our Python backend:

1. **Role-Based Access Control (Scholar User vs Admin Evaluator):**
   - **Scholar User Mode:** Designed for researchers and students. Provides a clean reading experience: model diagnostics (synthesis latency, Groq model metadata, pgvector LTM chips, judge score banners, and visual charts) and LLM-as-a-judge scorecards are hidden. The user sees the clean 4-agent flow (Search → Summarize → Write → Verify), the comprehensive monograph with interactive inline citations `[1]`, and strictly **Verified Sources** in the right inspector drawer.
   - **Admin Evaluator Mode:** Designed for AI engineers and evaluators. Unlocks full model diagnostics: the metrology strip (3.82s synthesis, Groq Llama-3.3-70b, pgvector LTM), the `9.6 / 10 Judge Score` banner, the automated **LLM-as-a-Judge Evaluation Scorecard** (`evaluation/judge.py`), model examiner critiques for prompt fine-tuning, the **Agent Trace** latency timeline, and **Memory & Safety** audits (Redis STM, pgvector LTM, PyRIT red-teaming).
   - **Unified Profile Component:** Single, elegant Profile button in the header (`Dr. Eleanor Vance | User` or `Admin Evaluator | Admin`). Clicking the profile opens a clean dropdown containing user identity, email, active permissions, and the single one-click login switch between User Mode and Admin Mode (removing all duplicate buttons from the toolbar).
2. **Permanently Fixed Bottom Composer:**
   - Styled and docked at the bottom of the conversation viewport for continuous natural interaction without UI jumps or duplicate input boxes.
3. **Collapsible & Reopenable History Sidebar:**
   - Can be collapsed to zero width for full-screen reading and reopened at any time via the persistent `#btn-toggle-sidebar` header button.
4. **4-Agent LangGraph Pipeline:**
   - **Search Agent:** Queries academic archives (arXiv, PubMed, NOAA, IEEE).
   - **Summarize Agent:** Extracts and deduplicates empirical findings.
   - **Write Agent:** Synthesizes structured monographs with line-level citations.
   - **Verify Agent:** Fact-checks claims against search findings (0 revisions required).
5. **Interactive Simulated Pipeline & Citations:**
   - Launching any query in the composer runs an animated, step-by-step walkthrough of the guardrails, cache check, 4 agents, and LLM judge.
   - Hovering or clicking `[1]`, `[2]`, etc. reveals inline tooltips and highlights corresponding verified papers in the Provenance Drawer.
   - Press <kbd>Ctrl</kbd> + <kbd>K</kbd> to open the inquiry search modal with live query matching.

---

## 🚀 How to Run

Because this is a completely standalone, professional client-side implementation:

1. **Directly in Browser:** Double-click `ui/index.html` or open `file:///c:/Projects/Multi-agent-research-platform/ui/index.html`.
2. **Via Local Static Server (Optional):**
   ```bash
   cd ui
   python -m http.server 3000
   ```
   Then navigate to `http://localhost:3000`.
