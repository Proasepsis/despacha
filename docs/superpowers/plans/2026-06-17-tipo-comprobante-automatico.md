# tipo_comprobante Automático Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detectar `tipo_comprobante` automáticamente del archivo Excel por cada `Documento`, eliminarlo del formulario de carga y mostrarlo en vistas de lista y detalle.

**Architecture:** El tipo viaja por el pipeline: adaptador → `DocumentoInterno.tipo_comprobante` → `procesar.py` → `Documento.tipo_comprobante`. Se elimina del modelo `Corte` y del formulario. La lista muestra un resumen de tipos únicos por corte; el detalle lo muestra por fila de documento.

**Tech Stack:** Django 5.2, Python 3.13, SQLite (tests), PostgreSQL (prod), openpyxl.

## Global Constraints

- Comandos de test: `.venv/bin/python manage.py test <módulo> --settings despacha.settings_test`
- Suite completa: `.venv/bin/python manage.py test --settings despacha.settings_test`
- Makemigrations: `.venv/bin/python manage.py makemigrations --settings despacha.settings_test`
- No usar `StringAgg` (PostgreSQL-only) — los tests usan SQLite; usar `prefetch_related` + Python
- Idioma del código: español en variables de dominio, inglés en infraestructura Django

---

### Task 1: Pipeline — DocumentoInterno y adaptador

**Files:**
- Modify: `core/adaptadores/modelo_interno.py`
- Modify: `core/adaptadores/plantilla/adaptador.py` (líneas ~233-239)
- Modify: `core/tests/test_adaptador_plantilla_filtro.py`

**Interfaces:**
- Produce: `DocumentoInterno.tipo_comprobante: str` — disponible para Task 3

- [ ] **Step 1: Escribir test que falla**

En `core/tests/test_adaptador_plantilla_filtro.py`, agregar al final de la clase `AdaptadorPlantillaFiltroTest`:

```python
def test_tipo_comprobante_se_propaga_al_documento(self):
    filas = [
        ["DOC001", "F", "1", "143505", "C", "150", "0005", "000005", "10", "L1", "800000", "11001", "Desc"],
    ]
    ruta = Path("/tmp/test_tipo_doc.xlsx")
    _crear_excel_plantilla(ruta, filas)

    documentos = self.adaptador.parse(ruta)
    ruta.unlink(missing_ok=True)

    self.assertEqual(documentos[0].tipo_comprobante, "F")

def test_tipo_comprobante_archivo_mixto(self):
    """Dos documentos distintos con tipos distintos."""
    filas = [
        ["DOC001", "F", "1", "143505", "C", "150", "0005", "000005", "10", "L1", "800000", "11001", "Desc F"],
        ["DOC002", "H", "5", "143505", "C", "150", "0005", "000005", "10", "L2", "900000", "11001", "Desc H"],
    ]
    ruta = Path("/tmp/test_tipo_mixto.xlsx")
    _crear_excel_plantilla(ruta, filas)

    documentos = self.adaptador.parse(ruta)
    ruta.unlink(missing_ok=True)

    tipos = {d.factura: d.tipo_comprobante for d in documentos}
    self.assertEqual(tipos["DOC001"], "F")
    self.assertEqual(tipos["DOC002"], "H")
```

- [ ] **Step 2: Correr test para verificar que falla**

```bash
.venv/bin/python manage.py test core.tests.test_adaptador_plantilla_filtro.AdaptadorPlantillaFiltroTest.test_tipo_comprobante_se_propaga_al_documento --settings despacha.settings_test
```

Esperado: `AttributeError: 'DocumentoInterno' object has no attribute 'tipo_comprobante'`

- [ ] **Step 3: Agregar campo a DocumentoInterno**

En `core/adaptadores/modelo_interno.py`, agregar `tipo_comprobante` a `DocumentoInterno`:

```python
@dataclass
class DocumentoInterno:
    factura: str
    nit: str = ""
    codigo_ciudad: str = ""
    tipo_comprobante: str = ""
    lineas: list[LineaInterna] = field(default_factory=list)
```

- [ ] **Step 4: Propagar tipo en el adaptador**

En `core/adaptadores/plantilla/adaptador.py`, el bloque que crea `DocumentoInterno` está alrededor de la línea 233:

```python
if num_doc not in documentos:
    documentos[num_doc] = DocumentoInterno(
        factura=num_doc,
        nit=nit,
        codigo_ciudad=codigo_ciudad,
    )
documentos[num_doc].lineas.append(linea)
```

Reemplazar por:

```python
if num_doc not in documentos:
    documentos[num_doc] = DocumentoInterno(
        factura=num_doc,
        nit=nit,
        codigo_ciudad=codigo_ciudad,
        tipo_comprobante=tipo_comprobante,
    )
documentos[num_doc].lineas.append(linea)
```

La variable `tipo_comprobante` ya existe en el loop (leída de la columna `TIPO DE COMPROBANTE` y ya pasó los filtros de validación).

- [ ] **Step 5: Correr tests del adaptador**

```bash
.venv/bin/python manage.py test core.tests.test_adaptador_plantilla_filtro --settings despacha.settings_test
```

Esperado: todos pasan.

- [ ] **Step 6: Commit**

```bash
git add core/adaptadores/modelo_interno.py core/adaptadores/plantilla/adaptador.py core/tests/test_adaptador_plantilla_filtro.py
git commit -m "feat: propagar tipo_comprobante desde Excel a DocumentoInterno"
```

---

### Task 2: Modelo y migración

**Files:**
- Modify: `cortes/models.py`
- Create: `cortes/migrations/0008_documento_tipo_comprobante.py` (generado)

**Interfaces:**
- Produce: `Documento.tipo_comprobante: CharField(max_length=1, blank=True, default="")`
- `Corte.tipo_comprobante` eliminado

- [ ] **Step 1: Actualizar modelos**

En `cortes/models.py`:

1. Eliminar de `Corte` la línea:
```python
tipo_comprobante = models.CharField(max_length=80, blank=True, default="")
```

2. Agregar a `Documento` (después del campo `nit`, antes de `ciudad`):
```python
tipo_comprobante = models.CharField(max_length=1, blank=True, default="")
```

El modelo `Documento` resultante en esa zona queda:
```python
class Documento(models.Model):
    corte = models.ForeignKey(Corte, on_delete=models.CASCADE, related_name="documentos")
    factura = models.CharField(max_length=50)
    nit = models.CharField(max_length=20, blank=True, default="")
    tipo_comprobante = models.CharField(max_length=1, blank=True, default="")
    ciudad = models.ForeignKey(...)
    ...
```

- [ ] **Step 2: Generar migración**

```bash
.venv/bin/python manage.py makemigrations cortes --name documento_tipo_comprobante --settings despacha.settings_test
```

Esperado: crea `cortes/migrations/0008_documento_tipo_comprobante.py`

- [ ] **Step 3: Verificar migración generada**

Abrir `cortes/migrations/0008_documento_tipo_comprobante.py` y confirmar que contiene:
- `migrations.AddField` en `documento` con `tipo_comprobante`
- `migrations.RemoveField` en `corte` con `tipo_comprobante`

- [ ] **Step 4: Aplicar migración en tests**

```bash
.venv/bin/python manage.py test --settings despacha.settings_test -v 0 2>&1 | head -5
```

Esperado: `OK` o solo fallos relacionados con `tipo_comprobante` en cargar (los fixearemos en Task 4).

- [ ] **Step 5: Commit**

```bash
git add cortes/models.py cortes/migrations/0008_documento_tipo_comprobante.py
git commit -m "feat: mover tipo_comprobante de Corte a Documento"
```

---

### Task 3: procesar.py — guardar tipo en Documento

**Files:**
- Modify: `cortes/servicios/procesar.py` (línea ~58-63)
- Modify: `cortes/tests/test_procesar.py`

**Interfaces:**
- Consume: `DocumentoInterno.tipo_comprobante: str` (de Task 1)
- Consume: `Documento.tipo_comprobante` (de Task 2)

- [ ] **Step 1: Escribir test que falla**

En `cortes/tests/test_procesar.py`, agregar un test a la clase existente `ProcesarDocumentosTest`:

```python
def test_tipo_comprobante_se_guarda_en_documento(self):
    from core.adaptadores.modelo_interno import DocumentoInterno, LineaInterna
    from decimal import Decimal

    docs = [
        DocumentoInterno(
            factura="F001",
            nit="800000001",
            codigo_ciudad="",
            tipo_comprobante="F",
            lineas=[
                LineaInterna(
                    producto_codigo="",
                    lote_raw="",
                    cantidad_origen=Decimal("10"),
                )
            ],
        )
    ]
    resultado = procesar_documentos_internos(self.corte, docs)
    doc = Documento.objects.get(factura="F001", corte=self.corte)
    self.assertEqual(doc.tipo_comprobante, "F")
```

Verificar que `Documento` está importado en el test (si no, agregar: `from cortes.models import ..., Documento`).

- [ ] **Step 2: Correr test para verificar que falla**

```bash
.venv/bin/python manage.py test cortes.tests.test_procesar.ProcesarDocumentosTest.test_tipo_comprobante_se_guarda_en_documento --settings despacha.settings_test
```

Esperado: `AssertionError: '' != 'F'`

- [ ] **Step 3: Implementar en procesar.py**

En `cortes/servicios/procesar.py`, el bloque que crea `Documento` (línea ~58-63):

```python
doc = Documento(
    corte=corte,
    factura=doc_interno.factura,
    nit=doc_interno.nit[:20],
    ciudad=ciudad,
)
```

Reemplazar por:

```python
doc = Documento(
    corte=corte,
    factura=doc_interno.factura,
    nit=doc_interno.nit[:20],
    tipo_comprobante=doc_interno.tipo_comprobante,
    ciudad=ciudad,
)
```

- [ ] **Step 4: Correr tests de procesar**

```bash
.venv/bin/python manage.py test cortes.tests.test_procesar --settings despacha.settings_test
```

Esperado: todos pasan.

- [ ] **Step 5: Commit**

```bash
git add cortes/servicios/procesar.py cortes/tests/test_procesar.py
git commit -m "feat: guardar tipo_comprobante en Documento al procesar"
```

---

### Task 4: Eliminar tipo_comprobante del flujo de carga

**Files:**
- Modify: `cortes/servicios/cargar.py` (líneas 68, 98)
- Modify: `cortes/forms.py`
- Modify: `cortes/views.py` (línea ~101)
- Modify: `cortes/templates/cortes/cargar.html`
- Modify: `cortes/tests/test_vista_cargar.py` (si hay referencias)

- [ ] **Step 1: Eliminar parámetro de cargar_archivo()**

En `cortes/servicios/cargar.py`:

1. Quitar el parámetro `tipo_comprobante: str = "",` de la firma de `cargar_archivo()`
2. Quitar la línea `tipo_comprobante=tipo_comprobante.strip(),` del `Corte.objects.create()`

La firma queda:
```python
def cargar_archivo(
    archivo: UploadedFile,
    usuario: User,
    formato_origen: str,
    numero_corte: int,
    es_adicional: bool = False,
    fecha: date | None = None,
) -> tuple[Corte, ResultadoProcesamiento]:
```

El `Corte.objects.create()` queda sin `tipo_comprobante=...`.

- [ ] **Step 2: Eliminar del formulario**

En `cortes/forms.py`, eliminar el campo `tipo_comprobante`:

```python
# Eliminar estas líneas:
tipo_comprobante = forms.CharField(
    ...
)
```

- [ ] **Step 3: Eliminar de la vista**

En `cortes/views.py`, en `CargarCorteView.post()`, la llamada a `cargar_archivo()` (línea ~95-102):

```python
corte, resultado = cargar_archivo(
    archivo=form.cleaned_data["archivo"],
    usuario=request.user,
    formato_origen=form.cleaned_data["formato_origen"],
    numero_corte=int(form.cleaned_data["numero_corte"]),
    es_adicional=form.cleaned_data.get("es_adicional", False),
    tipo_comprobante=form.cleaned_data.get("tipo_comprobante", ""),  # ← eliminar esta línea
)
```

- [ ] **Step 4: Eliminar del template de carga**

En `cortes/templates/cortes/cargar.html`, eliminar el bloque:

```html
<label for="{{ form.tipo_comprobante.id_for_label }}">{{ form.tipo_comprobante.label }}</label>
{{ form.tipo_comprobante }}
```

- [ ] **Step 5: Correr suite completa**

```bash
.venv/bin/python manage.py test --settings despacha.settings_test
```

Esperado: todos pasan. Si algún test de `test_vista_cargar.py` falla por referencias a `tipo_comprobante`, eliminar esas referencias en los datos de POST de los tests.

- [ ] **Step 6: Commit**

```bash
git add cortes/servicios/cargar.py cortes/forms.py cortes/views.py cortes/templates/cortes/cargar.html cortes/tests/test_vista_cargar.py
git commit -m "feat: eliminar tipo_comprobante manual del formulario de carga"
```

---

### Task 5: Lista — resumen de tipos por corte

**Files:**
- Modify: `cortes/views.py` (`ListaCortesView`)
- Modify: `cortes/templates/cortes/lista.html`

- [ ] **Step 1: Agregar prefetch en get_queryset()**

En `cortes/views.py`, `ListaCortesView.get_queryset()`:

```python
def get_queryset(self):
    hace_30_dias = timezone.localdate() - timedelta(days=30)
    return super().get_queryset().filter(
        fecha__gte=hace_30_dias,
    ).annotate(
        documentos_count=Count("documentos"),
    ).prefetch_related("documentos").order_by("-fecha", "numero_corte", "adicional_letra")
```

- [ ] **Step 2: Calcular tipos en get_context_data()**

En `cortes/views.py`, `ListaCortesView.get_context_data()`:

```python
def get_context_data(self, **kwargs):
    from itertools import groupby
    ctx = super().get_context_data(**kwargs)
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
    return ctx
```

- [ ] **Step 3: Actualizar template**

En `cortes/templates/cortes/lista.html`, reemplazar:

```html
<span class="row-tipo">{{ corte.tipo_comprobante|default:"—" }}</span>
```

por:

```html
<span class="row-tipo">{{ corte.tipos }}</span>
```

- [ ] **Step 4: Correr suite**

```bash
.venv/bin/python manage.py test --settings despacha.settings_test
```

Esperado: todos pasan.

- [ ] **Step 5: Commit**

```bash
git add cortes/views.py cortes/templates/cortes/lista.html
git commit -m "feat: mostrar tipos únicos por corte en lista (prefetch + Python)"
```

---

### Task 6: Detalle — badge tipo por documento

**Files:**
- Modify: `cortes/templates/cortes/detalle.html` (línea ~44-46)

- [ ] **Step 1: Agregar badge en encabezado de documento**

En `cortes/templates/cortes/detalle.html`, el encabezado de cada documento está en:

```html
<div style="display:flex;align-items:center;gap:1rem;">
    <span style="font-family:var(--font-mono);font-weight:500;font-size:13px;color:var(--text);">{{ doc.factura }}</span>
    <span style="font-family:var(--font-mono);font-size:11px;color:var(--text-muted);">NIT {{ doc.nit }}</span>
    <span style="background:var(--surface);border:1px solid var(--border-mid);border-radius:20px;padding:.1rem .5rem;font-family:var(--font-mono);font-size:10px;color:var(--text-soft);">{{ doc.lineas|length }} líneas</span>
</div>
```

Agregar el badge entre NIT y líneas:

```html
<div style="display:flex;align-items:center;gap:1rem;">
    <span style="font-family:var(--font-mono);font-weight:500;font-size:13px;color:var(--text);">{{ doc.factura }}</span>
    <span style="font-family:var(--font-mono);font-size:11px;color:var(--text-muted);">NIT {{ doc.nit }}</span>
    {% if doc.tipo_comprobante %}
    <span style="background:var(--surface);border:1px solid var(--border-mid);border-radius:20px;padding:.1rem .5rem;font-family:var(--font-mono);font-size:10px;color:var(--text-soft);">{{ doc.tipo_comprobante }}</span>
    {% endif %}
    <span style="background:var(--surface);border:1px solid var(--border-mid);border-radius:20px;padding:.1rem .5rem;font-family:var(--font-mono);font-size:10px;color:var(--text-soft);">{{ doc.lineas|length }} líneas</span>
</div>
```

- [ ] **Step 2: Correr suite completa**

```bash
.venv/bin/python manage.py test --settings despacha.settings_test
```

Esperado: 111+ tests pasan.

- [ ] **Step 3: Commit**

```bash
git add cortes/templates/cortes/detalle.html
git commit -m "feat: mostrar tipo_comprobante por documento en vista de detalle"
```
