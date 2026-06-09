# Roles, Presencia y Animación de Carga — Diseño

**Fecha:** 2026-06-09
**Alcance:** Roles nuevos (`facturacion`, `almacenamiento`), eliminación del bloqueo del flujo de edición, presencia en tiempo real (polling), animación de carga al subir archivo.

---

## Parte 1: Roles nuevos

### Grupos

| Grupo | Antes | Ahora |
|-------|-------|-------|
| `facturacion` | — | Nuevo: solo subir archivos |
| `almacenamiento` | — | Nuevo: editar, generar y descargar |
| `admin` | existe | Sin cambios: todo |
| `consulta` | existe | Sin cambios: solo lectura |
| `operario` | existe | Queda en DB pero deja de usarse en la lógica |

### Permisos por grupo

**`facturacion`:**
- `add_corte`, `change_corte` (para crear el Corte al subir)
- `view_*` en cortes, productos, core

**`almacenamiento`:**
- `view_*`, `change_documento`, `change_linea`, `add_corteversion` en cortes, productos, core

**`admin`:**
- Todos los permisos (sin cambios)

### Cambios en `cortes/views.py`

**`EsOperarioOAdminMixin`** → reemplazar por `EsFacturacionOAdminMixin`:
```python
class EsFacturacionOAdminMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.groups.filter(name__in=["facturacion", "admin"]).exists()
```

**`CargarCorteView`**: usar `EsFacturacionOAdminMixin`. Después de cargar, redirigir a `lista_cortes`:
```python
return redirect("lista_cortes")
```

**`DetalleCorteView.get_context_data()`**: `es_editor` se determina por grupo, no por bloqueo:
```python
puede_editar = bool(grupos & {"almacenamiento", "admin"})
es_editor = puede_editar
```
Eliminar toda la lógica de `intentar_tomar_bloqueo`, `bloqueo_info`, `es_admin` del contexto de edición.

**`EditarCorteView.post()`**: eliminar el guard de `refrescar_bloqueo`. Cualquier `almacenamiento` o `admin` puede editar:
```python
puede_editar = request.user.groups.filter(name__in=["almacenamiento", "admin"]).exists()
if not puede_editar:
    return HttpResponseForbidden("Sin permisos para editar")
```

**`GenerarCorteView.post()`**: mismo patrón, eliminar `refrescar_bloqueo`.

**`ForzarLiberacionView`**: dejar intacta (admin puede liberar bloqueos legacy si los hubiera), pero ocultar el botón del template.

### Cambios en `detalle.html`

- Eliminar el bloque `{% if bloqueo_info %}` con el indicador "● Editando: usuario" y el botón "Liberar bloqueo".
- `es_editor` ahora viene solo del grupo del usuario.

### Migración

Nueva migración en `core/migrations/` que:
1. Crea el grupo `facturacion` con sus permisos.
2. Crea el grupo `almacenamiento` con sus permisos.

---

## Parte 2: Presencia en tiempo real

### Modelo `PresenciaCorte` en `cortes/models.py`

```python
class PresenciaCorte(models.Model):
    user  = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    corte = models.ForeignKey(Corte, on_delete=models.CASCADE, related_name="presencias")
    visto_en = models.DateTimeField()

    class Meta:
        unique_together = [("user", "corte")]
```

### Endpoints nuevos en `cortes/urls.py`

```
POST /cortes/<pk>/presencia/   → PresenciaPingView
GET  /cortes/<pk>/presencia/   → PresenciaPingView (mismo view, método diferente)
```

### `PresenciaPingView` en `cortes/views.py`

**POST** — upsert de la fila:
```python
PresenciaCorte.objects.update_or_create(
    user=request.user, corte=corte,
    defaults={"visto_en": timezone.now()}
)
return JsonResponse({"ok": True})
```

**GET** — devuelve lista de activos (últimos 25s) y limpia stale:
```python
limite = timezone.now() - timedelta(seconds=25)
PresenciaCorte.objects.filter(corte=corte, visto_en__lt=limite).delete()
activos = PresenciaCorte.objects.filter(corte=corte).select_related("user")
usuarios = [
    {
        "username": p.user.username,
        "iniciales": (p.user.first_name[:1] + p.user.last_name[:1]).upper()
                     or p.user.username[:2].upper(),
        "soy_yo": p.user_id == request.user.pk,
    }
    for p in activos
]
return JsonResponse({"usuarios": usuarios})
```

Requiere `LoginRequiredMixin`.

### Frontend en `detalle.html`

**Colores deterministas** (en el script no-verbatim):
```js
var PRESENCE_COLORS = [
    '#0284c7','#059669','#b45309','#7c3aed','#db2777','#0891b2'
];
function presenceColor(username) {
    var h = 0;
    for (var i = 0; i < username.length; i++) h = (h * 31 + username.charCodeAt(i)) & 0xffff;
    return PRESENCE_COLORS[h % PRESENCE_COLORS.length];
}
```

**Polling** — dentro de `DOMContentLoaded`:
```js
function pingPresencia() {
    var base = '/cortes/' + CORTE_ID + '/presencia/';
    fetch(base, { method: 'POST', headers: { 'X-CSRFToken': getCSRF() } });
    fetch(base).then(r => r.json()).then(function(data) {
        var wrap = document.getElementById('presencia-chips');
        if (!wrap) return;
        wrap.innerHTML = '';
        data.usuarios.forEach(function(u) {
            var chip = document.createElement('span');
            chip.title = u.username;
            chip.textContent = u.iniciales;
            chip.style.cssText =
                'display:inline-flex;align-items:center;justify-content:center;' +
                'width:26px;height:26px;border-radius:50%;font-size:10px;font-weight:600;' +
                'font-family:var(--font-mono);color:#fff;cursor:default;' +
                'background:' + presenceColor(u.username) + ';' +
                (u.soy_yo ? 'outline:2px solid var(--accent);outline-offset:1px;' : '');
            wrap.appendChild(chip);
        });
    });
}
pingPresencia();
var presenciaInterval = setInterval(pingPresencia, 10000);
document.addEventListener('visibilitychange', function() {
    if (document.hidden) clearInterval(presenciaInterval);
    else { presenciaInterval = setInterval(pingPresencia, 10000); pingPresencia(); }
});
```

**HTML** — en el toolbar del detalle, junto al botón "← Volver":
```html
<div id="presencia-chips" style="display:flex;align-items:center;gap:.3rem;"></div>
```

---

## Parte 3: Animación de carga al subir archivo

### Cambios en `cortes/templates/cortes/cargar.html`

Al hacer submit del formulario, JS:
1. Deshabilita el botón de envío.
2. Muestra un overlay con barra de progreso animada y texto "Procesando archivo…".

**HTML del overlay** (añadir antes de `{% endblock %}`):
```html
<div id="upload-overlay" style="display:none;position:fixed;inset:0;
     background:rgba(8,11,18,.7);z-index:9999;
     display:none;align-items:center;justify-content:center;flex-direction:column;gap:1rem;">
    <div style="font-family:var(--font-mono);font-size:12px;color:var(--text-muted);
                letter-spacing:1px;">Procesando archivo…</div>
    <div style="width:280px;height:3px;background:var(--surface-raised);border-radius:2px;overflow:hidden;">
        <div id="upload-bar" style="height:100%;width:30%;background:var(--accent);
             border-radius:2px;animation:upload-slide 1.4s ease-in-out infinite;"></div>
    </div>
</div>
<style>
@keyframes upload-slide {
    0%   { margin-left:-30%; width:30%; }
    50%  { margin-left:40%; width:40%; }
    100% { margin-left:110%; width:30%; }
}
</style>
```

**JS** (en el script del form):
```js
document.querySelector('form').addEventListener('submit', function() {
    document.querySelector('[type=submit]').disabled = true;
    var overlay = document.getElementById('upload-overlay');
    overlay.style.display = 'flex';
});
```

---

## Archivos modificados

| Archivo | Cambio |
|---------|--------|
| `core/migrations/000X_grupos_facturacion_almacenamiento.py` | Crea grupos nuevos con permisos |
| `cortes/models.py` | +`PresenciaCorte` |
| `cortes/migrations/000X_presenciacorte.py` | Migración auto-generada |
| `cortes/views.py` | Nuevos mixins, eliminar lock de flujo edición/generación, +`PresenciaPingView` |
| `cortes/urls.py` | +`presencia/` endpoint |
| `cortes/templates/cortes/detalle.html` | -bloqueo UI, +chips presencia, +polling JS |
| `cortes/templates/cortes/cargar.html` | +overlay de carga |

---

## Fuera de alcance

- Migrar usuarios existentes de `operario` a los nuevos grupos: se hace manualmente en el admin.
- Presencia a nivel de documento específico (qué tarjeta está viendo cada usuario).
- Bloqueo de edición simultánea (se acepta que dos usuarios puedan editar a la vez).
- Eliminar los campos `bloqueado_por` / `bloqueado_hasta` del modelo `Corte` (se dejan, dejan de usarse en el flujo principal).
