# AGENTS.md

## Commands

```bash
# All local testing (SQLite in-memory, no .env)
DJANGO_SETTINGS_MODULE=despacha.settings_test python manage.py test
DJANGO_SETTINGS_MODULE=despacha.settings_test python manage.py test cortes.tests.test_procesar
DJANGO_SETTINGS_MODULE=despacha.settings_test python manage.py test cortes.tests.test_procesar.ProcesarDocumentosTest.test_lote_se_limpia_al_procesar

# Docker dev
docker compose up --build
docker compose exec web python manage.py test
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate
```

## Settings split

- `despacha/settings.py` — Postgres, reads `.env`, requires `SECRET_KEY`. **Will fail without Postgres.**
- `despacha/settings_test.py` — SQLite `:memory:`, hardcodes test secret, no env deps. **Always use this for local testing.**

## Apps

- `core/` — shared: format adapters (`core/adaptadores/`), destination adapters (`core/adaptadores/destinos/`), notifications (`core/servicios/notificaciones.py`), audit (`core/servicios/auditoria.py`)
- `cortes/` — main domain: `Corte`, `CorteVersion`, `Documento`, `Linea`, `Auditoria` models + services (cargar, procesar, generar, revision, split, bloqueo, corte_por_hora)
- `productos/` — read-only master catalog: `Producto`, `Ciudad` models (populated via `manage.py importar_productos`)

## Corte lifecycle

`cargado` → `en_revision` → `generado`. All mutations go through `cortes/servicios/auditoria.py` (field-level audit trail into `Auditoria` model).

## Conventions

- **Everything in Spanish** — models, fields, views, templates, comments. Language `es-co`, timezone `America/Bogota`.
- **Format adapters** in `core/adaptadores/<name>/`, register via `@registrar` decorator. Internal model: `DocumentoInterno` → `LineaInterna` (`core/adaptadores/modelo_interno.py`).
- **Destination adapters** in `core/adaptadores/destinos/` (`descarga`, `drive`), registry is a static dict in `destinos/registry.py`.
- **Tests** use Django `TestCase`, create model instances in `setUp` (no fixture files). Email uses `locmem` backend.
- **User groups**: `operario` (upload/edit), `admin` (force-release locks, bypass checks).
- **Entrypoint** (`scripts/entrypoint.sh`): auto-runs `migrate` → `collectstatic` → optional superuser creation → `gunicorn`.
- **Explicit settings override required** — `manage.py` defaults to `despacha.settings`; must pass `DJANGO_SETTINGS_MODULE=despacha.settings_test` for local work.
