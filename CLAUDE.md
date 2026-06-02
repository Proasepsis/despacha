# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

Despacha is a Django 5.2 web application that automates billing cut ("corte de facturación") processing for a dispatch/shipping operation. Users upload spreadsheet files, the system parses them into a structured internal model, resolves products against a master catalog, and generates/delivers output XLS files to configured destinations (Google Drive, browser download).

## Commands

### Development (Docker)

```bash
cp .env.example .env          # configure SECRET_KEY, DB_PASSWORD, etc.
docker compose up --build     # start postgres + web on localhost:8000
docker compose exec web python manage.py test   # run all tests
```

### Tests (local, uses SQLite in-memory)

```bash
DJANGO_SETTINGS_MODULE=despacha.settings_test python manage.py test
DJANGO_SETTINGS_MODULE=despacha.settings_test python manage.py test cortes.tests.test_procesar   # single test module
DJANGO_SETTINGS_MODULE=despacha.settings_test python manage.py test cortes.tests.test_procesar.ProcesarDocumentosTest.test_lote_se_limpia_al_procesar  # single test
```

### Migrations

```bash
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate
```

## Architecture

### Apps

- **`core`** — shared infrastructure: `ParametroSalida`, `ReglaClasificacion`, `NotificacionDestinatarios` models; the format adapter system; the destination adapter system; notification and audit services.
- **`cortes`** — the main domain: `Corte`, `CorteVersion`, `Documento`, `Linea`, `Auditoria` models; all views; all domain services.
- **`productos`** — master catalog: `Producto` and `Ciudad` models (read-only from the app's perspective).

### Format adapter system (`core/adaptadores/`)

Parsing of uploaded files is delegated to format adapters. Each adapter implements `AdaptadorFormato` (in `base.py`) with `validar(path)` and `parse(path) -> list[DocumentoInterno]`. Adapters register themselves via `@registrar` from `registry.py`. The registry auto-discovers subdirectories on first use. Currently only the `plantilla` adapter exists. To add a new format, create `core/adaptadores/<name>/` with an `__init__.py` that calls `registrar`.

The internal model (`modelo_interno.py`) is a format-neutral intermediate: `DocumentoInterno` (factura, nit, ciudad code, list of `LineaInterna`) → consumed by `cortes/servicios/procesar.py`.

### Destination adapter system (`core/adaptadores/destinos/`)

Delivering the generated XLS is handled by destination adapters implementing `AdaptadorDestino` with `entregar(bytes, filename, corte) -> ResultadoEntrega`. Available: `descarga` (browser download) and `drive` (Google Drive). The registry is a static dict in `destinos/registry.py`.

### Corte lifecycle

1. **Cargar** (`cortes/servicios/cargar.py`): SHA-256 dedup → save file → create `Corte` → adapter validates & parses → `procesar_documentos_internos` → state = `en_revision`. Sends email notification if unknown products detected.
2. **Revisar** (detail view): optimistic row-level locking via `bloqueado_por` / `bloqueado_hasta` (30-min timeout). Editors can modify `clasificador1`, `observaciones` on `Documento`; `cantidad_unidades` on `Linea`. Document split/undo-split is supported.
3. **Generar** (`cortes/servicios/generar.py`): validates no `sin_maestro` lines → generates XLS → delivers to selected destinations → increments `version_actual` → state = `generado`. Sends email notifications.

### Audit trail

All mutations go through `cortes/servicios/auditoria.py` → `Auditoria` model (field-level: old value, new value, event type, user, timestamp).

### Notifications

`core/servicios/notificaciones.py` sends SMTP email. Recipients per event are configured in `NotificacionDestinatarios` (admin). In `DEBUG` mode emails go to console; in tests they use `locmem`.

### User roles

Two Django groups: `operario` (can upload and edit), `admin` (can also force-release locks and bypass lock checks on edit/generate). Superuser setup is done via `DJANGO_SUPERUSER_*` env vars at container start.

### Settings

`despacha/settings.py` requires a real Postgres DB and a set `SECRET_KEY`. `despacha/settings_test.py` uses SQLite in-memory and no external dependencies — use it for all local testing.
