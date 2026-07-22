# Spec: toggle de punto final en lote por línea

**Fecha:** 2026-07-22
**Estado:** aprobado

## Problema

`core/adaptadores/plantilla/limpieza.py` (`limpiar_lote`) conserva intencionalmente un `.`
final cuando el lote crudo lo trae (ej. `"120010925."` → se guarda igual en `Linea.lote`).
Hoy esa decisión es fija: el punto siempre se conserva, sin intervención del usuario. Se
necesita que, solo en las líneas donde el lote termina en `.`, el editor pueda decidir
durante la revisión si ese punto va o no en la salida final.

## Solución

Agregar un campo booleano `Linea.punto_incluido` (default `False`, es decir "se quita" por
defecto). `Linea.lote` no se modifica nunca — sigue siendo el dato limpio tal cual hoy. La
decisión de incluir o no el punto se aplica solo al momento de generar el XLS. El toggle en
la UI de revisión solo aparece en filas donde `linea.lote` termina en `.`.

## Cambios en modelos

### `Linea` (cortes/models.py)
- Agregar: `punto_incluido = models.BooleanField(default=False)`
- Migración nueva (siguiente número disponible en `cortes/migrations/`)
- Registros existentes (cortes cargados antes de este cambio, en cualquier estado) quedan
  en `punto_incluido=False` por el default de la migración — sin backfill manual.
- Efecto retroactivo esperado: para cortes ya `generado`, no aplica (el XLS ya se entregó
  con el punto, como era el comportamiento anterior). Para cortes en `en_revision` con
  líneas ya cargadas, al generar ahora se les quitará el punto final por defecto salvo que
  el editor active el toggle en la línea correspondiente — esto es un cambio de
  comportamiento intencional y aceptado.

## Edición (autosave)

`cortes/views.py` (`EditarCorteView.post`, rama `tipo == "linea"`, líneas 303-327):
- Whitelist actual (línea 305) solo permite `cantidad_unidades`. Agregar `punto_incluido`
  a la condición, con su propia rama de validación (paralela al bloque `cantidad_unidades`).
- Valor recibido se interpreta como booleano igual que `subsanar_novedad` en el bloque de
  `documento` (línea 284): `valor = valor == "true"`.
- Igual que las demás ediciones, registrar auditoría vía `registrar_auditoria(...)` con
  `campo="punto_incluido"`, `valor_anterior`, `valor_nuevo`.

## Template

`cortes/templates/cortes/detalle.html`, fila de `Linea` (junto al `<td>{{ linea.lote }}</td>`
existente, línea ~116):
- Si `linea.lote` termina en `.`: renderizar un checkbox
  `onchange="autosave('linea', {{ linea.id }}, 'punto_incluido', this.checked)"`,
  marcado según `linea.punto_incluido`.
- Si no termina en `.`: no renderizar nada (sin toggle, sin celda distinta a la actual).

## Generación del XLS

`cortes/servicios/generar_archivo.py`, donde hoy se escribe `linea.lote` tal cual en la
columna `lote`:

```python
lote_salida = linea.lote
if lote_salida.endswith(".") and not linea.punto_incluido:
    lote_salida = lote_salida[:-1]
```

## Backup y rollback (despliegue)

- Antes de desplegar en producción: backup de la base con `pg_dump` (mecanismo ya usado en
  el proyecto).
- La migración es aditiva (columna booleana con default, no toca `lote` ni otras columnas)
  y por lo tanto trivialmente reversible:
  - Aplicar: `python manage.py migrate cortes`
  - Revertir: `python manage.py migrate cortes <migración_anterior>` (Django hace el
    `DROP COLUMN` automáticamente, sin pérdida de otros datos).
- El dump de `pg_dump` queda como red de seguridad adicional si hiciera falta restaurar el
  estado completo previo al cambio.

## Tests a agregar

- `cortes/tests/test_generar_archivo.py` (o el archivo equivalente existente): lote sin `.`
  final → sale igual sin importar `punto_incluido`; lote con `.` y `punto_incluido=False`
  (default) → sale sin el punto; lote con `.` y `punto_incluido=True` → sale con el punto.
- `cortes/tests/test_revision.py` (o equivalente de `EditarCorteView`): `punto_incluido` se
  puede editar vía autosave sobre una `Linea` y queda registrado en `Auditoria`.

## No incluido en este spec

- Detección de puntos en posiciones distintas al final del lote (no existe ese caso hoy).
- Cambios a `limpiar_lote` o a `Linea.lote` — se mantienen exactamente como están.
- Reglas automáticas o configurables (`ReglaClasificacion`) para decidir el toggle — la
  decisión es siempre manual, por línea, durante la revisión.
