# STATUS — Lista de la Compra

Última actualización: 2026-06-11

---

## Estado actual

| Ítem | Estado |
|------|--------|
| Código en `main` | ✅ v3.2.0 (commit `450a610`) |
| Tag git | ✅ `v3.2.0` pusheado |
| Railway (producción) | ⚠️ **BLOQUEADO** — ver sección abajo |
| COMPRA-35 | En Review (pendiente de verificar en producción) |

---

## ⚠️ Incidente: Railway no despliega (2026-06-11)

El commit `450a610` fue pusheado a `main` con tag `v3.2.0` pero Railway **no ha arrancado un nuevo build**. Los logs siguen mostrando el arranque de las 20:42 UTC (deployment anterior, COMPRA-34).

**Síntoma**: `GET /api/receipts` devuelve 404 → código viejo (COMPRA-34) sigue activo en producción.

**Lo que se intentó**:
- `git push origin main --tags` → confirmado en GitHub
- Poll de `/api/receipts` durante varios minutos → sigue en 404
- `railway logs` → sin actividad de nuevo build

**Posibles causas**:
- Railway no detectó el push de GitHub (webhook caído o retrasado)
- Build fallando en silencio antes de llegar a los logs

**Pasos para resolver** (para el siguiente agente/sesión):
1. Abrir Railway dashboard → proyecto `lista-compra` → servicio `api` → pestaña Deployments
2. Verificar si hay un build en curso o fallado
3. Si no hay build: hacer "Redeploy" manual desde el dashboard
4. Alternativa CLI: `cd /tmp/lista-compra && railway up --service api`
5. Verificar que el build termina y `/api/receipts` devuelve `{"receipts":[],"total":null}`
6. Confirmar que la DB migró: las nuevas columnas en `items` (`price`, `store_name`, `ticket_name`, `quantity`, `unit`) y la tabla `active_receipts` deben existir. `init_db()` las crea automáticamente al arrancar.

---

## Lo que se implementó en esta sesión (v3.2.0 — COMPRA-35)

### Cambio de flujo (breaking vs COMPRA-34)

| Antes (COMPRA-34) | Ahora (COMPRA-35) |
|---|---|
| Scan desde el historial (lista ya vaciada) | Scan desde la lista activa (botón 📷 en header) |
| Un ticket por entrada del historial | Múltiples tickets por sesión (multi-tienda) |
| Datos en `receipt_json` desconectados de los items | Precio/tienda guardado directamente en cada `item` |
| Matching por Groq (poco fiable) | Fuzzy match server-side con difflib (threshold 0.65) |

### Nuevos endpoints

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/receipt` | POST | Escanea ticket contra lista activa; enriquece items con precio/tienda |
| `/api/receipts` | GET | Tickets escaneados en la sesión actual (desde último reset) |

### Eliminado

- `POST /api/history/<id>/receipt` — scan retroactivo eliminado (beta, no necesario)
- Botón "🧾 Ticket" del panel de historial

### Schema DB (nuevas columnas/tablas)

```sql
-- items (columnas nuevas, todas nullable)
ALTER TABLE items ADD COLUMN price       NUMERIC(10,2);
ALTER TABLE items ADD COLUMN store_name  TEXT;
ALTER TABLE items ADD COLUMN ticket_name TEXT;  -- nombre exacto del ticket
ALTER TABLE items ADD COLUMN quantity    NUMERIC(6,2);
ALTER TABLE items ADD COLUMN unit        TEXT;

-- history (columna nueva)
ALTER TABLE history ADD COLUMN receipts_json JSONB;  -- array de receipts por sesión

-- tabla nueva
CREATE TABLE active_receipts (
    id SERIAL PRIMARY KEY,
    store_name TEXT,
    total_amount NUMERIC(10,2),
    scanned_at TIMESTAMP DEFAULT NOW(),
    extras_json JSONB  -- artículos del ticket que no estaban en la lista
);
```

`init_db()` aplica todos estos cambios automáticamente con `ADD COLUMN IF NOT EXISTS` al arrancar.

### UX nuevo flujo

1. Usuario tiene lista activa con 10 artículos
2. Va a la frutería → compra 3 → pulsa **📷** → foto ticket → 3 artículos enriquecidos con precio + tienda
3. Va al super → compra 7 → pulsa **📷** → segundo scan → 7 artículos más
4. El botón muestra `📷 2` (cuenta de tickets en sesión)
5. En casa → pulsa 🗑️ → vacía → historial archiva todo con precios por artículo
6. Panel 🕐 → expandir entrada → cada artículo muestra precio en verde + tienda

### Archivos modificados

- `server.py`: imports (`re`, `unicodedata`, `SequenceMatcher`), helpers `_normalize()` + `_best_match()`, `init_db()`, `load_items()`, `api_reset()`, nuevos endpoints
- `index.html`: botón 📷, CSS (`.item-price`, `.has-receipts`), `render()`, `uploadActiveReceipt()`, `resetList()`, `renderHistory()`, `renderHistoryDetail()`
- `CHANGELOG.md`: v3.2.0 documentado

---

## Tareas en Plane.so (proyecto `lacompra`)

| # | Título | Estado |
|---|--------|--------|
| COMPRA-35 | Integración ticket lista activa: multi-tienda, precio por artículo | **Review** (pendiente test en producción) |
| COMPRA-33 | Métricas sobre el historial de listas | Definicion (bloqueado hasta tener datos suficientes) |

---

## Repo y servicios

| Recurso | URL/Valor |
|---------|-----------|
| GitHub | https://github.com/iatxako/lista-compra.git |
| Railway app | https://api-production-5ac6.up.railway.app |
| Railway proyecto | `lista-compra` (ID: `94900b52-18c7-4cd2-b5b2-26edcfab5a17`) |
| Railway servicio | `api` |
| Groq model | `meta-llama/llama-4-scout-17b-16e-instruct` |

---

## Stack

- **Backend**: Python 3.12, Flask 3.x, Gunicorn gthread (1 worker, 4 threads, timeout 0)
- **DB**: PostgreSQL (Railway), psycopg2-binary
- **AI**: Groq vision API (`GROQ_API_KEY` en Railway env vars)
- **Frontend**: HTML/JS vanilla, SSE para sync tiempo real, localStorage para offline
- **Auth**: Cookie HMAC-SHA256 httponly + `X-API-Key` header fallback
