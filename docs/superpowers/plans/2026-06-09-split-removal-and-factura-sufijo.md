# Split Removal + Subsanar Novedad Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Quitar el split del front-end y agregar campo de sufijo de factura (`subsanar_novedad` + `factura_sufijo`) en `Documento`, con UI en detalle y salida en el XLS.

**Architecture:** Parte 1 es puro HTML — se eliminan bloques en `detalle.html`. Parte 2 agrega dos campos al modelo `Documento`, expone su edición vía el endpoint `editar_corte` existente, aplica el sufijo en `generar_archivo.py`, y agrega controles en `detalle.html`.

**Tech Stack:** Django 5.2, vanilla JS, xlwt (generación XLS), xlrd (tests XLS).

---

## File Map

| Archivo | Tipo | Qué cambia |
|---------|------|-----------|
| `cortes/templates/cortes/detalle.html` | Modify | Eliminar split; agregar checkbox novedad + input sufijo + `toggleNovedad()` |
| `cortes/models.py` | Modify | +`subsanar_novedad`, +`factura_sufijo` en `Documento` |
| `cortes/migrations/0003_documento_novedad.py` | Create | Migración auto-generada |
| `cortes/views.py` | Modify | Whitelist ampliada, lógica bool, limpiar sufijo, guard |
| `cortes/servicios/generar_archivo.py` | Modify | `factura_completa = doc.factura + doc.factura_sufijo` |
| `cortes/tests/test_revision.py` | Modify | +4 tests nuevos para novedad/sufijo |
| `cortes/tests/test_generar.py` | Modify | +1 test XLS con sufijo |

---

## Task 1: Quitar split del front-end (`detalle.html`)

**Files:**
- Modify: `cortes/templates/cortes/detalle.html`

No hay tests automatizados para esta tarea — es solo HTML. Verificación manual.

- [ ] **Paso 1.1: Eliminar el bloque Partir / Deshacer split**

Localizar y eliminar el bloque completo (actualmente líneas ~77–81):

```html
{% if not doc.creado_por_split %}
<button data-parent-doc-id="{{ doc.id }}" onclick="abrirSplit({{ doc.id }})" class="btn" style="font-size:11px;padding:.2rem .6rem;background:var(--warning-dim);color:var(--warning);border:1px solid rgba(251,191,36,.25);">Partir</button>
{% else %}
<button data-parent-doc-id="{{ doc.id }}" onclick="deshacerSplit({{ doc.id }})" class="btn btn-ghost" style="font-size:11px;padding:.2rem .6rem;">Deshacer split</button>
{% endif %}
```

Resultado esperado: solo queda el botón "Ver líneas" al final de la sección `{% if es_editor %}`.

- [ ] **Paso 1.2: Eliminar la columna checkbox del `<thead>`**

Reemplazar:
```html
<th style="width:32px;">{% if es_editor %}<input type="checkbox" disabled>{% endif %}</th>
```
Con nada (eliminar esa línea completamente). La tabla pasa de 6 columnas a 5.

- [ ] **Paso 1.3: Eliminar la celda checkbox de cada fila del `<tbody>`**

Eliminar el `<td>` completo:
```html
<td style="text-align:center;">
    {% if es_editor and not doc.creado_por_split %}
    <input type="checkbox" class="split-check-{{ doc.id }}" data-parent-doc-id="{{ doc.id }}" value="{{ linea.id }}">
    {% endif %}
</td>
```

- [ ] **Paso 1.4: Eliminar `abrirSplit()` y `deshacerSplit()` del bloque `{% verbatim %}`**

Localizar y eliminar las dos funciones completas (actualmente ~líneas 206–232):

```js
function abrirSplit(docId) {
    var checks = document.querySelectorAll('.split-check-' + docId + ':checked');
    var ids = [];
    checks.forEach(function(c) { ids.push(parseInt(c.value)); });
    if (!ids.length) { alert('Selecciona al menos una línea para mover.'); return; }
    if (!confirm('¿Mover ' + ids.length + ' línea(s) a un documento aparte?')) return;
    fetch('/cortes/' + CORTE_ID + '/split/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCSRF() },
        body: JSON.stringify({documento_id: docId, lineas_ids: ids})
    }).then(function(r) {
        if (r.ok) location.reload();
        else r.json().then(function(d) { alert(d.error); });
    });
}

function deshacerSplit(docId) {
    if (!confirm('¿Deshacer el split y devolver las líneas al documento original?')) return;
    fetch('/cortes/' + CORTE_ID + '/deshacer-split/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCSRF() },
        body: JSON.stringify({documento_id: docId})
    }).then(function(r) {
        if (r.ok) location.reload();
        else r.json().then(function(d) { alert(d.error); });
    });
}
```

- [ ] **Paso 1.5: Verificar leyendo el archivo**

Confirmar que:
- No existe ninguna referencia a `abrirSplit`, `deshacerSplit`, `split-check`, `creado_por_split`, `Partir` ni `Deshacer split`.
- El `<thead>` de la tabla de líneas tiene 5 `<th>` (Referencia, Descripción, Lote, Cantidad, columna vacía de warnings).
- El botón "Ver líneas" aún existe en ambas ramas (`{% if es_editor %}` y `{% else %}`).

```bash
grep -n "split\|Partir\|Deshacer\|creado_por" cortes/templates/cortes/detalle.html
```

Resultado esperado: sin coincidencias.

- [ ] **Paso 1.6: Commit**

```bash
git add cortes/templates/cortes/detalle.html
git commit -m "feat: remove split buttons and checkboxes from detalle frontend"
```

---

## Task 2: Agregar campos al modelo `Documento`

**Files:**
- Modify: `cortes/models.py`
- Create: `cortes/migrations/0003_documento_novedad.py` (auto-generada)
- Modify: `cortes/tests/test_revision.py`

- [ ] **Paso 2.1: Escribir el test que fallará**

Agregar al final de la clase `VistaRevisionTest` en `cortes/tests/test_revision.py`:

```python
def test_documento_campos_novedad_defaults(self):
    nuevo = Documento.objects.create(
        corte=self.corte,
        factura="NUEVO001",
        nit="999999",
        clasificador1="EMBALAR",
        observaciones="NO PRIORIDAD",
    )
    self.assertFalse(nuevo.subsanar_novedad)
    self.assertEqual(nuevo.factura_sufijo, "")
```

- [ ] **Paso 2.2: Ejecutar el test — debe fallar**

```bash
DJANGO_SETTINGS_MODULE=despacha.settings_test .venv/bin/python manage.py test cortes.tests.test_revision.VistaRevisionTest.test_documento_campos_novedad_defaults
```

Resultado esperado: `AttributeError: 'Documento' object has no attribute 'subsanar_novedad'`

- [ ] **Paso 2.3: Agregar los campos al modelo**

En `cortes/models.py`, dentro de la clase `Documento`, después de `observaciones`:

```python
subsanar_novedad = models.BooleanField(default=False)
factura_sufijo   = models.CharField(max_length=10, blank=True, default="")
```

- [ ] **Paso 2.4: Generar la migración**

```bash
.venv/bin/python manage.py makemigrations cortes --name documento_novedad
```

Resultado esperado: `Migrations for 'cortes': cortes/migrations/0003_documento_novedad.py`

- [ ] **Paso 2.5: Ejecutar el test — debe pasar**

```bash
DJANGO_SETTINGS_MODULE=despacha.settings_test .venv/bin/python manage.py test cortes.tests.test_revision.VistaRevisionTest.test_documento_campos_novedad_defaults
```

Resultado esperado: `OK`

- [ ] **Paso 2.6: Ejecutar todos los tests**

```bash
DJANGO_SETTINGS_MODULE=despacha.settings_test .venv/bin/python manage.py test
```

Resultado esperado: todos en `OK`, sin errores.

- [ ] **Paso 2.7: Commit**

```bash
git add cortes/models.py cortes/migrations/0003_documento_novedad.py cortes/tests/test_revision.py
git commit -m "feat: add subsanar_novedad and factura_sufijo fields to Documento"
```

---

## Task 3: Actualizar endpoint autosave (`views.py`)

**Files:**
- Modify: `cortes/views.py`
- Modify: `cortes/tests/test_revision.py`

- [ ] **Paso 3.1: Escribir los 4 tests que fallarán**

Agregar a `VistaRevisionTest` en `cortes/tests/test_revision.py`:

```python
def test_autosave_subsanar_novedad_activar(self):
    self._tomar_bloqueo()
    response = self.client.post(
        reverse("editar_corte", args=[self.corte.pk]),
        json.dumps({"tipo": "documento", "id": self.doc.pk,
                    "campo": "subsanar_novedad", "valor": "true"}),
        content_type="application/json",
    )
    self.assertEqual(response.status_code, 200)
    self.assertTrue(response.json()["ok"])
    self.doc.refresh_from_db()
    self.assertTrue(self.doc.subsanar_novedad)

def test_autosave_factura_sufijo_con_novedad_activa(self):
    self._tomar_bloqueo()
    self.doc.subsanar_novedad = True
    self.doc.save()
    response = self.client.post(
        reverse("editar_corte", args=[self.corte.pk]),
        json.dumps({"tipo": "documento", "id": self.doc.pk,
                    "campo": "factura_sufijo", "valor": "A"}),
        content_type="application/json",
    )
    self.assertEqual(response.status_code, 200)
    self.assertTrue(response.json()["ok"])
    self.doc.refresh_from_db()
    self.assertEqual(self.doc.factura_sufijo, "A")

def test_autosave_factura_sufijo_sin_novedad_rechazado(self):
    self._tomar_bloqueo()
    response = self.client.post(
        reverse("editar_corte", args=[self.corte.pk]),
        json.dumps({"tipo": "documento", "id": self.doc.pk,
                    "campo": "factura_sufijo", "valor": "A"}),
        content_type="application/json",
    )
    self.assertEqual(response.status_code, 400)

def test_desactivar_novedad_limpia_sufijo(self):
    self._tomar_bloqueo()
    self.doc.subsanar_novedad = True
    self.doc.factura_sufijo = "AA"
    self.doc.save()
    response = self.client.post(
        reverse("editar_corte", args=[self.corte.pk]),
        json.dumps({"tipo": "documento", "id": self.doc.pk,
                    "campo": "subsanar_novedad", "valor": "false"}),
        content_type="application/json",
    )
    self.assertEqual(response.status_code, 200)
    self.doc.refresh_from_db()
    self.assertFalse(self.doc.subsanar_novedad)
    self.assertEqual(self.doc.factura_sufijo, "")
```

- [ ] **Paso 3.2: Ejecutar los tests — deben fallar**

```bash
DJANGO_SETTINGS_MODULE=despacha.settings_test .venv/bin/python manage.py test cortes.tests.test_revision.VistaRevisionTest.test_autosave_subsanar_novedad_activar cortes.tests.test_revision.VistaRevisionTest.test_autosave_factura_sufijo_con_novedad_activa cortes.tests.test_revision.VistaRevisionTest.test_autosave_factura_sufijo_sin_novedad_rechazado cortes.tests.test_revision.VistaRevisionTest.test_desactivar_novedad_limpia_sufijo
```

Resultado esperado: `FAIL` (los 4 tests).

- [ ] **Paso 3.3: Actualizar el bloque `tipo == "documento"` en `views.py`**

En `cortes/views.py`, reemplazar el bloque completo `if tipo == "documento":` (desde la línea con `doc = get_object_or_404(...)` hasta el `registrar_auditoria(...)` inclusive) con:

```python
if tipo == "documento":
    doc = get_object_or_404(Documento, pk=obj_id, corte=corte)
    valor_anterior = getattr(doc, campo)
    if campo not in ("clasificador1", "observaciones", "subsanar_novedad", "factura_sufijo"):
        return HttpResponseBadRequest(f"Campo no editable: {campo}")
    if campo == "factura_sufijo" and not doc.subsanar_novedad:
        return HttpResponseBadRequest("No se puede editar sufijo sin novedad activa")
    if campo == "subsanar_novedad":
        valor = valor == "true"
    setattr(doc, campo, valor)
    if campo == "subsanar_novedad" and not valor:
        doc.factura_sufijo = ""
        doc.save(update_fields=[campo, "factura_sufijo"])
    else:
        doc.save(update_fields=[campo])
    registrar_auditoria(
        usuario=request.user,
        objeto_tipo="Documento",
        objeto_id=str(doc.pk),
        campo=campo,
        valor_anterior=str(valor_anterior),
        valor_nuevo=str(valor),
        tipo_evento="edicion",
    )
```

- [ ] **Paso 3.4: Ejecutar los 4 tests nuevos — deben pasar**

```bash
DJANGO_SETTINGS_MODULE=despacha.settings_test .venv/bin/python manage.py test cortes.tests.test_revision.VistaRevisionTest.test_autosave_subsanar_novedad_activar cortes.tests.test_revision.VistaRevisionTest.test_autosave_factura_sufijo_con_novedad_activa cortes.tests.test_revision.VistaRevisionTest.test_autosave_factura_sufijo_sin_novedad_rechazado cortes.tests.test_revision.VistaRevisionTest.test_desactivar_novedad_limpia_sufijo
```

Resultado esperado: `OK`

- [ ] **Paso 3.5: Ejecutar todos los tests**

```bash
DJANGO_SETTINGS_MODULE=despacha.settings_test .venv/bin/python manage.py test
```

Resultado esperado: `OK`

- [ ] **Paso 3.6: Commit**

```bash
git add cortes/views.py cortes/tests/test_revision.py
git commit -m "feat: allow editing subsanar_novedad and factura_sufijo via autosave"
```

---

## Task 4: XLS con sufijo de factura

**Files:**
- Modify: `cortes/servicios/generar_archivo.py`
- Modify: `cortes/tests/test_generar.py`

- [ ] **Paso 4.1: Escribir el test que fallará**

Agregar al final de la clase `GenerarArchivoTest` en `cortes/tests/test_generar.py`:

```python
def test_generar_xls_con_sufijo_novedad(self):
    self.doc.subsanar_novedad = True
    self.doc.factura_sufijo = "A"
    self.doc.save()

    xls_bytes = generar_xls(self.corte)
    ruta = Path("/tmp/test_gen_sufijo.xls")
    ruta.write_bytes(xls_bytes)

    wb = xlrd.open_workbook(str(ruta))
    ws = wb.sheet_by_name("BOGOTA")
    col_map = {ws.cell_value(0, c): c for c in range(ws.ncols)}

    self.assertEqual(ws.cell_value(1, col_map["documento_referencia"]), "FC001A")
    self.assertEqual(ws.cell_value(1, col_map["clasificador2"]), "FC001A")
    ruta.unlink(missing_ok=True)

def test_generar_xls_sin_sufijo_novedad(self):
    xls_bytes = generar_xls(self.corte)
    ruta = Path("/tmp/test_gen_sin_sufijo.xls")
    ruta.write_bytes(xls_bytes)

    wb = xlrd.open_workbook(str(ruta))
    ws = wb.sheet_by_name("BOGOTA")
    col_map = {ws.cell_value(0, c): c for c in range(ws.ncols)}

    self.assertEqual(ws.cell_value(1, col_map["documento_referencia"]), "FC001")
    self.assertEqual(ws.cell_value(1, col_map["clasificador2"]), "FC001")
    ruta.unlink(missing_ok=True)
```

- [ ] **Paso 4.2: Ejecutar los tests — deben fallar**

```bash
DJANGO_SETTINGS_MODULE=despacha.settings_test .venv/bin/python manage.py test cortes.tests.test_generar.GenerarArchivoTest.test_generar_xls_con_sufijo_novedad cortes.tests.test_generar.GenerarArchivoTest.test_generar_xls_sin_sufijo_novedad
```

Resultado esperado: `FAIL` — `test_generar_xls_con_sufijo_novedad` falla porque `documento_referencia` es `"FC001"` y no `"FC001A"`. `test_generar_xls_sin_sufijo_novedad` pasa (ya funciona).

- [ ] **Paso 4.3: Actualizar `generar_archivo.py`**

En `cortes/servicios/generar_archivo.py`, dentro del loop `for row_idx, (doc, linea) in enumerate(filas, start=1):`, reemplazar:

```python
valores = {
    ...
    "documento_referencia": doc.factura,
    ...
    "clasificador2": doc.factura,
    ...
}
```

Con:

```python
factura_completa = doc.factura + doc.factura_sufijo
valores = {
    ...
    "documento_referencia": factura_completa,
    ...
    "clasificador2": factura_completa,
    ...
}
```

La variable `factura_completa` va justo antes del dict `valores`, dentro del loop.

- [ ] **Paso 4.4: Ejecutar los tests nuevos — deben pasar**

```bash
DJANGO_SETTINGS_MODULE=despacha.settings_test .venv/bin/python manage.py test cortes.tests.test_generar.GenerarArchivoTest.test_generar_xls_con_sufijo_novedad cortes.tests.test_generar.GenerarArchivoTest.test_generar_xls_sin_sufijo_novedad
```

Resultado esperado: `OK`

- [ ] **Paso 4.5: Ejecutar todos los tests**

```bash
DJANGO_SETTINGS_MODULE=despacha.settings_test .venv/bin/python manage.py test
```

Resultado esperado: `OK`

- [ ] **Paso 4.6: Commit**

```bash
git add cortes/servicios/generar_archivo.py cortes/tests/test_generar.py
git commit -m "feat: apply factura_sufijo in XLS documento_referencia and clasificador2"
```

---

## Task 5: UI en `detalle.html` — checkbox novedad + input sufijo

**Files:**
- Modify: `cortes/templates/cortes/detalle.html`

No hay tests automatizados para esta tarea. Verificación manual.

- [ ] **Paso 5.1: Agregar checkbox y input al encabezado del documento (modo editor)**

En `detalle.html`, dentro del bloque `{% if es_editor %}`, después del label "PRIO" (después del `</label>` que cierra el select de observaciones) y antes del botón "Ver líneas", agregar:

```html
<label style="font-family:var(--font-mono);font-size:10px;color:var(--text-muted);display:flex;align-items:center;gap:.3rem;">
    <input type="checkbox" id="nov-{{ doc.id }}"
           data-parent-doc-id="{{ doc.id }}"
           {% if doc.subsanar_novedad %}checked{% endif %}
           onchange="toggleNovedad({{ doc.id }}, this.checked)"
           style="width:auto;">
    Subsanar novedad
</label>
<div id="sufijo-wrap-{{ doc.id }}"
     style="display:{% if doc.subsanar_novedad %}flex{% else %}none{% endif %};align-items:center;gap:.3rem;">
    <span style="font-family:var(--font-mono);font-size:11px;color:var(--text-soft);">{{ doc.factura }}</span>
    <input type="text" maxlength="10"
           id="sufijo-{{ doc.id }}"
           data-parent-doc-id="{{ doc.id }}"
           value="{{ doc.factura_sufijo }}"
           placeholder="A"
           onchange="autosave('documento', {{ doc.id }}, 'factura_sufijo', this.value)"
           style="width:60px;font-size:12px;font-family:var(--font-mono);padding:.2rem .4rem;background:var(--surface-raised);border:1px solid var(--border-mid);border-radius:4px;color:var(--text);">
</div>
```

- [ ] **Paso 5.2: Agregar función `toggleNovedad()` al script no-verbatim**

En el bloque `<script>` que está después del `{% endverbatim %}` (el que tiene `initKeyNav` y el Escape guard), agregar la función **antes** del `document.addEventListener('DOMContentLoaded', ...)`:

```js
function toggleNovedad(docId, checked) {
    autosave('documento', docId, 'subsanar_novedad', checked ? 'true' : 'false');
    var wrap = document.getElementById('sufijo-wrap-' + docId);
    if (wrap) wrap.style.display = checked ? 'flex' : 'none';
    if (!checked) {
        var inp = document.getElementById('sufijo-' + docId);
        if (inp) { inp.value = ''; autosave('documento', docId, 'factura_sufijo', ''); }
    }
}
```

- [ ] **Paso 5.3: Verificar manualmente en el browser**

- Abrir el detalle de un corte en estado `en_revision` con sesión de editor.
- Confirmar que aparece el checkbox "Subsanar novedad" junto a los selects EMB/PRIO.
- Marcar el checkbox → debe aparecer el div con el número de factura y el campo de texto.
- Escribir `A` en el input y salir del campo → debe llamar autosave y persistir.
- Recargar la página → el checkbox y el valor `A` deben seguir marcados/presentes.
- Desmarcar el checkbox → el input desaparece y el sufijo se limpia.
- Recargar → checkbox desmarcado, input no visible.

- [ ] **Paso 5.4: Commit**

```bash
git add cortes/templates/cortes/detalle.html
git commit -m "feat: add subsanar novedad checkbox and sufijo input to detalle"
```

---

## Verificación final

- [ ] Ejecutar suite completa:
```bash
DJANGO_SETTINGS_MODULE=despacha.settings_test .venv/bin/python manage.py test
```
Resultado esperado: `OK` (96+ tests).

- [ ] Reconstruir Docker y verificar migración en contenedor:
```bash
docker compose up --build -d
docker compose logs web --tail=10
```
Resultado esperado: `No migrations to apply` o la migración 0003 aplicada sin errores.
