# 🔎 Multi-Agent Research Platform — UI Layer

A clean, modular scholarly web interface built using the **Academic Editorial Intelligence** design system, tailored specifically to mirror the platform's multi-agent backend architecture.

---

## 📁 Clean Separated Architecture

The UI is cleanly organized into two dedicated workspaces:

```
ui/
├── index.html         # Main Gateway Portal (select between Scholar Workspace & Admin Dashboard)
├── user/              # 🎓 Scholar Research Platform (User Mode)
│   ├── index.html     # Semantic research workspace (reading canvas, composer, provenance drawer)
│   ├── css/
│   │   └── style.css  # Academic Editorial Intelligence stylesheet
│   ├── js/
│   │   ├── api.js     # Backend client for /generate and /health
│   │   ├── app.js     # Client UI controller (inquiry launcher, citations, search modal)
│   │   └── mock-data.js # Academic research sample monographs and evaluations
│   └── README.md      # User workspace documentation
├── admin/             # 🎛️ Observability & Metrology Suite (Admin Mode)
│   ├── index.html     # Master Unified SPA Dashboard
│   ├── views/         # Standalone modular views (health, metrics, traces, quality, safety, cache, audit)
│   ├── js/
│   │   ├── admin-app.js  # State manager, live probe simulators, and modals
│   │   └── admin-data.js # Rich mock datasets matching admin_backend Pydantic models
│   ├── css/
│   │   └── admin-style.css # Dark metrology styling tokens and animations
│   └── README.md      # Admin dashboard documentation
└── README.md          # This documentation file
```

---

## 🚀 How to Run

Because both workspaces are completely standalone, static web implementations:

1. **Directly in Browser:**
   - **Gateway Portal:** Double-click `ui/index.html` to choose your workspace.
   - **User Workspace:** Double-click `ui/user/index.html`.
   - **Admin Dashboard:** Double-click `ui/admin/index.html`.

2. **Via Local Static Server:**
   ```bash
   cd ui
   python -m http.server 3000
   ```
   Then navigate to:
   - `http://localhost:3000` (Portal)
   - `http://localhost:3000/user/` (Scholar Workspace)
   - `http://localhost:3000/admin/` (Admin Dashboard)
