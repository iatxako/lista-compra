# Lista de la Compra — v2

App web para gestionar la lista de la compra desde cualquier sitio.

## Stack v2

- **Frontend:** HTML + JS vanilla (GitHub Pages)
- **Backend:** Python Flask + Gunicorn (Railway)
- **Persistencia:** Notion API directa (sin disco local)
- **Auth:** API Key via cabecera `X-API-Key`
- **Control:** Telegram vía Hermes Agent

## Arquitectura

```
                            ┌──────────────────┐
  Usuario (móvil) ────────▶│  GitHub Pages    │
                            │  (index.html)    │
                            └────────┬─────────┘
                                     │ API calls (con X-API-Key)
                            ┌────────▼─────────┐
                            │  Railway         │
                            │  (server.py)     │
                            └────────┬─────────┘
                                     │ Notion API
                            ┌────────▼─────────┐
                            │  Notion Page     │
                            │  (lista compra)  │
                            └──────────────────┘
```

## Despliegue

### Frontend (GitHub Pages)

El `index.html` se sirve desde GitHub Pages automáticamente.
Configurar en Settings → Pages → Source: Deploy from branch `main`, root `/`.

### Backend (Railway)

1. Crear proyecto en Railway desde el repo
2. Railway detecta `Procfile` y `railway.json` automáticamente
3. Añadir variables de entorno:

| Variable | Descripción |
|----------|-------------|
| `NOTION_TOKEN` | Token de integración de Notion |
| `NOTION_PAGE_ID` | ID de la página de la lista (default: 37a13b5c...) |
| `API_KEY` | Clave para proteger los endpoints |

4. Copiar la URL del backend (ej: `https://lista-compra.up.railway.app`)

### Configurar frontend

Abrir la app → ⚙️ (esquina superior derecha) → pegar URL del backend + API Key.

O pasar como query params:
```
https://iatxako.github.io/lista-compra/?api_url=https://lista-compra.up.railway.app&api_key=...

```

## Desarrollo local

```bash
pip install -r requirements.txt
NOTION_TOKEN=... API_KEY=... python3 server.py
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
- ✅ Frontend en GitHub Pages (CDN global)
- ✅ Persistencia directa a Notion (sin `data.json`)
- ✅ Auth con API Key
- ✅ Sin puertos abiertos en el NAS
- ✅ Sin dependencias del ecosistema local
