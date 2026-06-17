# Spec: tipo_comprobante automático por documento

**Fecha:** 2026-06-17
**Estado:** aprobado

## Problema

El campo `tipo_comprobante` en `Corte` es ingresado manualmente por el usuario al cargar
un archivo. Esto es propenso a error y redundante: el adaptador ya lee el valor `TIPO DE
COMPROBANTE` de cada fila del Excel para filtrarlas. Además, un archivo puede mezclar
múltiples tipos (F, H, S, T) en documentos distintos, por lo que el nivel correcto de
granularidad es el `Documento`, no el `Corte`.

## Solución

Propagar el tipo detectado por el adaptador a través del pipeline interno hasta `Documento`.
Eliminar el campo del formulario de carga y del modelo `Corte`.

## Pipeline de datos

```
Excel (columna TIPO DE COMPROBANTE)
  → adaptador.py: toma el tipo de la primera línea del grupo por factura
  → DocumentoInterno.tipo_comprobante  (campo nuevo, str, ej: "F")
  → procesar.py: lo lee y lo guarda en Documento
  → Documento.tipo_comprobante  (campo nuevo en el modelo)
```

## Cambios en modelos

### `Documento` (cortes/models.py)
- Agregar: `tipo_comprobante = CharField(max_length=1, blank=True, default="")`
- Migración nueva: `0008_documento_tipo_comprobante`
- Registros existentes quedan con `tipo_comprobante=""` (aceptable, dato no existía antes)

### `Corte` (cortes/models.py)
- Eliminar: `tipo_comprobante`
- Incluir en la misma migración `0008`

## Cambios en el adaptador

`core/adaptadores/modelo_interno.py`:
- Agregar `tipo_comprobante: str = ""` a `DocumentoInterno`

`core/adaptadores/plantilla/adaptador.py`:
- Al agrupar filas por factura, tomar el `tipo_comprobante` de la primera línea del grupo
- Asignarlo al `DocumentoInterno` correspondiente

## Cambios en procesamiento

`cortes/servicios/procesar.py`:
- En `_crear_linea_con_producto` y creación de `Documento`, leer `doc_interno.tipo_comprobante`
- Guardarlo en `Documento.tipo_comprobante`

## Formulario de carga

`cortes/forms.py`:
- Eliminar campo `tipo_comprobante`

`cortes/views.py` (`CargarCorteView`):
- Eliminar `tipo_comprobante=form.cleaned_data.get("tipo_comprobante", "")` al crear el corte

`cortes/templates/cortes/cargar.html`:
- Eliminar el bloque label + input de tipo_comprobante

## Vista de lista

`cortes/views.py` (`ListaCortesView.get_queryset`):
- Agregar anotación:
  ```python
  .annotate(tipos=StringAgg(
      "documentos__tipo_comprobante",
      delimiter="·",
      distinct=True,
      ordering="documentos__tipo_comprobante"
  ))
  ```

`cortes/templates/cortes/lista.html`:
- Reemplazar `{{ corte.tipo_comprobante|default:"—" }}` por `{{ corte.tipos|default:"—" }}`

## Vista de detalle

`cortes/templates/cortes/detalle.html`:
- Agregar badge `tipo_comprobante` por fila de documento, entre NIT y conteo de líneas
- Estilo: discreto, monoespacio, consistente con el resto del detalle

```
DOC001  |  800123456  |  F  |  EMBALAR  |  3 líneas
```

## Tests a actualizar / agregar

- `core/tests/test_adaptador_plantilla_filtro.py`: verificar que `DocumentoInterno.tipo_comprobante` se llena correctamente
- `cortes/tests/test_procesar.py`: verificar que `Documento.tipo_comprobante` se guarda desde el interno
- `cortes/tests/test_vista_cargar.py`: remover referencias al campo `tipo_comprobante` en el form
- `cortes/tests/test_revision.py`: setup de `Documento` ya no incluye `tipo_comprobante` en `Corte`

## No incluido en este spec

- Filtro de lista por tipo_comprobante (spec separado)
- Edición manual del tipo por documento (no requerido)
