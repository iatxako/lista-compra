# Lista de la Compra — v2

App web para gestionar la lista de la compra desde cualquier sitio.

## Stack v2

- **Frontend:** HTML + JS vanilla (servido por el backend en Railway)
- **Backend:** Python Flask + Gunicorn (Railway)
- **Persistencia:** Postgres (Railway)
- **Auth:** API Key via cabecera `X-API-Key`

## Arquitectura

```
                            ┌──────────────────┐
  Usuario (móvil) ────────▶│  Railway          │
                            │  (server.py)      │
                            │  ├── / → frontend │
                            │  └── /api/* → API │
                            └────────┬─────────┘
                                     │ DATABASE_URL
                            ┌────────▼─────────┐
                            │  Postgres         │
                            │  (tabla items)    │
                            └──────────────────┘
```

## Despliegue

### Railway (backend + frontend)

1. Crear proyecto en Railway desde el repo `iatxako/lista-compra`
2. Railway detecta `Procfile` y `railway.json` automáticamente
3. Añadir variables de entorno en Railway Dashboard:

| Variable | Descripción |
|----------|-------------|
| `DATABASE_URL` | Connection string de Postgres (Railway la provee al añadir el plugin) |
| `API_KEY` | Clave para proteger los endpoints |

4. La app se sirve en `https://api-production-5ac6.up.railway.app`

La API Key se configura en Railway como variable de entorno `API_KEY` y se introduce
manualmente en la app (⚙️ Settings) — no se acepta por parámetro de URL.

## Desarrollo local

```bash
pip install -r requirements.txt
DATABASE_URL=... API_KEY=... python3 server.py
# Abrir: http://localhost:8767
```

## API

| Endpoint | Método | Auth | Descripción |
|----------|--------|------|-------------|
| `/api/list` | GET | No | Lista actual en JSON |
| `/api/check` | POST | Sí | Marcar/desmarcar item |
| `/api/add` | POST | Sí | Añadir item |
| `/api/remove` | POST | Sí | Eliminar item |
| `/api/reset` | POST | Sí | Vaciar lista |
| `/health` | GET | No | Health check |

## v2 — Cambios respecto a v0.1

- ✅ Backend en Railway (accesible desde cualquier sitio)
- ✅ Frontend servido por el mismo Railway (sin CORS, sin servicios extra)
- ✅ Persistencia en Postgres (sin `data.json`)
- ✅ Auth con API Key
- ✅ Sin puertos abiertos en el NAS
- ✅ Sin dependencias del ecosistema local
