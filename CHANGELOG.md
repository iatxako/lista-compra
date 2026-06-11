# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Planned
- Receipt scanning via Groq vision to enrich history entries (store name, total, item prices)
- Metrics dashboard from history data

---

## [3.0.0] — 2026-06-11

### Added
- **History**: every time the list is cleared, a snapshot is saved to PostgreSQL
  - `history` table: `id, saved_at, item_count, checked_count, items_json (JSONB)`
  - History panel (🕐 button) shows last 10 snapshots with date, item count, completion %
  - Tap to expand each entry and see the full item list sorted by category
  - Auto-purge: only the last 10 snapshots are kept
  - New endpoints: `GET /api/history`, `GET /api/history/<id>`
- **Category grouping**: items in the active list are grouped by category (9 categories)
  - Auto-mapping of ~130 product names via `AUTO_MAP` constant
  - Manual category picker (bottom sheet) per item
  - Category stored in `catalog.category` — persists across list clears
- **Sort unchecked-first**: within each category group, pending items appear above checked ones
- **Offline-first with merge-on-reconnect**: changes are queued in localStorage when offline
  - Pending operations (add/check/remove/category) merge on top of server state on reconnect
  - `window.online` event triggers sync flush

### Fixed
- **SSE-compatible gunicorn config**: `--worker-class gthread --workers 1 --threads 4 --timeout 0`
  - Previous `--workers 2 --timeout 30` caused SSE connection drops

### Changed
- `railway.json` `startCommand` aligned with `Procfile` (gthread, 1 worker, timeout 0)
- `requirements.txt`: added `groq>=0.9` for upcoming receipt scanning feature

---

## [2.0.0] — 2026-06-10

### Added
- **Cookie-based auth**: httponly HMAC-SHA256 signed cookie set on `GET /`
  - Eliminates manual API key entry — any device that loads the page is authenticated
  - Fallback: `X-API-Key` header still accepted
- **SSE real-time sync**: `GET /api/stream` pushes updates to all connected clients
  - 25s heartbeat to keep connections alive through proxies
- **Catalog tracking**: `catalog` table records `times_added`, `times_purchased`, `avg_interval_days`
- **Smart suggestions**: up to 5 products from catalog not currently in the list, shown as chips
- `GET /api/suggestions` endpoint
- `POST /api/category` endpoint

### Fixed
- Silent 401 on all write operations (caused by missing cookie — now set automatically on page load)

### Security
- Removed open CORS (`Access-Control-Allow-Origin: *`)
- Removed `?api_key=` URL parameter support (key was leaking into server logs)
- API key configured in Railway env vars — never committed

---

## [1.0.0] — 2026-05-xx

### Added
- Railway deployment (Flask + Gunicorn + PostgreSQL)
- `items` table: `name, added, checked, created_at`
- CRUD endpoints: `add`, `check`, `remove`, `reset`
- `GET /health` endpoint with DB connectivity check
- PWA manifest + icons (installable on mobile home screen)
- Empty state UI with cart emoji
- Toast notifications

---

## [0.1.0] — 2026-04-xx

### Added
- Initial local NAS version (Python Flask + JSON file storage)
- Basic checklist UI (vanilla HTML/JS)
- Telegram bot integration (later removed)
