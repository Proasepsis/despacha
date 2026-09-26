# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

Despacha is a Django 5.2 web application that automates billing cut ("corte de facturación") processing for a dispatch/shipping operation. Users upload spreadsheet files, the system parses them into a structured internal model, resolves products against a master catalog, and generates/delivers output XLS files to configured destinations (Google Drive, browser download).

## Commands

### Development (Docker)

```bash
cp .env.example .env          # configure SECRET_KEY, DB_PASSWORD, etc.
docker compose up --build     # start postgres + web on localhost:8000
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate
```

### Tests (local — SQLite in-memory, no external deps)

```bash
DJANGO_SETTINGS_MODULE=despacha.settings_test python manage.py test
DJANGO_SETTINGS_MODULE=despacha.settings_test python manage.py test cortes.tests.test_procesar
DJANGO_SETTINGS_MODULE=despacha.settings_test python manage.py test cortes.tests.test_procesar.ProcesarDocumentosTest.test_lote_se_limpia_al_procesar
```

Always use `settings_test` for local testing. `settings.py` requires a live Postgres and a set `SECRET_KEY`.

## Architecture

### Apps

- **`core`** — shared infrastructure: `ParametroSalida`, `ReglaClasificacion`, `NotificacionDestinatarios` models; format adapter system; destination adapter system; notification and audit services.
- **`cortes`** — main domain: `Corte`, `CorteVersion`, `Documento`, `Linea`, `Auditoria`, `PresenciaCorte` models; all views; all domain services.
- **`productos`** — master catalog: `Producto` and `Ciudad` models (read-only from the app's perspective).
- **`clientes`** — `Cliente` model (NIT-keyed), populated via `manage.py importar_clientes`. Read-only reference data, not currently joined into corte processing.
- **`integraciones_siigo`** — receives billing-cut data pushed from SIIGO as JSON instead of an uploaded spreadsheet; see [SIIGO ingestion](#siigo-ingestion-integraciones_siigo).
- **`api_vigia`** — read-only external API exposing generated cortes; see [Vigia API](#vigia-read-only-api-api_vigia).

### Corte lifecycle

States: `cargado` → `en_revision` → `generado` (or `con_error` at any point).

1. **Cargar** (`cortes/servicios/cargar.py`): SHA-256 dedup → `Corte` created → adapter validates & parses → `procesar_documentos_internos` → state = `en_revision`. Triggers `notificar_sin_maestra_detectado` if unknown products found.
2. **Revisar** (detail view): optimistic row-level locking via `bloqueado_por` / `bloqueado_hasta` (30-min timeout). Editors can modify `clasificador1`, `observaciones`, `subsanar_novedad`, `factura_sufijo` on `Documento`; `cantidad_unidades` on `Linea`. Document split/undo-split supported.
3. **Generar** (`cortes/servicios/generar.py`): validates no `sin_maestro` lines → `generar_xls` → delivers to each destination → increments `version_actual` → state = `generado`. Sends email notifications.

### Corte uniqueness and additionals

A `Corte` is uniquely identified by `(fecha, numero_corte, adicional_letra)`. Normal cortes have `adicional_letra=""`. When a date/number pair already exists, the user can check "Es adicional" — the service assigns the next available letter (A, B, C...). Limit is 5 additionals (A–E) per date+number.

### Format adapter system (`core/adaptadores/`)

Each adapter implements `AdaptadorFormato` (`base.py`) with `validar(path)` and `parse(path) -> list[DocumentoInterno]`. Adapters self-register via `@registrar` decorator from `registry.py`, which auto-discovers subdirectories on first use.

**`AdaptadorPlantilla`** (the only existing adapter): reads `Hoja1`, headers on row 5. Filters rows by:
- `TIPO DE COMPROBANTE` must be in `{"F", "H", "S", "T"}` with matching `CÓDIGO COMPROBANTE` (`F→1, H→5, S→1, T→10`)
- `CUENTA CONTABLE` must start with `"14"`
- `DÉBITO O CRÉDITO` must be `"C"` — except `T+10` (traslados) which accepts both `"D"` and `"C"`

Product code is assembled from three columns: `LÍNEA(3-padded) + GRUPO(4-padded) + CÓDIGO(6-padded)` → 13-char string matching `Producto.producto`.

To add a new format: create `core/adaptadores/<name>/` with an `__init__.py` that instantiates and calls `@registrar`.

`core/adaptadores/api_siigo/convertir.py` (`filas_a_documentos_internos`) is a second adapter for SIIGO's JSON row format, but it is *not* registered through this file-upload registry — it's called directly by `cargar_ingesta` (see below), since the ingestion arrives as parsed JSON, not a file to `validar`/`parse`.

### Internal model (`core/adaptadores/modelo_interno.py`)

Format-neutral intermediate used between adapter output and `procesar_documentos_internos`:
- `DocumentoInterno(factura, nit, codigo_ciudad, lineas: list[LineaInterna])`
- `LineaInterna(producto_codigo, lote_raw, cantidad_origen, descripcion_origen)`

### Processing (`cortes/servicios/procesar.py`)

Bulk-creates `Documento` and `Linea` records. Resolves products and cities in two bulk queries. Lines with no matching `Producto` get `sin_maestro=True`; lines with inactive products get `inactivo=True`. `cantidad_unidades = cantidad_origen × producto.unidad_empaque`.

### XLS output (`cortes/servicios/generar_archivo.py`)

Generates one sheet per `Ciudad.nombre_archivo`. Each row is a `(Documento, Linea)` pair. Fixed 31-column layout (see `COLUMNAS` list). Static fields (punto, identificacion, nombre, etc.) come from `ParametroSalida` key-value config. `factura_completa = doc.factura + doc.factura_sufijo`. Output file name: `MMM D corte N.xls` (v2+ appends ` (vN)`).

### Destination adapter system (`core/adaptadores/destinos/`)

Each adapter implements `AdaptadorDestino` with `entregar(bytes, filename, corte) -> ResultadoEntrega`. Registry is a static dict in `destinos/registry.py`.

- **`descarga`**: browser download (returns bytes to the view).
- **`drive`**: uploads to Google Drive via service account. Folder structure: `DRIVE_ROOT_FOLDER_ID / MONTH_NAME / DAY`. Retries 3 times with backoff (1s, 3s, 10s). Requires env vars `DRIVE_SERVICE_ACCOUNT_JSON` and `DRIVE_ROOT_FOLDER_ID`.

### Locking (`cortes/servicios/bloqueo.py`)

Optimistic row-level lock on `Corte`. `intentar_tomar_bloqueo` succeeds if lock is free or expired. `refrescar_bloqueo` extends by 30 min. `liberar_bloqueo(forzado_por_admin=True)` records an audit event. Lock expiry is also cleared lazily in `info_bloqueo`.

### Document split (`cortes/servicios/split.py`)

`partir_documento(doc, lineas_ids, user)` moves selected lines to a new `Documento` with an auto-suffixed factura (`<original>A`, `<original>B`...). `deshacer_split` reverses this and deletes the child document. Both operations record audit events. Split is only reversible while state is `en_revision`.

### Real-time presence (`PresenciaCorte`)

`PresenciaPingView` (POST `/cortes/<pk>/presencia/`) upserts a `PresenciaCorte` record; GET returns users seen within the last 25 seconds and auto-purges stale rows.

### Audit trail (`core/servicios/auditoria.py`)

All mutations call `registrar_auditoria(usuario, objeto_tipo, objeto_id, tipo_evento, campo, valor_anterior, valor_nuevo, metadata)` → `Auditoria` model. `cortes/servicios/auditoria.py` is a re-export shim for backwards compatibility. Failed login attempts are captured via Django signal in `cortes/signals/__init__.py`.

### Notifications (`core/servicios/notificaciones.py`)

SMTP via Google Workspace. Recipients per event (corte_generado, corte_regenerado, sin_maestro_detectado) configured in `NotificacionDestinatarios` (comma- or newline-separated emails). `ENVIRONMENT=staging` adds `[STAGING]` prefix to subjects. In `DEBUG` mode emails go to console; in tests they use `locmem`. Failures are logged and recorded as `notificacion_fallida` audit events.

### User roles

Four Django groups control access:
- **`facturacion`** — can upload cortes (`CargarCorteView`)
- **`almacenamiento`** — can edit documents/lines and generate output (`EditarCorteView`, `GenerarCorteView`, split operations)
- **`admin`** — all of the above, plus force-release locks (`ForzarLiberacionView`)
- Superuser setup via `DJANGO_SUPERUSER_*` env vars at container start.

### Configurable output parameters (`ParametroSalida`)

Key-value store managed in Django admin. Keys used by `generar_archivo.py`: `punto`, `identificacion`, `nombre`, `direccion`, `tipo_doc_ref`, `estado_articulo`, `ciudad_default`.

### Corte suggestion heuristic

`cortes/servicios/corte_por_hora.py`: returns `2` if current Bogotá time < 12:00, else `1`. Corte 2 = mañana, Corte 1 = tarde. Used as default in the upload form.

### SIIGO ingestion (`integraciones_siigo`)

An alternate entry point to the corte lifecycle: `POST /api/v1/siigo/ingestions` accepts a JSON payload from an external SIIGO extraction job instead of a spreadsheet upload.

- Auth: `Authorization: Bearer <token>` checked against one or more SHA-256 hashes in `SIIGO_INGEST_TOKEN_SHA256` (comma-separated, supports rotation). Request also requires an `X-Content-SHA256` header matching the raw body hash, and an `Idempotency-Key` header equal to the payload's `extraction_id`.
- Payload is validated field-by-field (`_validate_payload` in `integraciones_siigo/views.py`), including recomputing `rows_sha256` from the canonicalized `rows` array to detect tampering, then stored verbatim as `IngestionSiigo` (dedup key: unique `extraction_id`, plus a `rows_sha256` index used later for corte-level dedup).
- The endpoint only *receives and stores* the ingestion (returns `202`/`200 duplicate`); it does **not** create a `Corte`. Turning an `IngestionSiigo` into a `Corte` is a separate, manual step: `cargar_ingesta()` (`cortes/servicios/cargar_ingesta.py`), invoked from the Django admin action "Crear corte desde esta ingesta" on `IngestionSiigo`. It converts `payload["rows"]` via `filas_a_documentos_internos`, dedups on `Corte.hash_sha256 == ingestion.rows_sha256`, and otherwise follows the same `procesar_documentos_internos` → `en_revision` path as a normal upload.
- **Billing windows:** rows may carry `fecha_actualizacion` (YYYYMMDD, SIIGO col AM) and `hora_actualizacion` (HHMMSS, col AN). Each document takes the earliest time of its rows, and `cargar_ingesta` keeps only documents inside `ventana_corte()` (`cortes/servicios/corte_por_hora.py`): Corte 2 = [16:00 previous day, 11:00), Corte 1 = [11:00, 16:00), Bogotá local time. Documents without a time are always kept. If no `numero_corte` is given, it is derived from `ingestion.generated_at`.
- **Schema 1.1 (extractor v0.2):** the endpoint accepts `schema_version` `"1.0"` and `"1.1"`. A 1.1 payload carries `cut = {nombre, desde, hasta, ...}`: the extractor already filtered rows to `(desde, hasta]`, so `cargar_ingesta` does not re-filter, takes the corte date from `cut.hasta` (Bogotá), and maps names, which run opposite to Despacha's: `corte_1` (11:00 run, morning) → Corte 2, `corte_2` (16:00 run, afternoon) → Corte 1. `extra`/`recuperacion` fall back to `generated_at`.
- Documents are grouped by `(tipo_comprobante, codigo_comprobante, numero_documento)` in both adapters: the same number can exist as `F` and `T`.

### Vigia read-only API (`api_vigia`)

Read-only JSON API under `/api/v1/vigia/` for external systems to pull *already-generated* cortes (`estado="generado"` only — nothing in `cargado`/`en_revision` is ever exposed).

- Auth (`api_vigia/auth.py`, `@autenticar_vigia`): `Authorization: Bearer vigia_<identificador>_<secret>` checked against `CredencialVigia.token_sha256`, plus an optional per-credential IP allowlist (`ips_permitidas`, CIDR-aware). Credentials are created via `manage.py crear_credencial_vigia`. `ultimo_uso_en`/`ultima_ip` are throttled to update at most every 30s.
- Endpoints: `GET cortes` (cursor-paginated list, filterable by `fecha_desde/hasta` and `actualizado_desde`), `GET cortes/<id>` (full detail with paginated `documentos`, supports `If-None-Match`/`ETag` caching keyed off the latest `CorteVersion.archivo_hash`), `GET documentos` (cross-corte documents for a given day, filterable by `tipo`).
- Row serialization reuses `cortes/servicios/generar_archivo.py::construir_fila_salida` so the API reflects the exact same output columns as the generated XLS.
