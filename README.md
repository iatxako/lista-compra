# Lista de la Compra — v3

App web para gestionar la lista de la compra desde cualquier dispositivo, con sincronización en tiempo real, modo offline y agrupación por categorías.

## Stack

- **Frontend:** HTML + JS vanilla (SPA, servido por el backend)
- **Backend:** Python Flask + Gunicorn (Railway)
- **Persistencia:** PostgreSQL (Railway)
- **Auth:** Cookie HMAC firmada (httponly, SameSite=Strict) + `X-API-Key` header como fallback
- **Sync:** SSE (Server-Sent Events) para actualización en tiempo real entre dispositivos
- **Offline:** Cola de operaciones pendientes en localStorage, merge al reconectar

## Arquitectura

```
  Usuario (móvil/web)
       │
       ├── GET /          → index.html (SPA) + cookie de auth
       ├── GET /api/stream → SSE (sync tiempo real)
       └── POST /api/*    → operaciones autenticadas
               │
        ┌──────▼──────────┐
        │  Railway         │
        │  server.py       │
        └──────┬──────────┘
               │ DATABASE_URL
        ┌──────▼──────────┐
        │  PostgreSQL      │
        │  ├── items       │  ← lista activa
        │  ├── catalog     │  ← historial de productos + categorías
        │  └── history     │  ← snapshots de listas eliminadas
        └──────────────────┘
```

## Tablas PostgreSQL

| Tabla | Descripción |
|-------|-------------|
| `items` | Lista activa: `name, added, checked, created_at` |
| `catalog` | Catálogo de productos: `name, times_added, times_purchased, last_added_at, last_purchased_at, avg_interval_days, category` |
| `history` | Snapshots al vaciar: `id, saved_at, item_count, checked_count, items_json` |

## API

| Endpoint | Método | Auth | Descripción |
|----------|--------|------|-------------|
| `/api/stream` | GET | No | SSE — sync en tiempo real |
| `/api/list` | GET | No | Lista actual en JSON |
| `/api/add` | POST | Sí | Añadir item (`{name, category?}`) |
| `/api/check` | POST | Sí | Marcar/desmarcar (`{name, checked}`) |
| `/api/remove` | POST | Sí | Eliminar item (`{name}`) |
| `/api/category` | POST | Sí | Asignar categoría (`{name, category}`) |
| `/api/reset` | POST | Sí | Vaciar lista + guardar snapshot en history |
| `/api/history` | GET | Sí | Lista de snapshots (últimos 10) |
| `/api/history/<id>` | GET | Sí | Detalle de snapshot con `items_json` |
| `/api/suggestions` | GET | No | Sugerencias basadas en `catalog` |
| `/health` | GET | No | Health check |

## Funcionalidades

- **Agrupación por categoría** — 9 categorías con emojis; auto-mapeado de ~130 productos; picker manual por artículo
- **Orden dentro de grupos** — artículos pendientes primero, comprados al final
- **Modo offline** — cambios quedan en cola y se sincronizan al reconectar
- **Historial** — cada vez que se vacía la lista se guarda un snapshot con fecha, conteos y lista completa
  - Panel 🕐 en el header muestra los últimos 10 historiales
  - Tap en cada entrada expande la lista de artículos ordenados por categoría
- **Sugerencias** — productos del catálogo con `times_added > 1` que no están en la lista actual
- **Sincronización multi-dispositivo** — SSE notifica cambios a todos los clientes conectados

## Despliegue

```bash
cd /tmp/lista-compra
railway up --service api
```

Variables de entorno en Railway:

| Variable | Descripción |
|----------|-------------|
| `DATABASE_URL` | Connection string PostgreSQL (Railway la provee automáticamente) |
| `API_KEY` | Clave para proteger los endpoints de escritura |

## Desarrollo local

```bash
pip install -r requirements.txt
DATABASE_URL=postgresql://... API_KEY=... python3 server.py
# http://localhost:8767
```

## Commits relevantes

| Commit | Feature |
|--------|---------|
| `b81996a` | Revert offline-first roto → online funcional |
| `d41a830` | Auth via cookie HMAC (fix silent 401) |
| `b66a8e5` | Offline-first con merge-on-reconnect |
| `b5c4fa0` | Agrupación por categoría + picker |
| `cc47d9c` | Sort pendientes-primero dentro de grupos |
| `6a1eff6` | Historial de listas — snapshot al vaciar |
| `c84f335` | Detalle de artículos por entrada del historial |
| `89f2021` | Sort por categoría en detalle del historial |
