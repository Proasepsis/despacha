#!/bin/bash
set -e

echo "==> Aplicando migraciones..."
python manage.py migrate --noinput

echo "==> Recopilando estáticos..."
python manage.py collectstatic --noinput

if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    echo "==> Verificando superusuario..."
    python manage.py shell -c "
from django.contrib.auth.models import User
if not User.objects.filter(username='${DJANGO_SUPERUSER_USERNAME}').exists():
    User.objects.create_superuser(
        username='${DJANGO_SUPERUSER_USERNAME}',
        email='${DJANGO_SUPERUSER_EMAIL:-admin@local}',
        password='${DJANGO_SUPERUSER_PASSWORD}',
    )
    print('Superusuario creado.')
else:
    print('Superusuario ya existe.')
"
fi

echo "==> Arrancando Gunicorn..."
exec gunicorn despacha.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --access-logfile -
