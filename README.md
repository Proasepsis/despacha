# Despacha

> Sistema de automatización de cortes de facturación para operaciones de despacho.

Desarrollado por **Sergio Ospitia** — licenciado bajo [Apache 2.0](LICENSE).

---

## ¿Qué hace?

Despacha automatiza el ciclo completo de un **corte de facturación**:

1. **Carga** — el usuario sube un archivo `.xlsx` con el corte del día
2. **Revisión** — el equipo de almacenamiento revisa y ajusta documentos y líneas
3. **Generación** — el sistema produce un archivo `.xls` estructurado y lo entrega a Google Drive o descarga directa

Incluye deduplicación por SHA-256, detección automática de tipo de comprobante, resolución de productos contra catálogo maestro, notificaciones por email y trazabilidad completa de auditoría.

---

## Instalación rápida

En cualquier servidor Ubuntu/Debian limpio (instala Docker y Git si no están):

```bash
curl -fsSL https://raw.githubusercontent.com/Proasepsis/despacha/main/setup.sh | bash -s prod
```

O descárgalo primero para revisarlo:

```bash
curl -O https://raw.githubusercontent.com/Proasepsis/despacha/main/setup.sh
bash setup.sh prod      # producción  → puerto 8000
bash setup.sh dev       # desarrollo  → puerto 8001
bash setup.sh           # interactivo → pregunta el modo
```

El script genera automáticamente claves seguras (`openssl rand`), crea el `.env`, los directorios necesarios y levanta los contenedores. Al final muestra las credenciales del superusuario.

---

## Entornos

| | Producción | Desarrollo |
|---|---|---|
| Directorio | `/opt/despacha` | `/opt/despacha-dev` |
| Puerto | `8000` | `8001` |
| Base de datos | `/home/despachos/postgres-data` | `/home/despachos/postgres-data-dev` |
| `DEBUG` | `False` | `True` |

Ambos entornos son completamente independientes — comparten el mismo `docker-compose.yml` parametrizado.

---

## Comandos del día a día

```bash
# Actualizar y redesplegar
git pull && docker compose up --build -d

# Ver logs en vivo
docker compose logs web -f

# Apagar (conserva la base de datos)
docker compose down

# Apagar y borrar base de datos (útil en dev)
docker compose down -v

# Correr pruebas
DJANGO_SETTINGS_MODULE=despacha.settings_test python manage.py test

# Acceder al admin Django
http://localhost:8000/admin/
```

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
cortes/          → dominio principal: Corte, Documento, Linea, vistas, servicios
core/            → infraestructura compartida: adaptadores de formato y destino,
│                  notificaciones, auditoría, parámetros de salida
├── adaptadores/
│   ├── plantilla/   → único formato soportado (Excel PLANTILLA)
│   └── destinos/    → drive, descarga
productos/       → catálogo maestro: Producto, Ciudad (solo lectura)
```

### Ciclo de vida de un corte

```
Cargado → En revisión → Generado
                     ↘ Con error
```

- **Cargado**: SHA-256 dedup → adaptador valida y parsea → se crean Documentos y Líneas
- **En revisión**: edición con bloqueo optimista (30 min), split/undo de documentos, presencia en tiempo real
- **Generado**: validación → XLS por ciudad → entrega a destinos → notificación por email

### Roles

| Grupo | Permisos |
|---|---|
| `facturacion` | Cargar archivos |
| `almacenamiento` | Revisar, editar, generar, hacer split |
| `admin` | Todo lo anterior + forzar liberación de bloqueos |

---

## Variables de entorno

| Variable | Descripción |
|---|---|
| `SECRET_KEY` | Clave Django (obligatoria) |
| `DEBUG` | `True` / `False` |
| `ALLOWED_HOSTS` | Hosts separados por coma |
| `DB_NAME / DB_USER / DB_PASSWORD` | Credenciales PostgreSQL |
| `PORT` | Puerto del host (default `8000`) |
| `POSTGRES_DATA_PATH` | Ruta del volumen de datos |
| `DRIVE_SERVICE_ACCOUNT_JSON` | Ruta al JSON de la cuenta de servicio |
| `DRIVE_ROOT_FOLDER_ID` | ID de carpeta raíz en Drive |
| `EMAIL_HOST_USER / EMAIL_HOST_PASSWORD` | SMTP Gmail |
| `ENVIRONMENT` | `production` / `development` / `staging` |
| `DJANGO_SUPERUSER_*` | Superusuario inicial (creado al arrancar) |

---

## Licencia

Copyright 2026 Sergio Ospitia — [Apache License 2.0](LICENSE)
