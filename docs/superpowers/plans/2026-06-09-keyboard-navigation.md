# Keyboard Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir navegación completa con teclado en la lista de cortes y el detalle de corte usando roving tabindex, sin mouse.

**Architecture:** Un helper `initKeyNav()` en `base.html` implementa el patrón roving tabindex. `lista.html` lo usa para navegar entre filas de la tabla; `detalle.html` lo usa para navegar entre encabezados de documento y agrega un guard de Escape para volver desde controles internos. No hay cambios de backend.

**Tech Stack:** Vanilla JS, Django templates HTML, CSS custom properties (ya existentes).

---

## File Map

| Archivo | Tipo | Qué cambia |
|---------|------|-----------|
| `cortes/templates/cortes/base.html` | Modify | + CSS focus styles (2 reglas) + función `initKeyNav()` |
| `cortes/templates/cortes/lista.html` | Modify | `<tr>` reemplaza `onclick` por `data-corte-url`; + script `initKeyNav` |
| `cortes/templates/cortes/detalle.html` | Modify | encabezados reciben `data-doc-header`/`data-doc-id`; controles internos reciben `data-parent-doc-id`; + script `initKeyNav` + guard Escape |

---

## Task 1: CSS de foco + helper `initKeyNav()` en `base.html`

**Files:**
- Modify: `cortes/templates/cortes/base.html`

### Paso 1.1 — Agregar reglas CSS de foco

En `base.html`, dentro del bloque `<style>`, después del comentario `/* ══ UTILS */` (aproximadamente línea 570), agregar antes del bloque `/* ══ RESPONSIVE */`:

```css
        /* ══ KEYBOARD NAV ═════════════════════════════════════════ */
        [data-nav-item]:focus {
            outline: none;
            box-shadow: inset 0 0 0 2px var(--accent);
        }

        tbody tr[data-nav-item]:focus td {
            background: var(--surface-raised);
        }
```

- [ ] Agregar las dos reglas CSS en `base.html` antes del bloque `@media (max-width: 768px)`.

### Paso 1.2 — Agregar función `initKeyNav()`

En `base.html`, dentro del segundo bloque `<script>` (el que tiene `toggleTheme`, `updateToggleUI`, `DOMContentLoaded`), agregar `initKeyNav` **antes** del listener `DOMContentLoaded` existente:

```js
    function initKeyNav(items, options) {
        if (!items || items.length === 0) return;
        var opts = options || {};
        var onActivate = opts.onActivate || function() {};
        var arr = Array.from(items);

        arr.forEach(function(item, i) {
            item.setAttribute('tabindex', i === 0 ? '0' : '-1');
            item.setAttribute('data-nav-item', '');
        });

        function moveFocus(newItem) {
            arr.forEach(function(it) { it.setAttribute('tabindex', '-1'); });
            newItem.setAttribute('tabindex', '0');
            newItem.focus();
        }

        arr.forEach(function(item, i) {
            item.addEventListener('keydown', function(e) {
                if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    if (i < arr.length - 1) moveFocus(arr[i + 1]);
                } else if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    if (i > 0) moveFocus(arr[i - 1]);
                } else if (e.key === 'Enter') {
                    e.preventDefault();
                    onActivate(item);
                }
            });

            item.addEventListener('blur', function() {
                setTimeout(function() {
                    var active = document.activeElement;
                    var inGroup = arr.some(function(it) { return it === active; });
                    if (!inGroup) {
                        arr.forEach(function(it, idx) {
                            it.setAttribute('tabindex', idx === 0 ? '0' : '-1');
                        });
                    }
                }, 0);
            });
        });
    }
```

- [ ] Agregar la función `initKeyNav()` en el segundo `<script>` de `base.html`, antes de `document.addEventListener('DOMContentLoaded', ...)`.

### Paso 1.3 — Verificar manualmente

- [ ] Abrir la app en el browser.
- [ ] Abrir DevTools → Console.
- [ ] Ejecutar `typeof initKeyNav` — debe retornar `"function"`.
- [ ] No debe haber errores en consola al cargar cualquier página.

### Paso 1.4 — Commit

```bash
git add cortes/templates/cortes/base.html
git commit -m "feat: add initKeyNav helper and focus CSS to base.html"
```

- [ ] Hacer commit.

---

## Task 2: Navegación por teclado en `lista.html`

**Files:**
- Modify: `cortes/templates/cortes/lista.html`

### Paso 2.1 — Reemplazar `onclick` por `data-corte-url` en las filas

Actualmente la fila es:
```html
<tr onclick="location.href='{% url 'detalle_corte' corte.pk %}'" style="cursor:pointer;">
```

Cambiarla a:
```html
<tr data-corte-url="{% url 'detalle_corte' corte.pk %}" style="cursor:pointer;">
```

- [ ] Editar la `<tr>` del loop `{% for corte in cortes %}` en `lista.html`.

### Paso 2.2 — Agregar script al final del bloque `{% block content %}`

Agregar antes del `{% endblock %}` final:

```html
<script>
document.addEventListener('DOMContentLoaded', function() {
    var rows = document.querySelectorAll('tbody tr[data-corte-url]');
    rows.forEach(function(row) {
        row.addEventListener('click', function() {
            location.href = row.dataset.corteUrl;
        });
    });
    initKeyNav(rows, {
        onActivate: function(row) { location.href = row.dataset.corteUrl; }
    });
});
</script>
```

- [ ] Agregar el bloque `<script>` al final del content de `lista.html`.

### Paso 2.3 — Verificar manualmente

- [ ] Cargar `/cortes/` en el browser.
- [ ] Presionar Tab varias veces hasta que el foco llegue a la primera fila — debe verse el ring de `--accent` (azul/cyan según el tema).
- [ ] Presionar ↓ — el foco debe bajar a la segunda fila.
- [ ] Presionar ↑ — el foco debe volver a la primera fila.
- [ ] Presionar Enter — debe navegar al detalle del corte.
- [ ] Volver, presionar Tab hasta llegar a la tabla, luego Tab otra vez para salir — el ring debe desaparecer.
- [ ] Click en una fila con mouse — debe seguir funcionando.

### Paso 2.4 — Commit

```bash
git add cortes/templates/cortes/lista.html
git commit -m "feat: keyboard navigation on cortes list with roving tabindex"
```

- [ ] Hacer commit.

---

## Task 3: Navegación por teclado en `detalle.html`

**Files:**
- Modify: `cortes/templates/cortes/detalle.html`

### Paso 3.1 — Agregar atributos al encabezado de cada documento

Actualmente el div de encabezado (línea ~49) es:
```html
<div style="display:flex;align-items:center;justify-content:space-between;padding:.6rem 1rem;background:var(--surface-raised);border-bottom:1px solid var(--border);">
```

Cambiarlo a:
```html
<div data-doc-header data-doc-id="{{ doc.id }}" style="display:flex;align-items:center;justify-content:space-between;padding:.6rem 1rem;background:var(--surface-raised);border-bottom:1px solid var(--border);">
```

- [ ] Editar el div de encabezado en el loop `{% for doc in documentos_data %}`.

### Paso 3.2 — Agregar `data-parent-doc-id` a los controles internos (modo editor)

A todos los controles dentro del bloque `{% if es_editor %}`, agregar `data-parent-doc-id="{{ doc.id }}"`:

**Select EMB** (actualmente `id="clas1-{{ doc.id }}" onchange="..."`):
```html
<select id="clas1-{{ doc.id }}" data-parent-doc-id="{{ doc.id }}" onchange="autosave('documento', {{ doc.id }}, 'clasificador1', this.value)"
```

**Select PRIO** (actualmente `id="obs-{{ doc.id }}" onchange="..."`):
```html
<select id="obs-{{ doc.id }}" data-parent-doc-id="{{ doc.id }}" onchange="autosave('documento', {{ doc.id }}, 'observaciones', this.value)"
```

**Botón "Ver líneas"** (dentro del `{% if es_editor %}` outer block):
```html
<button data-parent-doc-id="{{ doc.id }}" onclick="toggleLineas({{ doc.id }})" class="btn btn-ghost" style="font-size:11px;padding:.2rem .6rem;">Ver líneas</button>
```

**Botón "Partir"**:
```html
<button data-parent-doc-id="{{ doc.id }}" onclick="abrirSplit({{ doc.id }})" class="btn" style="font-size:11px;padding:.2rem .6rem;background:var(--warning-dim);color:var(--warning);border:1px solid rgba(251,191,36,.25);">Partir</button>
```

**Botón "Deshacer split"**:
```html
<button data-parent-doc-id="{{ doc.id }}" onclick="deshacerSplit({{ doc.id }})" class="btn btn-ghost" style="font-size:11px;padding:.2rem .6rem;">Deshacer split</button>
```

**Botón "Ver líneas" (rama `{% else %}`, modo lectura)**:
```html
<button data-parent-doc-id="{{ doc.id }}" onclick="toggleLineas({{ doc.id }})" class="btn btn-ghost" style="font-size:11px;padding:.2rem .6rem;">Ver líneas</button>
```

**Inputs de cantidad en las líneas**:
```html
<input type="number" step="0.01" min="0.01" value="{{ linea.cantidad_unidades }}"
       data-parent-doc-id="{{ doc.id }}"
       onchange="autosave('linea', {{ linea.id }}, 'cantidad_unidades', this.value)"
       style="width:90px;font-size:12px;font-family:var(--font-mono);padding:.2rem .4rem;background:var(--surface-raised);border:1px solid var(--border-mid);border-radius:4px;color:var(--text);">
```

**Checkboxes de split**:
```html
<input type="checkbox" class="split-check-{{ doc.id }}" data-parent-doc-id="{{ doc.id }}" value="{{ linea.id }}">
```

- [ ] Agregar `data-parent-doc-id="{{ doc.id }}"` a todos los controles listados arriba.

### Paso 3.3 — Agregar script al final del bloque `{% block content %}`

Agregar justo antes del cierre `</script>` del bloque `{% verbatim %}...{% endverbatim %}` que ya existe en `detalle.html`, o mejor como un `<script>` separado **después** del bloque verbatim existente y antes de `{% endblock %}`:

```html
<script>
document.addEventListener('DOMContentLoaded', function() {
    var headers = document.querySelectorAll('[data-doc-header]');
    initKeyNav(headers, {
        onActivate: function(header) {
            toggleLineas(parseInt(header.dataset.docId));
        }
    });

    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && document.activeElement && document.activeElement.dataset.parentDocId) {
            e.preventDefault();
            var docId = document.activeElement.dataset.parentDocId;
            var header = document.querySelector('[data-doc-header][data-doc-id="' + docId + '"]');
            if (header) header.focus();
        }
    });
});
</script>
```

- [ ] Agregar el bloque `<script>` después del bloque `{% verbatim %}...{% endverbatim %}` y antes de `{% endblock %}`.

### Paso 3.4 — Verificar manualmente

- [ ] Cargar el detalle de un corte con varios documentos.
- [ ] Presionar Tab hasta llegar al primer encabezado de documento — debe verse el ring de `--accent`.
- [ ] Presionar ↓ — el foco debe moverse al siguiente encabezado de documento.
- [ ] Presionar ↑ — vuelve al encabezado anterior.
- [ ] Presionar Enter — las líneas del documento se deben expandir/colapsar.
- [ ] Con las líneas abiertas, presionar Tab — el foco debe ir al select EMB, luego PRIO, luego checkboxes, luego botones.
- [ ] Con el foco en un select o checkbox, presionar Escape — el foco debe volver al encabezado del documento.
- [ ] Verificar que los selects EMB/PRIO siguen guardando con `onchange`.
- [ ] Verificar que los checkboxes para split siguen funcionando.

### Paso 3.5 — Commit

```bash
git add cortes/templates/cortes/detalle.html
git commit -m "feat: keyboard navigation on corte detail with roving tabindex and Escape guard"
```

- [ ] Hacer commit.

---

## Verificación final end-to-end

- [ ] Flujo completo sin mouse: Tab → tabla lista → ↓↓ seleccionar corte → Enter → detalle → Tab → primer doc → Enter (expandir) → Tab → select EMB → cambiar valor → Escape → encabezado → ↓ siguiente doc.
- [ ] Verificar en modo oscuro que el ring de foco es visible (usa `--accent` que en dark es cyan).
- [ ] Verificar que Alt+L, Alt+N y demás atajos existentes siguen funcionando.
