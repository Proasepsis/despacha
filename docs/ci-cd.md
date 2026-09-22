# CI/CD de Despacha

## Flujo

El proyecto usa una sola rama estable y promueve la misma imagen inmutable:

1. Cada cambio se propone mediante un pull request hacia `main`.
2. GitHub Actions ejecuta toda la suite y construye la imagen Docker.
3. Al fusionar, la imagen `sha-<commit>` se publica en GHCR y se despliega en staging.
4. Produccion solo se actualiza desde `Promote to production`, con aprobacion del environment `production`.
5. La promocion se rechaza si la imagen solicitada no es exactamente la que esta corriendo en staging.

Los despliegues respaldan PostgreSQL en `/opt/despacha-cicd-backups`, conservan
14 dias y revierten la imagen de la aplicacion si falla el chequeo de salud.

## Runner privado

El runner temporal se instala en el servidor con la etiqueta
`despacha-deploy`. Nunca se usa para ejecutar workflows de pull requests.

1. En GitHub, abrir `Settings > Actions > Runners > New self-hosted runner`.
2. Generar el token de registro de un solo uso.
3. En el servidor, ejecutar como `root` sin publicar el token:

```bash
RUNNER_TOKEN='<token-de-un-solo-uso>' bash scripts/install-actions-runner.sh
```

El instalador verifica el SHA-256 del paquete oficial y registra un servicio
dedicado bajo el usuario `github-runner`.

## Protecciones requeridas

- Proteger `main` y exigir que el job `test` finalice correctamente.
- Crear el environment `staging` sin aprobacion manual.
- Crear el environment `production` con al menos un aprobador obligatorio.
- Restringir los workflows con permisos minimos de `contents` y `packages`.

## Promocion

Para promover, abrir `Actions > Promote to production > Run workflow` e
introducir el SHA completo del commit que esta ejecutandose en staging. El job
esperara la aprobacion del environment y verificara nuevamente la identidad de
la imagen antes de modificar produccion.
