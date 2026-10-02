# Despacha

> Sistema de automatización de cortes de facturación para operaciones de despacho.

Desarrollado por **Sergio Ospitia** — licenciado bajo [Apache 2.0](LICENSE).

---

## ¿Qué hace?

Despacha automatiza el ciclo completo de un **corte de facturación**:

1. **Carga** — el corte llega como archivo `.xlsx` subido por facturación, o como extracción enviada por SIIGO
2. **Revisión** — el equipo de almacenamiento revisa y ajusta documentos y líneas
3. **Generación** — el sistema produce un archivo `.xls` por ciudad y lo entrega a Google Drive o como descarga directa

Incluye deduplicación por SHA-256, franjas horarias por corte, resolución de productos contra el catálogo maestro, notificaciones por email, auditoría completa y una API de solo lectura (Vigia) para cortes generados.

---

## Despliegue

Staging y producción solo reciben imágenes construidas por GitHub Actions:

1. Un merge a `main` corre los tests, construye la imagen y la despliega en **staging**.
2. El workflow **Promote to production**, con aprobación, lleva esa misma imagen a **producción**.

Detalles en [docs/ci-cd.md](docs/ci-cd.md).

| | Producción | Staging |
|---|---|---|
| Directorio (solo configuración) | `/opt/despacha` | `/opt/despacha-dev` |
| Puerto | `8000` | `8001` |
| Base de datos | `/home/despachos/postgres-data` | `/home/despachos/postgres-data-dev` |

---

## Pruebas

```bash
DJANGO_SETTINGS_MODULE=despacha.settings_test python manage.py test
```

Usan SQLite en memoria y no necesitan `.env` ni Postgres.

---

## Stack técnico

| Capa | Tecnología |
|---|---|
| Backend | Python 3.13 · Django 5.2 |
| Base de datos | PostgreSQL 17 (prod) · SQLite (tests) |
| Servidor | Gunicorn · Docker Compose |
| Archivos Excel | openpyxl (lectura) · xlwt (escritura) |
| Almacenamiento | Google Drive API v3 (cuenta de servicio) |
| Email | SMTP Gmail (notificaciones) |

---

## Arquitectura

```
cortes/               → dominio principal: Corte, Documento, Linea, vistas, servicios
core/                 → infraestructura compartida: adaptadores de formato y destino,
                        notificaciones, auditoría, parámetros de salida
productos/            → catálogo maestro: Producto, Ciudad (solo lectura)
clientes/             → clientes por NIT
integraciones_siigo/  → recepción de extracciones de SIIGO (JSON)
api_vigia/            → API de solo lectura de cortes generados
```

### Ciclo de vida de un corte

```
Cargado → En revisión → Generado
                     ↘ Con error
```

### Roles

| Grupo | Permisos |
|---|---|
| `facturacion` | Cargar cortes y eliminar documentos de un corte en revisión |
| `almacenamiento` | Revisar, editar, dividir documentos y generar |
| `admin` | Todo lo anterior + configuración y auditoría |
| `consulta` | Solo lectura |

Guías de uso: [manual del operador](docs/manual-operador.md) y [manual del administrador](docs/manual-administrador.md).

---

## Variables de entorno

| Variable | Descripción |
|---|---|
| `SECRET_KEY` | Clave Django (obligatoria) |
| `DEBUG` | `True` / `False` |
| `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` | Hosts y orígenes separados por coma |
| `DB_NAME / DB_USER / DB_PASSWORD / DB_HOST / DB_PORT` | Conexión PostgreSQL |
| `DRIVE_SERVICE_ACCOUNT_JSON` | Ruta al JSON de la cuenta de servicio |
| `DRIVE_ROOT_FOLDER_ID` | ID de carpeta raíz en Drive |
| `EMAIL_HOST_USER / EMAIL_HOST_PASSWORD` | SMTP Gmail |
| `SIIGO_INGEST_TOKEN_SHA256` | Hash(es) SHA-256 del token del extractor SIIGO, separados por coma |
| `ENVIRONMENT` | `production` / `staging` |
| `DJANGO_SUPERUSER_*` | Superusuario inicial (creado al arrancar) |

Plantilla completa en [.env.example](.env.example).

---

## Licencia

Copyright 2026 Sergio Ospitia — [Apache License 2.0](LICENSE)
