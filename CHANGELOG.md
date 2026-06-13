# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Planned
- Metrics dashboard from history + receipt data
- Store tags: normalize store names to display chips (COMPRA-38)
- Price intelligence: tracking precio/kg por producto y comparativa tiendas
- Corrección manual de datos del ticket
- Smart alerts: sugerencias de reposición por frecuencia

---

## [3.6.0] — 2026-06-13

### Added (COMPRA-41, COMPRA-38)
- **Edición manual de artículos del historial (COMPRA-41)**: toca cualquier artículo en el detalle del historial para editar precio, cantidad y unidad. Los datos corregidos se guardan en PostgreSQL y el detalle se refresca automáticamente.
- **Store tags como pills (COMPRA-38 parcial)**: los nombres de tienda se muestran como chips con fondo azul claro, tanto en cabeceras del historial como junto a cada artículo.

### Fixed
- Prompt Groq: instrucción explícita de alinear precio con su propia fila (no con la adyacente).
- Nuevo endpoint `PATCH /api/history/<id>/item` para actualizar precio/cantidad/unidad de un artículo del historial.

---

## [3.5.0] — 2026-06-13

### Added
- **Feedback visual del scan**: overlay con spinner mientras Groq procesa el ticket. Al terminar muestra ✅ con tienda + total + artículos actualizados (se cierra solo a los 3s) o ❌ con mensaje de error + botón Cerrar.

### Fixed
- **Extracción de pesos**: prompt de Groq mejorado con ejemplo real de formato de ticket español. Especifica explícitamente que para artículos de peso variable el formato es "0,206 KG × 11,50€/KG" y que quantity debe ser el peso del envase (0.206), no el precio/kg. Incluye ejemplos de bacalao 150g, leche 1L, huevos 12ud.

---

## [3.4.2] — 2026-06-13

### Fixed (feedback post-test v3.4.1)
- **Precio confundido con €/kg del nombre**: el prompt de Groq ahora especifica que `price` es el importe de la columna derecha del ticket, nunca el precio por unidad de peso que pueda aparecer dentro del nombre del artículo.
- **Historial muestra solo artículos comprados**: `renderHistoryDetail()` filtra a `checked === true`. Los artículos que estaban en la lista pero no se compraron no aparecen en el historial (siguen guardados en `items_json` para métricas futuras, COMPRA-33). El dato tiene valor analítico pero no aporta claridad visual en esta fase.
- **Orden en historial**: nombre → cantidad/peso → precio → tienda. Añadido campo `quantity+unit` en la visualización.
- **Tachado eliminado del historial**: se elimina la clase `done` y el tachado — todos los items mostrados son comprados, el tachado es redundante.

---

## [3.4.1] — 2026-06-13

### Fixed (feedback post-COMPRA-37)
- **Sugerencias genéricas restauradas**: eliminado el bloque de rename de nombre que renombaba `catalog` al texto del ticket (ej: "pechuga de pavo extra 150gr" sobreescribía "pavo"). El nombre del ítem en la lista sigue siendo el que puso el usuario; el detalle del ticket queda en `ticket_name`.
- **Precios y pesos ya no se inventan**: el prompt de Groq incluye ahora instrucción explícita de no estimar ni inventar valores numéricos — si un precio, peso o cantidad no es claramente legible en el ticket, Groq debe devolver `null`.
- **Tag de tienda simplificado**: nueva función `simplifyStore()` en el frontend extrae la primera palabra significativa del nombre de la tienda (descartando "Grupo", "SL", "SA", etc.). Ej: "Vidania Gastronomia SL" → "Vidania", "Grupo Dia Lorca" → "Dia". Se aplica en historial, detalle de historial y toast del scan. El nombre completo se sigue almacenando en DB.

---

## [3.4.0] — 2026-06-13

### Changed (COMPRA-37 — refinamientos scan ticket)
- **Categoría automática para extras**: los productos del ticket no presentes en la lista se categorizan automáticamente via `_category_for_name()` (coincidencia por palabras clave) antes de insertarse. Ej: "Contramuslo de pollo" → `carne_pescado`, "Bacalao desalado" → `carne_pescado`. Se propaga también al catálogo para mantener la categoría en futuros usos.
- **Nombre más rico en detalle**: si el ticket aporta un nombre más específico que el de la lista (ej: ticket "Contramuslo de pollo" vs lista "Pollo"), y el nombre de la lista aparece como subcadena del nombre del ticket, el ítem se renombra automáticamente al nombre más descriptivo. Se actualiza tanto `items` como `catalog`.
- **Selector de galería habilitado**: eliminado `capture="environment"` del input de imagen — ahora el diálogo permite tanto hacer una foto nueva como elegir una imagen existente de la galería.
- **Eliminado emoji redundante por ítem**: el botón de categoría en la lista activa muestra `⋯` en lugar del emoji de categoría. El emoji ya se muestra en la cabecera del grupo de categoría; duplicarlo por ítem era ruido visual.
- **Eliminada línea secundaria de ticket en historial**: la línea en cursiva que mostraba el texto original del ticket (ej: "contracoix de pollastre") bajo el nombre del ítem ha sido eliminada. El nombre del ítem ya refleja la versión más rica; guardar el original en `ticket_name` sigue siendo posible para métricas futuras (COMPRA-33) pero no se muestra en la UI.

---

## [3.3.0] — 2026-06-13

### Added (COMPRA-36)
- **Soporte catalán y multilingüe**: campo `name_es` en el output de Groq — el modelo traduce el texto del ticket al castellano cuando está en catalán, valenciano u otro idioma. El fuzzy match usa `name_es` para comparar contra la lista (en castellano). `ticket_name` sigue guardando el texto original fiel al ticket.
- **Detalle del ticket en historial**: al expandir una entrada del historial, cada artículo muestra en línea secundaria el texto exacto del ticket (`ticket_name`) cuando difiere del nombre del catálogo. Ej: "Huevos" + "OUS ECOLOGICS 6 UNITATS". Base para drill-down en métricas futuras (COMPRA-33).
- **Extras → lista activa**: artículos del ticket que no estaban en la lista se añaden automáticamente como comprados (`checked=TRUE`). El toast refleja "X act. · Y añadidos". Los extras también se registran en `catalog` para alimentar sugerencias futuras.

---

## [3.2.0] — 2026-06-11

### Changed (breaking redesign of COMPRA-34 receipt flow)
- **Receipt scan movido a la lista activa (COMPRA-35)**: el scan ya no ocurre desde el historial sino durante la sesión de compra
  - Botón 📷 en el header junto a 🕐 y 🗑️ — disponible mientras la lista está activa
  - Soporte multi-tienda: múltiples scans por sesión (uno por cada tienda visitada)
  - Fuzzy matching server-side (difflib SequenceMatcher >0.65) — no requiere que Groq conozca el catálogo
  - Items enriquecidos con precio + tienda visibles en la lista activa y en el detalle del historial
  - Al vaciar la lista, todos los datos de precio/tienda se archivan en el historial automáticamente
  - El botón 📷 muestra conteo de tickets escaneados en la sesión (e.g. `📷 2`)
  - Estado de sesión persiste tras refresh de página (vía `GET /api/receipts`)

### Added
- Nuevas columnas en `items`: `price`, `store_name`, `ticket_name`, `quantity`, `unit`
- Nueva tabla `active_receipts`: acumula receipts de la sesión actual, se vacía en cada reset
- Nueva columna `history.receipts_json`: array de receipts por sesión (una entrada por tienda)
- `POST /api/receipt`: nuevo endpoint primario — escanea contra lista activa y actualiza items
- `GET /api/receipts`: devuelve receipts escaneados en la sesión actual

### Removed
- `POST /api/history/<id>/receipt`: eliminado (beta, sin necesidad de scans retroactivos)
- Botón "🧾 Ticket" del panel de historial

### Fixed
- `load_items()` ahora incluye los campos de precio/tienda → SSE propaga precios a todos los clientes en tiempo real

---

## [3.1.0] — 2026-06-11

### Added
- **Receipt scanning (COMPRA-34)**: asociar el ticket físico de la compra a cada entrada del historial
  - Botón "🧾 Ticket" en cada entrada del panel de historial
  - Captura de imagen desde cámara (móvil) o selector de archivo
  - Procesado con Groq `llama-3.2-90b-vision-preview` — extrae supermercado, total, artículos con precios y matching contra catálogo
  - La imagen **no se almacena** — procesada en memoria y descartada; solo el JSON resultante va a PostgreSQL
  - Nuevas columnas en `history`: `store_name`, `total_amount`, `receipt_json (JSONB)`
  - Endpoint: `POST /api/history/<id>/receipt`
  - El historial muestra 🏪 nombre tienda y 💚 total gastado por entrada cuando hay ticket
- **Repo hygiene**: CHANGELOG.md, GitHub Actions CI, .gitignore mejorado
- **Fix crítico**: `railway.json` alineado con Procfile (`gthread --workers 1 --timeout 0`)
  — `--workers 2 --timeout 30` causaba que SSE no llegara a todos los clientes y drops de conexión

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

---

## [3.5.0] — 2026-06-13
