# Split removal + Subsanar novedad — Diseño

**Fecha:** 2026-06-09  
**Alcance:** `detalle.html`, `cortes/models.py`, `cortes/views.py`, `cortes/servicios/generar_archivo.py`

---

## Parte 1: Quitar split del front-end

### Problema

La función "Partir" existe en el backend pero el usuario no la necesita visible. Se debe ocultar completamente del front sin tocar el backend.

### Cambios en `cortes/templates/cortes/detalle.html`

Eliminar:

1. El bloque `{% if not doc.creado_por_split %}` con el botón **Partir** y su rama `{% else %}` con **Deshacer split**:
   ```html
   {% if not doc.creado_por_split %}
   <button ... >Partir</button>
   {% else %}
   <button ... >Deshacer split</button>
   {% endif %}
   ```

2. El checkbox de selección de líneas en cada fila del tbody (solo en modo editor):
   ```html
   {% if es_editor and not doc.creado_por_split %}
   <input type="checkbox" class="split-check-{{ doc.id }}" ...>
   {% endif %}
   ```

3. La columna de checkbox en el `<thead>`:
   ```html
   <th style="width:32px;">{% if es_editor %}<input type="checkbox" disabled>{% endif %}</th>
   ```
   → reemplazar por `<th style="width:32px;"></th>` vacío (o eliminar la columna completa del thead y del tbody).

4. Las funciones JS `abrirSplit()` y `deshacerSplit()` del bloque `{% verbatim %}`.

**Backend intacto:** URLs, views, servicios de split no se tocan.

---

## Parte 2: Subsanar novedad + sufijo de factura

### Problema

Cuando una factura debe reenviarse por novedad, el número de factura en el XLS debe llevar un sufijo de letras: `5258` → `5258A` (primera novedad), `5258AA` (segunda), etc. El usuario escribe el sufijo manualmente. No todos los documentos lo necesitan.

### Modelo (`cortes/models.py`)

Dos campos nuevos en `Documento`:

```python
subsanar_novedad = models.BooleanField(default=False)
factura_sufijo   = models.CharField(max_length=10, blank=True, default="")
```

- `subsanar_novedad`: controla si el documento está en modo novedad.
- `factura_sufijo`: las letras que el usuario escribe (ej. `"A"`, `"AA"`, `"AAA"`). Se limpia cuando `subsanar_novedad` pasa a `False`.
- El campo original `factura` nunca se modifica.

Una migración nueva.

### Autosave endpoint (`cortes/views.py`)

La whitelist de campos editables para `tipo == "documento"` se amplía:

```python
# antes
if campo not in ("clasificador1", "observaciones"):
    return HttpResponseBadRequest(...)

# después
if campo not in ("clasificador1", "observaciones", "subsanar_novedad", "factura_sufijo"):
    return HttpResponseBadRequest(...)
```

- `subsanar_novedad` recibe `"true"` / `"false"` (string) desde JS → convertir a bool con `valor == "true"`.
- Cuando `subsanar_novedad` cambia a `False`, el endpoint también limpia `factura_sufijo` (lo pone en `""`).
- Si `campo == "factura_sufijo"` pero `doc.subsanar_novedad == False`, el endpoint retorna `HttpResponseBadRequest` — el sufijo solo es editable con novedad activa.
- Ambos campos se auditan con el evento `"edicion"` igual que los otros campos.

### UI en `detalle.html` (solo `{% if es_editor %}`)

En el encabezado de cada documento, a continuación de los selects EMB y PRIO:

```html
<!-- Checkbox subsanar novedad -->
<label style="font-family:var(--font-mono);font-size:10px;color:var(--text-muted);
              display:flex;align-items:center;gap:.3rem;">
  <input type="checkbox" id="nov-{{ doc.id }}"
         data-parent-doc-id="{{ doc.id }}"
         {% if doc.subsanar_novedad %}checked{% endif %}
         onchange="toggleNovedad({{ doc.id }}, this.checked)"
         style="width:auto;">
  Subsanar novedad
</label>

<!-- Input sufijo (visible solo si subsanar_novedad está activo) -->
<div id="sufijo-wrap-{{ doc.id }}"
     style="display:{% if doc.subsanar_novedad %}flex{% else %}none{% endif %};
            align-items:center;gap:.3rem;">
  <span style="font-family:var(--font-mono);font-size:11px;color:var(--text-soft);">
    {{ doc.factura }}
  </span>
  <input type="text" maxlength="10"
         id="sufijo-{{ doc.id }}"
         data-parent-doc-id="{{ doc.id }}"
         value="{{ doc.factura_sufijo }}"
         placeholder="A"
         onchange="autosave('documento', {{ doc.id }}, 'factura_sufijo', this.value)"
         style="width:60px;font-size:12px;font-family:var(--font-mono);
                padding:.2rem .4rem;background:var(--surface-raised);
                border:1px solid var(--border-mid);border-radius:4px;color:var(--text);">
</div>
```

Función JS nueva `toggleNovedad` (fuera del bloque verbatim):

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

### XLS (`cortes/servicios/generar_archivo.py`)

```python
# antes
"documento_referencia": doc.factura,
...
"clasificador2": doc.factura,

# después
factura_completa = doc.factura + doc.factura_sufijo
"documento_referencia": factura_completa,
...
"clasificador2": factura_completa,
```

---

## Archivos modificados

| Archivo | Cambio |
|---------|--------|
| `cortes/models.py` | +`subsanar_novedad`, +`factura_sufijo` en `Documento` |
| `cortes/migrations/` | Nueva migración |
| `cortes/views.py` | Whitelist ampliada + lógica bool + limpiar sufijo al desactivar |
| `cortes/servicios/generar_archivo.py` | `factura_completa = doc.factura + doc.factura_sufijo` |
| `cortes/templates/cortes/detalle.html` | Eliminar split; agregar checkbox + input sufijo + `toggleNovedad()` |

---

## Fuera de alcance

- Vista de solo lectura (no editor): muestra el estado pero no permite editar — ya manejado por `{% if es_editor %}`.
- Validación de formato del sufijo (solo letras): el `maxlength=10` es suficiente por ahora.
- Paginación ni filtros por `subsanar_novedad` en la lista de cortes.
