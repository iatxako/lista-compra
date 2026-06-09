# Lista de la Compra — NAS Shopping List

Web app ligera para gestionar la lista de la compra desde el móvil, con sincronización bidireccional con Notion y control por Telegram.

## Stack

- **Backend:** Python 3 (http.server — sin dependencias externas)
- **Frontend:** HTML + JS vanilla (sin frameworks)
- **Persistencia:** JSON local + Notion API (sync)
- **Control:** Telegram (vía Hermes Agent)

## Requisitos

- Python 3.10+
- Clave de API de Notion (para sincronización)

## Arranque rápido

```bash
python3 server.py
# Abrir en el navegador: http://localhost:8767
```

## APIs

| Endpoint | Método | Descripción |
|---|---|---|
| `/` | GET | Interfaz web |
| `/api/list` | GET | Lista actual en JSON |
| `/api/check` | POST | Marcar/desmarcar item |
| `/api/add` | POST | Añadir item |
| `/api/remove` | POST | Eliminar item |
| `/api/refresh` | POST | Recargar desde Notion |
| `/api/sync` | POST | Sincronizar cambios a Notion |
| `/api/reset` | POST | Vaciar lista |

## Estructura

```
.
├── server.py        # Servidor web + API REST
├── index.html       # Interfaz mobile-first
├── data.json        # Estado local (no versionado)
├── LICENSE
└── README.md
```

## v0.1.0 — Prototipo funcional

- Lista con checkboxes táctiles
- Añadir items desde la web
- Sincronización manual con Notion
- Control por Telegram vía Hermes Agent

## Próximos pasos (v2)

Ver [Hermes #40](https://app.plane.so/txako/projects/3f7aacda-d426-4b7e-9ae3-397945c37523/issues/40) para la definición de v2.
