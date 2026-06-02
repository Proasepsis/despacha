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
u, created = User.objects.get_or_create(
    username='${DJANGO_SUPERUSER_USERNAME}',
    defaults={
        'email': '${DJANGO_SUPERUSER_EMAIL:-admin@local}',
        'is_superuser': True,
        'is_staff': True,
    }
)
if created:
    u.set_password('${DJANGO_SUPERUSER_PASSWORD}')
    u.save()
    print('Superusuario creado.')
else:
    print('Superusuario ya existe.')

grupo_admin, _ = Group.objects.get_or_create(name='admin')
u.groups.add(grupo_admin)
print('Superusuario asignado al grupo admin.')
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
