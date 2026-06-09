# Keyboard Navigation — Diseño

**Fecha:** 2026-06-09  
**Alcance:** `lista.html` y `detalle.html`  
**Enfoque elegido:** Roving tabindex (patrón ARIA grid simplificado)

---

## Problema

Las filas de la tabla de cortes y los bloques de documento en el detalle solo son alcanzables con mouse. El usuario debe hacer click antes de poder usar cualquier tecla. Los atajos Alt+key del `base.html` ya funcionan bien; el problema es la navegación dentro de las vistas de lista y detalle.

---

## Comportamiento esperado

### Lista de cortes (`lista.html`)

| Tecla | Acción |
|-------|--------|
| Tab | Entra a la tabla, enfoca la primera fila |
| ↑ / ↓ | Mueve el foco entre filas |
| Enter | Abre el corte (`location.href`) |
| Escape / Tab fuera | Sale de la tabla, regresa al flujo normal de Tab |

### Detalle de corte (`detalle.html`)

| Tecla | Acción |
|-------|--------|
| Tab | Entra al primer documento, enfoca su encabezado |
| ↑ / ↓ | Mueve el foco entre encabezados de documento |
| Enter | Toggle de líneas (abre/cierra el documento) |
| Tab (dentro de doc abierto) | Navega: select EMB → select PRIO → checkboxes → botón Partir/Deshacer |
| Escape | Desde dentro de un documento, regresa el foco al encabezado |

---

## Arquitectura

### Helper reutilizable en `base.html`

```js
function initKeyNav(items, { onActivate, onExit }) { ... }
```

- `items`: NodeList o Array de elementos navegables
- `onActivate(item)`: callback al presionar Enter en el ítem activo
- `onExit()`: callback opcional al presionar Escape

**Mecanismo roving tabindex:**
- Al inicializar: todos los ítems reciben `tabindex="-1"` y `data-nav-item`; el primero recibe `tabindex="0"`
- Al mover foco: el ítem anterior pasa a `tabindex="-1"`, el nuevo a `tabindex="0"` y recibe `.focus()`
- Al hacer Tab fuera: el foco vuelve a `tabindex="0"` en el primer ítem (listo para la próxima vez que Tab llegue)

### Uso en `lista.html`

```js
// Después del DOM ready
var rows = document.querySelectorAll('tbody tr[data-corte-url]');
initKeyNav(rows, {
  onActivate: function(row) { location.href = row.dataset.corteUrl; }
});
```

Las `<tr>` reciben el atributo `data-corte-url` en el template (reemplaza el `onclick` inline).

### Uso en `detalle.html`

```js
var headers = document.querySelectorAll('[data-doc-header]');
initKeyNav(headers, {
  onActivate: function(header) { toggleLineas(parseInt(header.dataset.docId)); }
});
```

Los divs de encabezado de documento reciben `data-doc-header` y `data-doc-id` en el template.  
Cuando un documento está abierto (líneas visibles), Tab desde el encabezado fluye naturalmente a los controles internos (selects, checkboxes, botones) porque ya tienen `tabindex` nativo. Los controles internos del documento (selects, checkboxes, botones dentro de cada card) reciben `data-parent-doc-id="{{ doc.id }}"` en el template. Un listener de `keydown` en el documento escucha Escape: si el foco está en un control con `data-parent-doc-id`, mueve el foco de vuelta al encabezado correspondiente (`[data-doc-id="X"]`).

---

## Estilos CSS (en `base.html`)

```css
[data-nav-item]:focus {
    outline: none;
    box-shadow: inset 0 0 0 2px var(--accent);
}

tbody tr[data-nav-item]:focus td {
    background: var(--surface-raised);
}
```

El atributo `data-nav-item` es agregado por JS al inicializar — no está en el HTML del template, así el markup queda limpio si el script no corre.

---

## Cambios por archivo

| Archivo | Cambio |
|---------|--------|
| `cortes/templates/cortes/base.html` | +función `initKeyNav()` + 2 reglas CSS |
| `cortes/templates/cortes/lista.html` | `<tr>` recibe `data-corte-url`; se llama `initKeyNav` |
| `cortes/templates/cortes/detalle.html` | encabezados de doc reciben `data-doc-header`/`data-doc-id`; se llama `initKeyNav`; controles internos reciben guard de Escape |

Sin cambios en Python, modelos, URLs ni tests de backend.

---

## Fuera de alcance

- Paginación con teclado (flechas no cruzan páginas)
- Vista `cargar.html` (un solo formulario, Tab nativo es suficiente)
- Soporte para lectores de pantalla (ARIA roles completos) — posible mejora futura
