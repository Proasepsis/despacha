# Despacha

Sistema de automatización de cortes de facturación para despacho.

## Levantar en desarrollo

```bash
cp .env.example .env
# Editar .env con valores reales (SECRET_KEY, DB_PASSWORD, etc.)
docker compose up --build
```

## Acceso al admin

http://localhost:8000/admin/

## Correr pruebas

```bash
docker compose exec web python manage.py test
```
