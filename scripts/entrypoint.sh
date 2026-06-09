#!/bin/bash
set -e

echo "==> Aplicando migraciones..."
python manage.py migrate --noinput

echo "==> Recopilando estáticos..."
python manage.py collectstatic --noinput

if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    echo "==> Verificando superusuario..."
    python manage.py shell -c "
from django.contrib.auth.models import User, Group
if not User.objects.filter(username='${DJANGO_SUPERUSER_USERNAME}').exists():
    u = User.objects.create_superuser(
        username='${DJANGO_SUPERUSER_USERNAME}',
        email='${DJANGO_SUPERUSER_EMAIL:-admin@local}',
        password='${DJANGO_SUPERUSER_PASSWORD}',
    )
    grupo_admin, _ = Group.objects.get_or_create(name='admin')
    u.groups.add(grupo_admin)
    print('Superusuario creado y asignado al grupo admin.')
else:
    print('Superusuario ya existe, omitiendo.')
"
fi

echo "==> Arrancando Gunicorn..."
exec gunicorn despacha.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --worker-class gthread \
    --threads 4 \
    --timeout 120 \
    --keep-alive 65 \
    --log-level info \
    --access-logfile - \
    --error-logfile -
