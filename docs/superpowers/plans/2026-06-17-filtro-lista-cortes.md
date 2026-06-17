# Filtro de lista de cortes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar barra de filtros (texto, estado, usuario, fechas) encima de la lista de cortes con búsqueda en toda la historia cuando hay filtros activos.

**Architecture:** Form GET en la misma URL; `ListaCortesView.get_queryset()` lee los params y aplica filtros ORM. Sin nuevo endpoint ni dependencias. JS de ~20 líneas para debounce y submit automático.

**Tech Stack:** Django 5.2, Python 3.13, SQLite (tests), PostgreSQL (prod). Sin librerías adicionales.

## Global Constraints

- Sin nuevas dependencias pip.
- Tests con `DJANGO_SETTINGS_MODULE=despacha.settings_test` (SQLite in-memory).
- Comando de tests: `.venv/bin/python manage.py test --settings despacha.settings_test`
- No tocar la vista de detalle ni el modelo.
- Búsqueda `icontains` (SQL LIKE) sobre `Documento.factura` y `Documento.nit`, con `.distinct()`.
- Sin filtros activos → últimos 30 días. Con cualquier filtro activo → toda la historia.
- Paginación existente `paginate_by = 20` se mantiene intacta.

---

### Task 1: Backend — filtros en `ListaCortesView`

**Files:**
- Modify: `cortes/views.py:49-76`
- Test: `cortes/tests/test_lista_filtros.py` (nuevo)

**Interfaces:**
- Produces: `ListaCortesView` acepta GET params `q`, `estado`, `usuario`, `desde`, `hasta`. Agrega `filtros_activos` (bool) y `total_filtrado` (int, solo si hay filtros) al contexto.

- [ ] **Step 1: Crear archivo de tests**

```python
# cortes/tests/test_lista_filtros.py
from datetime import date, timedelta
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone

from cortes.models import Corte, Documento


def _corte(usuario, fecha, numero=1, estado="en_revision", hash_extra=""):
    return Corte.objects.create(
        archivo="test.xlsx",
        hash_sha256=f"hash{fecha}{numero}{hash_extra}",
        usuario_carga=usuario,
        fecha=fecha,
        numero_corte=numero,
        estado=estado,
    )


def _doc(corte, factura, nit="800000"):
    return Documento.objects.create(corte=corte, factura=factura, nit=nit)


class FiltroListaTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u1", password="pw")
        self.user2 = User.objects.create_user(username="u2", password="pw")
        self.client.force_login(self.user)

        hoy = timezone.localdate()
        hace_60 = hoy - timedelta(days=60)

        # corte reciente (dentro de 30 días)
        self.corte_reciente = _corte(self.user, hoy, numero=1, estado="generado", hash_extra="r")
        _doc(self.corte_reciente, "FAC001", nit="900111")

        # corte antiguo (fuera de 30 días)
        self.corte_antiguo = _corte(self.user2, hace_60, numero=2, estado="en_revision", hash_extra="a")
        _doc(self.corte_antiguo, "FAC999", nit="800555")

    def _get(self, params=""):
        return self.client.get(reverse("lista_cortes") + params)

    def test_sin_filtros_solo_30_dias(self):
        r = self._get()
        self.assertEqual(r.status_code, 200)
        ids = [c.pk for c in r.context["cortes"]]
        self.assertIn(self.corte_reciente.pk, ids)
        self.assertNotIn(self.corte_antiguo.pk, ids)

    def test_busqueda_q_trae_corte_antiguo(self):
        r = self._get("?q=FAC999")
        self.assertEqual(r.status_code, 200)
        ids = [c.pk for c in r.context["cortes"]]
        self.assertIn(self.corte_antiguo.pk, ids)
        self.assertNotIn(self.corte_reciente.pk, ids)

    def test_busqueda_q_por_nit(self):
        r = self._get("?q=900111")
        ids = [c.pk for c in r.context["cortes"]]
        self.assertIn(self.corte_reciente.pk, ids)

    def test_filtro_estado(self):
        r = self._get("?estado=generado")
        ids = [c.pk for c in r.context["cortes"]]
        self.assertIn(self.corte_reciente.pk, ids)
        self.assertNotIn(self.corte_antiguo.pk, ids)

    def test_filtro_usuario(self):
        r = self._get(f"?usuario={self.user2.pk}")
        ids = [c.pk for c in r.context["cortes"]]
        self.assertIn(self.corte_antiguo.pk, ids)
        self.assertNotIn(self.corte_reciente.pk, ids)

    def test_filtro_desde(self):
        hace_70 = (timezone.localdate() - timedelta(days=70)).isoformat()
        r = self._get(f"?desde={hace_70}")
        ids = [c.pk for c in r.context["cortes"]]
        self.assertIn(self.corte_antiguo.pk, ids)
        self.assertIn(self.corte_reciente.pk, ids)

    def test_filtros_activos_en_contexto(self):
        r = self._get("?q=FAC999")
        self.assertTrue(r.context["filtros_activos"])
        self.assertIn("total_filtrado", r.context)

    def test_sin_filtros_no_hay_total(self):
        r = self._get()
        self.assertFalse(r.context["filtros_activos"])
        self.assertNotIn("total_filtrado", r.context)
```

- [ ] **Step 2: Ejecutar tests — deben fallar**

```bash
.venv/bin/python manage.py test cortes.tests.test_lista_filtros --settings despacha.settings_test
```

Esperado: `FAIL` — `lista_cortes` no existe aún como nombre de URL o los filtros no funcionan. (Si la URL existe pero los filtros no, los tests de filtros fallan; los de 200 pasan.)

- [ ] **Step 3: Implementar filtros en la vista**

Reemplazar el método `get_queryset` y `get_context_data` en `cortes/views.py`:

```python
class ListaCortesView(LoginRequiredMixin, ListView):
    model = Corte
    template_name = "cortes/lista.html"
    context_object_name = "cortes"
    paginate_by = 20

    def _params(self):
        g = self.request.GET
        return {
            "q":       g.get("q", "").strip(),
            "estado":  g.get("estado", "").strip(),
            "usuario": g.get("usuario", "").strip(),
            "desde":   g.get("desde", "").strip(),
            "hasta":   g.get("hasta", "").strip(),
        }

    def get_queryset(self):
        from django.db.models import Q
        p = self._params()
        hay_filtro = any(p.values())

        qs = super().get_queryset().annotate(
            documentos_count=Count("documentos"),
        ).prefetch_related("documentos").order_by("-fecha", "numero_corte", "adicional_letra")

        if not hay_filtro:
            hace_30 = timezone.localdate() - timedelta(days=30)
            return qs.filter(fecha__gte=hace_30)

        if p["q"]:
            qs = qs.filter(
                Q(documentos__factura__icontains=p["q"]) |
                Q(documentos__nit__icontains=p["q"])
            ).distinct()
        if p["estado"] and p["estado"] in dict(Corte.ESTADO_CHOICES):
            qs = qs.filter(estado=p["estado"])
        if p["usuario"] and p["usuario"].isdigit():
            qs = qs.filter(usuario_carga_id=int(p["usuario"]))
        if p["desde"]:
            qs = qs.filter(fecha__gte=p["desde"])
        if p["hasta"]:
            qs = qs.filter(fecha__lte=p["hasta"])

        return qs

    def get_context_data(self, **kwargs):
        from itertools import groupby
        ctx = super().get_context_data(**kwargs)
        p = self._params()
        hay_filtro = any(p.values())

        for corte in ctx["cortes"]:
            tipos = sorted({d.tipo_comprobante for d in corte.documentos.all() if d.tipo_comprobante})
            corte.tipos = "·".join(tipos) if tipos else "—"

        dias = []
        for fecha, fecha_iter in groupby(ctx["cortes"], key=lambda c: c.fecha):
            grupos = []
            for numero, corte_iter in groupby(list(fecha_iter), key=lambda c: c.numero_corte):
                grupos.append(list(corte_iter))
            dias.append({"fecha": fecha, "grupos": grupos})
        ctx["dias"] = dias
        ctx["filtros_activos"] = hay_filtro
        ctx["params"] = p

        if hay_filtro:
            ctx["total_filtrado"] = self.get_queryset().count()

        # para el select de usuarios en el filtro
        from django.contrib.auth.models import User as AuthUser
        ctx["usuarios_carga"] = AuthUser.objects.filter(
            cortes__isnull=False
        ).distinct().order_by("username")

        return ctx
```

- [ ] **Step 4: Verificar URL name**

```bash
grep -n "lista_cortes\|ListaCortesView" /opt/despacha/cortes/urls.py
```

El name debe ser `lista_cortes`. Si es diferente, ajusta el test de Step 1 para que use el name correcto.

- [ ] **Step 5: Ejecutar tests — deben pasar**

```bash
.venv/bin/python manage.py test cortes.tests.test_lista_filtros --settings despacha.settings_test
```

Esperado: `OK` — 8 tests pasando.

- [ ] **Step 6: Suite completa**

```bash
.venv/bin/python manage.py test --settings despacha.settings_test
```

Esperado: todos los tests existentes siguen pasando.

- [ ] **Step 7: Commit**

```bash
git add cortes/views.py cortes/tests/test_lista_filtros.py
git commit -m "feat: filtros GET en ListaCortesView (q, estado, usuario, fechas)"
```

---

### Task 2: Template — barra de filtros, aviso y JS

**Files:**
- Modify: `cortes/templates/cortes/lista.html`

**Interfaces:**
- Consumes del contexto: `filtros_activos` (bool), `total_filtrado` (int, opcional), `params` (dict con q/estado/usuario/desde/hasta), `usuarios_carga` (queryset de User).

- [ ] **Step 1: Agregar form de filtros y aviso en `lista.html`**

Insertar justo **antes** de `{% if dias %}` (línea 13 actual), reemplazando el bloque `{% if dias %}...{% endif %}` completo con lo siguiente:

```html
<form method="get" id="filtros-form" style="margin-bottom:1rem;">
  <div class="filtros-bar">
    <input type="search" name="q" value="{{ params.q }}"
           placeholder="Factura o NIT…"
           class="filtro-input filtro-q"
           autocomplete="off">
    <select name="estado" class="filtro-select">
      <option value="">Todos los estados</option>
      <option value="cargado"     {% if params.estado == "cargado" %}selected{% endif %}>Cargado</option>
      <option value="en_revision" {% if params.estado == "en_revision" %}selected{% endif %}>En revisión</option>
      <option value="generado"    {% if params.estado == "generado" %}selected{% endif %}>Generado</option>
      <option value="con_error"   {% if params.estado == "con_error" %}selected{% endif %}>Con error</option>
    </select>
    <select name="usuario" class="filtro-select">
      <option value="">Todos los usuarios</option>
      {% for u in usuarios_carga %}
      <option value="{{ u.pk }}" {% if params.usuario == u.pk|stringformat:"s" %}selected{% endif %}>{{ u.username }}</option>
      {% endfor %}
    </select>
    <input type="date" name="desde" value="{{ params.desde }}" class="filtro-date" title="Desde">
    <input type="date" name="hasta" value="{{ params.hasta }}" class="filtro-date" title="Hasta">
    {% if filtros_activos %}
    <a href="{% url 'lista_cortes' %}" class="filtro-clear" title="Limpiar filtros">✕</a>
    {% endif %}
  </div>
</form>

{% if filtros_activos %}
<p class="filtro-aviso">
  Se encontr{% if total_filtrado == 1 %}ó 1 corte{% else %}aron {{ total_filtrado }} cortes{% endif %}
</p>
{% endif %}

{% if dias %}
<div class="cortes-header">
    <span>Corte</span>
    <span>Tipo comprobante</span>
    <span>Estado</span>
    <span class="ch-meta">
        <span>Facturas</span>
        <span class="meta-dot">·</span>
        <span>Versión</span>
        <span class="meta-dot">·</span>
        <span>Usuario</span>
    </span>
</div>

<div class="cortes-feed">
{% for dia in dias %}
    <div class="day-section">
        <div class="day-divider">
            <span class="day-label">{{ dia.fecha|date:"d/m/Y" }}</span>
        </div>
        <div class="day-table">
            {% for grupo in dia.grupos %}
            {% for corte in grupo %}
            <a href="{% url 'detalle_corte' corte.pk %}"
               class="corte-row{% if corte.adicional_letra %} row-adicional{% else %} row-base{% endif %}">
                <span class="row-name">{{ corte.display_corte }}</span>
                <span class="row-tipo">{{ corte.tipos }}</span>
                <span class="badge badge-{{ corte.estado }}">{{ corte.get_estado_display }}</span>
                <div class="row-meta">
                    <span>{{ corte.documentos_count }}</span>
                    <span class="meta-dot">·</span>
                    <span>v{{ corte.version_actual }}</span>
                    <span class="meta-dot">·</span>
                    <span>{{ corte.usuario_carga.username }}</span>
                </div>
            </a>
            {% endfor %}
            {% if not forloop.last %}
            <div class="grupo-sep"></div>
            {% endif %}
            {% endfor %}
        </div>
    </div>
{% endfor %}
</div>
{% elif filtros_activos %}
<p style="text-align:center;color:var(--text-muted);padding:3rem;font-size:13px;">
    No se encontraron cortes con esos filtros.
</p>
{% else %}
<p style="text-align:center;color:var(--text-muted);padding:3rem;font-size:13px;">
    No hay cortes en los últimos 30 días.
</p>
{% endif %}
```

- [ ] **Step 2: Agregar estilos para la barra de filtros**

Dentro del bloque `<style>` existente, agregar al final (antes del cierre `</style>`):

```css
/* ── barra de filtros ── */
.filtros-bar {
    display: flex;
    flex-wrap: wrap;
    gap: .5rem;
    align-items: center;
}
.filtro-input,
.filtro-select,
.filtro-date {
    font-family: var(--font-mono);
    font-size: 12px;
    background: var(--surface);
    border: 1px solid var(--border-mid);
    border-radius: 6px;
    padding: .35rem .6rem;
    color: var(--text);
    outline: none;
}
.filtro-input:focus,
.filtro-select:focus,
.filtro-date:focus {
    border-color: var(--accent);
}
.filtro-q { flex: 1; min-width: 160px; }
.filtro-select { min-width: 140px; }
.filtro-date { width: 130px; }
.filtro-clear {
    font-size: 11px;
    color: var(--text-muted);
    text-decoration: none;
    padding: .35rem .5rem;
    border: 1px solid var(--border);
    border-radius: 6px;
    line-height: 1;
}
.filtro-clear:hover { color: var(--text); border-color: var(--border-mid); }
.filtro-aviso {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--text-muted);
    margin: 0 0 .5rem 0;
    padding: 0 .25rem;
}
@media (max-width: 600px) {
    .filtro-q { width: 100%; }
    .filtro-select,
    .filtro-date { flex: 1; min-width: 0; }
}
```

- [ ] **Step 3: Agregar JS de debounce y auto-submit**

Reemplazar el bloque `<script>` existente con:

```html
<script>
document.addEventListener('DOMContentLoaded', function() {
    // ── navegación teclado en filas ──
    var rows = Array.from(document.querySelectorAll('.corte-row'));
    if (rows.length) {
        rows.forEach(function(r, i) {
            r.setAttribute('tabindex', i === 0 ? '0' : '-1');
            r.setAttribute('data-nav-item', '');
        });
        function moveTo(r) {
            rows.forEach(function(x) { x.setAttribute('tabindex', '-1'); });
            r.setAttribute('tabindex', '0');
            r.focus();
        }
        rows.forEach(function(r, i) {
            r.addEventListener('keydown', function(e) {
                if (e.key === 'ArrowDown' && i < rows.length - 1) { e.preventDefault(); moveTo(rows[i + 1]); }
                if (e.key === 'ArrowUp'   && i > 0)               { e.preventDefault(); moveTo(rows[i - 1]); }
            });
        });
    }

    // ── filtros: submit automático ──
    var form = document.getElementById('filtros-form');
    if (!form) return;

    // selectores y fechas → submit inmediato
    form.querySelectorAll('select, input[type="date"]').forEach(function(el) {
        el.addEventListener('change', function() { form.submit(); });
    });

    // texto → debounce 400ms
    var timer;
    var qInput = form.querySelector('input[type="search"]');
    if (qInput) {
        qInput.addEventListener('input', function() {
            clearTimeout(timer);
            timer = setTimeout(function() { form.submit(); }, 400);
        });
    }
});
</script>
```

- [ ] **Step 4: Verificar el nombre de URL en el template**

```bash
grep -n "url 'lista_cortes'\|url \"lista_cortes\"" /opt/despacha/cortes/templates/cortes/lista.html
grep -n "lista_cortes" /opt/despacha/cortes/urls.py
```

Ambos deben coincidir. Si el name es diferente, actualizar `{% url 'lista_cortes' %}` en el template.

- [ ] **Step 5: Suite completa**

```bash
.venv/bin/python manage.py test --settings despacha.settings_test
```

Esperado: todos los tests pasan (el template no tiene tests propios; los de Task 1 siguen verdes).

- [ ] **Step 6: Commit**

```bash
git add cortes/templates/cortes/lista.html
git commit -m "feat: barra de filtros en lista de cortes con aviso de resultados"
```
