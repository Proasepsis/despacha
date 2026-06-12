# Documentación Técnica — Despacha

> Versión del documento: junio 2026  
> Autor original del sistema: Sergio Ospitia  
> Propósito: guía de referencia completa para quien deba mantener, extender o entender este software.

---

## Tabla de contenido

1. [¿Qué hace este sistema?](#1-qué-hace-este-sistema)
2. [Stack tecnológico y dependencias](#2-stack-tecnológico-y-dependencias)
3. [Estructura de archivos del proyecto](#3-estructura-de-archivos-del-proyecto)
4. [Arquitectura general](#4-arquitectura-general)
5. [Apps de Django](#5-apps-de-django)
6. [Modelos de base de datos](#6-modelos-de-base-de-datos)
7. [Ciclo de vida de un Corte](#7-ciclo-de-vida-de-un-corte)
8. [Sistema de adaptadores de formato](#8-sistema-de-adaptadores-de-formato)
9. [Lógica de filtrado del archivo de entrada](#9-lógica-de-filtrado-del-archivo-de-entrada)
10. [Servicios de dominio](#10-servicios-de-dominio)
11. [Sistema de adaptadores de destino](#11-sistema-de-adaptadores-de-destino)
12. [Vistas y URLs](#12-vistas-y-urls)
13. [Formularios](#13-formularios)
14. [Roles y permisos de usuario](#14-roles-y-permisos-de-usuario)
15. [Sistema de notificaciones por correo](#15-sistema-de-notificaciones-por-correo)
16. [Registro de auditoría](#16-registro-de-auditoría)
17. [Configuración y variables de entorno](#17-configuración-y-variables-de-entorno)
18. [Despliegue con Docker](#18-despliegue-con-docker)
19. [Pruebas automatizadas](#19-pruebas-automatizadas)
20. [Cómo extender el sistema](#20-cómo-extender-el-sistema)

---

## 1. ¿Qué hace este sistema?

Despacha automatiza el proceso de **corte de facturación** para una operación de despacho/distribución (empresa Proasepsis).

El flujo resumido es:

1. Un operario de facturación **sube un archivo Excel** exportado del sistema contable.
2. El sistema **filtra, parsea y clasifica** las líneas del archivo según criterios contables.
3. El equipo de almacenamiento **revisa y ajusta** los documentos en pantalla.
4. El sistema **genera un archivo XLS de salida** con el formato que requiere el WMS (almacén) y lo entrega a Google Drive y/o descarga directa en el navegador.
5. Se envían **notificaciones por correo** a los equipos involucrados.

Un **corte** es el conjunto de documentos (facturas/remisiones) que se procesan en un período del día. Hay dos cortes por día: Corte 1 (mañana) y Corte 2 (tarde).

---

## 2. Stack tecnológico y dependencias

| Tecnología | Versión | Uso |
|---|---|---|
| Python | 3.11+ | Lenguaje principal |
| Django | 5.2 | Framework web y ORM |
| PostgreSQL | 15+ | Base de datos principal (producción) |
| SQLite | built-in | Base de datos en pruebas |
| psycopg | 3.2 | Driver PostgreSQL |
| gunicorn | 23.0 | Servidor WSGI para producción |
| django-environ | 0.11 | Lectura de variables `.env` |
| whitenoise | 6.7 | Servir archivos estáticos sin nginx |
| openpyxl | 3.1 | Leer archivos `.xlsx` de entrada |
| xlwt | 1.3 | Escribir archivos `.xls` de salida |
| xlrd | 2.0 | Leer `.xls` (soporte legacy) |
| google-api-python-client | 2.140 | SDK para subir a Google Drive |
| google-auth | 2.34 | Autenticación con cuenta de servicio Google |
| Docker / Docker Compose | — | Entorno de despliegue |

---

## 3. Estructura de archivos del proyecto

```
despacha/                          ← raíz del proyecto
├── core/                          ← app de infraestructura compartida
│   ├── adaptadores/
│   │   ├── base.py                ← interfaz abstracta AdaptadorFormato
│   │   ├── modelo_interno.py      ← dataclasses DocumentoInterno / LineaInterna
│   │   ├── registry.py            ← registro de adaptadores de formato
│   │   ├── plantilla/             ← único adaptador de formato implementado
│   │   │   ├── adaptador.py       ← lógica de parseo del Excel de entrada
│   │   │   └── limpieza.py        ← función limpiar_lote()
│   │   └── destinos/
│   │       ├── base.py            ← interfaz abstracta AdaptadorDestino
│   │       ├── registry.py        ← registro estático de destinos
│   │       ├── descarga.py        ← destino: descarga directa en navegador
│   │       └── drive.py           ← destino: Google Drive
│   ├── models.py                  ← ParametroSalida, ReglaClasificacion, NotificacionDestinatarios
│   ├── servicios/
│   │   ├── notificaciones.py      ← envío de emails
│   │   └── auditoria.py           ← helper de auditoría compartida
│   ├── views.py                   ← vista de auditoría y panel de configuración
│   └── urls.py
│
├── cortes/                        ← app principal del dominio
│   ├── models.py                  ← Corte, CorteVersion, Documento, Linea, Auditoria, PresenciaCorte
│   ├── forms.py                   ← CargarCorteForm
│   ├── views.py                   ← todas las vistas
│   ├── urls.py
│   └── servicios/
│       ├── cargar.py              ← subida y pre-procesamiento del archivo
│       ├── procesar.py            ← creación de Documentos y Lineas en BD
│       ├── generar.py             ← orquestación de la generación del XLS
│       ├── generar_archivo.py     ← construcción byte a byte del XLS de salida
│       ├── split.py               ← dividir/reunir documentos
│       ├── bloqueo.py             ← sistema de lock optimista por usuario
│       ├── auditoria.py           ← registro de cambios
│       ├── nombrado.py            ← nombre del archivo de salida
│       └── corte_por_hora.py      ← sugerir corte 1 ó 2 según la hora
│
├── productos/                     ← app del catálogo maestro (solo lectura desde cortes)
│   └── models.py                  ← Producto, Ciudad
│
├── despacha/                      ← configuración del proyecto Django
│   ├── settings.py                ← configuración de producción
│   ├── settings_test.py           ← configuración para pruebas (SQLite)
│   ├── urls.py                    ← URL raíz
│   └── wsgi.py
│
├── templates/                     ← plantillas HTML (Django templates)
│   └── cortes/
│       ├── lista.html
│       ├── cargar.html
│       └── detalle.html
│
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env.example
```

---

## 4. Arquitectura general

```
                        ┌─────────────────────────────────────┐
                        │            NAVEGADOR                 │
                        │  (operario facturación / almacén)    │
                        └──────────────┬──────────────────────┘
                                       │ HTTP
                        ┌──────────────▼──────────────────────┐
                        │        Django / Gunicorn             │
                        │  ┌─────────┐  ┌──────────────────┐  │
                        │  │  Views  │  │   Admin Django   │  │
                        │  └────┬────┘  └──────────────────┘  │
                        │       │                              │
                        │  ┌────▼──────────────────────────┐  │
                        │  │         Servicios              │  │
                        │  │  cargar · procesar · generar   │  │
                        │  │  split · bloqueo · auditoria   │  │
                        │  └────┬──────────────────────┬───┘  │
                        │       │                      │       │
                        │  ┌────▼────┐          ┌──────▼────┐ │
                        │  │  ORM    │          │ Adaptador │ │
                        │  │ Django  │          │  formato  │ │
                        │  └────┬────┘          └──────┬────┘ │
                        └───────┼──────────────────────┼──────┘
                                │                      │
               ┌────────────────▼──┐           ┌───────▼─────────┐
               │   PostgreSQL      │           │  Archivo .xlsx  │
               │   (datos y audit) │           │  (entrada)      │
               └───────────────────┘           └─────────────────┘

Destinos de salida:
  ┌──────────────────┐    ┌──────────────────┐
  │  Google Drive    │    │  Descarga .xls   │
  │  (carpeta/mes/   │    │  en navegador    │
  │   día)           │    └──────────────────┘
  └──────────────────┘
```

El sistema tiene **tres capas**:

- **Vistas**: reciben HTTP, validan permisos, delegan todo a servicios.
- **Servicios**: contienen toda la lógica de negocio; nunca mezclan HTTP con dominio.
- **Modelos/ORM**: representan el estado persistente.

---

## 5. Apps de Django

### `core` — Infraestructura compartida

Contiene lo que es reutilizable por las demás apps:
- Los modelos de configuración global (`ParametroSalida`, `ReglaClasificacion`, `NotificacionDestinatarios`).
- El sistema de adaptadores de formato (cómo leer el archivo de entrada).
- El sistema de adaptadores de destino (cómo entregar el archivo de salida).
- El servicio de notificaciones por correo.

### `cortes` — Dominio principal

Todo el proceso del corte vive aquí:
- Los modelos de datos del corte (`Corte`, `Documento`, `Linea`, etc.).
- Todas las vistas que el usuario ve.
- Todos los servicios de dominio (cargar, procesar, generar, split, bloqueo, auditoría).

### `productos` — Catálogo maestro

Base de datos de productos conocidos. El sistema la consulta al cargar un corte para resolver los códigos de producto. Se considera de **solo lectura desde la perspectiva de los cortes** — se actualiza externamente (vía admin o comando de importación).

---

## 6. Modelos de base de datos

### `cortes.Corte` — El corte de facturación

Campo principal que agrupa todos los documentos de un período.

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | BigAutoField (PK) | Identificador único |
| `archivo` | CharField(255) | Nombre original del archivo subido |
| `formato_origen` | CharField(20) | Siempre `"PLANTILLA"` por ahora |
| `hash_sha256` | CharField(64) | Hash del archivo para detectar duplicados |
| `usuario_carga` | FK → User | Quién subió el archivo |
| `fecha` | DateField | Fecha del corte (indexada) |
| `numero_corte` | SmallInt | 1 ó 2 (Corte 1 / Corte 2) |
| `adicional_letra` | CharField(1) | `""` para el principal; `"A"`, `"B"`... para adicionales del mismo día |
| `tipo_comprobante` | CharField(80) | Texto libre descriptivo (ej: "F1, H5") — solo informativo, no filtra |
| `estado` | CharField(20) | `cargado` → `en_revision` → `generado` / `con_error` |
| `version_actual` | SmallInt | Número de veces que se ha generado el XLS (0 = nunca generado) |
| `bloqueado_por` | FK → User (nullable) | Usuario que tiene el corte abierto para editar |
| `bloqueado_hasta` | DateTimeField (nullable) | Expira el lock a los 30 minutos |
| `creado_en` / `actualizado_en` | DateTimeField | Timestamps automáticos |

**Restricción única**: `(fecha, numero_corte, adicional_letra)` — no puede haber dos cortes para el mismo día, número y letra.

---

### `cortes.CorteVersion` — Historial de versiones generadas

Cada vez que se genera (o regenera) el XLS se crea un registro aquí.

| Campo | Tipo | Descripción |
|---|---|---|
| `corte` | FK → Corte | A qué corte pertenece |
| `numero` | SmallInt | Número de versión (1, 2, 3…) |
| `drive_url` | URLField | URL en Google Drive (vacío si no se usó Drive) |
| `archivo_hash` | CharField(64) | SHA-256 del XLS generado |
| `usuario` | FK → User | Quién generó |
| `fecha_generacion` | DateTimeField | Cuándo se generó |
| `motivo` | TextField | Motivo de regeneración (libre) |

---

### `cortes.Documento` — Una factura/remisión dentro del corte

| Campo | Tipo | Descripción |
|---|---|---|
| `corte` | FK → Corte | Corte al que pertenece |
| `factura` | CharField(30) | Número del documento (ej: `"1430462000"`) |
| `nit` | CharField(20) | NIT del cliente |
| `ciudad` | FK → Ciudad (nullable) | Ciudad de destino |
| `clasificador1` | CharField(20) | `"EMBALAR"` / `"NO EMBALAR"` / `"PREGUNTAR"` |
| `observaciones` | CharField(20) | `"PRIORIDAD"` / `"NO PRIORIDAD"` |
| `subsanar_novedad` | BooleanField | Indica si se aplica sufijo de novedad |
| `factura_sufijo` | CharField(10) | Sufijo agregado al número de factura para novedades |
| `creado_por_split_de` | FK → Documento (nullable) | Si fue creado por un split, apunta al documento origen |

---

### `cortes.Linea` — Una línea de producto dentro de un documento

| Campo | Tipo | Descripción |
|---|---|---|
| `documento` | FK → Documento | Documento al que pertenece |
| `referencia` | CharField(50) | Referencia del producto (del catálogo) |
| `lote` | CharField(50) | Número de lote (ya limpiado) |
| `cantidad_origen` | Decimal(12,2) | Cantidad del archivo fuente |
| `cantidad_unidades` | Decimal(14,2) | `cantidad_origen × unidad_empaque` (editable) |
| `sin_maestro` | BooleanField | `True` si el producto no existe en el catálogo |
| `inactivo` | BooleanField | `True` si el producto existe pero está inactivo |
| `referencia_snapshot` | CharField(50) | Copia de la referencia al momento de procesar |
| `descripcion_snapshot` | CharField(200) | Copia de la descripción al momento de procesar |
| `unidad_empaque_snapshot` | PositiveInt | Copia de la unidad de empaque al momento de procesar |
| `movida_desde` | FK → Documento (nullable) | Si la línea fue movida por un split, apunta al doc origen |

> **¿Por qué los `_snapshot`?** Porque el catálogo de productos puede cambiar. El XLS de salida usa los valores del momento en que se procesó el corte, no los valores actuales del catálogo.

---

### `cortes.Auditoria` — Registro de cada cambio

| Campo | Tipo | Descripción |
|---|---|---|
| `fecha` | DateTimeField | Cuándo ocurrió |
| `usuario` | FK → User (nullable) | Quién lo hizo (null = sistema) |
| `objeto_tipo` | CharField(50) | `"Corte"`, `"Documento"`, `"Linea"`, etc. |
| `objeto_id` | CharField(50) | PK del objeto afectado |
| `campo` | CharField(50) | Campo que cambió |
| `valor_anterior` | TextField | Valor antes del cambio |
| `valor_nuevo` | TextField | Valor después del cambio |
| `tipo_evento` | CharField(30) | Ver tabla de eventos abajo |
| `metadata` | JSONField | Datos adicionales libres |

**Tipos de evento**:

| Código | Descripción |
|---|---|
| `edicion` | Cambio de un campo por un usuario |
| `regeneracion` | El XLS fue regenerado (versión > 1) |
| `split` | Un documento fue dividido |
| `deshacer_split` | Se deshizo un split |
| `forzar_liberacion` | Admin liberó el lock de otro usuario |
| `creacion` | Primera generación del XLS |
| `inactivacion` | Línea marcada inactiva |
| `login_fallido` | Intento de login fallido |
| `notificacion_fallida` | Fallo al enviar un correo |

---

### `cortes.PresenciaCorte` — Quién está viendo un corte ahora mismo

| Campo | Tipo | Descripción |
|---|---|---|
| `user` | FK → User | Usuario presente |
| `corte` | FK → Corte | Corte que está viendo |
| `visto_en` | DateTimeField | Último ping (se actualiza cada ~20 segundos vía JS) |

Se usa para mostrar avatares en tiempo real. Los registros con más de 25 segundos de antigüedad se eliminan automáticamente.

---

### `core.ParametroSalida` — Parámetros de configuración del XLS de salida

| Campo | Tipo | Descripción |
|---|---|---|
| `clave` (PK) | CharField(50) | Nombre del parámetro |
| `valor` | CharField(200) | Valor configurado |
| `descripcion` | CharField(300) | Texto descriptivo para el admin |

Parámetros utilizados en la generación del XLS:

| Clave | Descripción |
|---|---|
| `punto` | Código del punto de venta |
| `identificacion` | NIT de la empresa |
| `nombre` | Nombre de la empresa |
| `direccion` | Dirección de la empresa |
| `tipo_doc_ref` | Tipo de documento de referencia (ej: `"FA"`) |
| `estado_articulo` | Estado del artículo en el WMS |
| `ciudad_default` | Ciudad a usar cuando el documento no tiene ciudad configurada |

---

### `core.ReglaClasificacion` — Reglas automáticas de clasificación

Permite configurar valores automáticos para `clasificador1` y `observaciones` según criterios. (Implementado en el modelo, la lógica de aplicación está pendiente de completar.)

| Campo | Tipo | Descripción |
|---|---|---|
| `nombre` | CharField(100) | Nombre de la regla |
| `campo_destino` | CharField(20) | `"clasificador1"` ó `"observaciones"` |
| `valor_por_defecto` | CharField(50) | Valor a asignar |
| `activa` | BooleanField | Si la regla está activa |
| `prioridad` | SmallInt | Orden de evaluación |

---

### `core.NotificacionDestinatarios` — A quién enviar cada tipo de correo

| Campo | Tipo | Descripción |
|---|---|---|
| `evento` (PK) | CharField(50) | Tipo de evento (`corte_generado`, `corte_regenerado`, `sin_maestro_detectado`) |
| `correos` | TextField | Lista de correos separados por coma o salto de línea |
| `activo` | BooleanField | Si este evento envía correos |

---

### `productos.Producto` — Catálogo maestro de productos

| Campo | Tipo | Descripción |
|---|---|---|
| `producto` (PK) | CharField(13) | Código de 13 dígitos: `LLL GGGG CCCCCC` (línea+grupo+código) |
| `referencia` | CharField(50) | Referencia comercial del producto |
| `descripcion` | CharField(200) | Descripción del producto |
| `unidad_empaque` | PositiveInt | Unidades por caja/empaque |
| `activo` | BooleanField | Si el producto está vigente |
| `revisado` | BooleanField | Si fue revisado manualmente |

---

### `productos.Ciudad` — Catálogo de ciudades

| Campo | Tipo | Descripción |
|---|---|---|
| `codigo` (PK) | CharField(20) | Código de la ciudad (ej: `"11001"` para Bogotá) |
| `nombre` | CharField(100) | Nombre completo |
| `nombre_archivo` | CharField(100) | Nombre que se usa como pestaña en el XLS de salida |
| `activo` | BooleanField | Si está activa |

---

## 7. Ciclo de vida de un Corte

```
                  ┌──────────────────────────────────────────┐
                  │           ESTADO: (nuevo)                 │
                  └──────────────────┬───────────────────────┘
                                     │  usuario sube archivo
                          ┌──────────▼──────────┐
                          │   ESTADO: cargado   │  ← se crea el registro Corte
                          └──────────┬──────────┘
                                     │  adaptador parsea y procesa documentos
                          ┌──────────▼──────────┐
                          │ ESTADO: en_revision │  ← Documentos y Lineas en BD
                          └──────────┬──────────┘
                     ╔═══════════════╪══════════╗
                     ║  Revisión y edición      ║
                     ║  (usuarios almacén)      ║
                     ╚═══════════════╪══════════╝
                                     │  usuario genera XLS
                          ┌──────────▼──────────┐
                          │  ESTADO: generado   │  ← XLS entregado
                          └─────────────────────┘
                                     │  (puede regenerarse: vuelve al mismo estado)
                          ┌──────────▼──────────┐
                          │   ESTADO: con_error │  ← fallo al entregar
                          └─────────────────────┘
```

### Paso 1: Cargar (`cargar.py`)

1. Se calcula el **SHA-256** del archivo. Si ya existe un corte con ese hash, se rechaza como duplicado.
2. Se verifica que no exista ya un corte para esa fecha y número. Si existe, se sugiere marcarlo como "adicional".
3. Se crea el registro `Corte` en estado `cargado`.
4. El **adaptador de formato** valida y parsea el archivo a una lista de `DocumentoInterno`.
5. Se llama a `procesar_documentos_internos` para crear `Documento` y `Linea` en la BD.
6. El corte pasa a estado `en_revision`.
7. Si se detectaron productos sin maestra, se envía un correo de alerta.

### Paso 2: Revisar (vistas `DetalleCorteView` / `EditarCorteView`)

- El usuario de almacenamiento **toma un bloqueo** (lock de 30 minutos) para evitar ediciones simultáneas.
- Puede cambiar en cada `Documento`:
  - `clasificador1`: `EMBALAR`, `NO EMBALAR`, `PREGUNTAR`
  - `observaciones`: `PRIORIDAD`, `NO PRIORIDAD`
  - `subsanar_novedad` y `factura_sufijo` (para documentos con novedad)
- Puede cambiar en cada `Linea`:
  - `cantidad_unidades`
- Puede **dividir un documento** (split): mover algunas líneas a una nueva factura derivada.
- Puede **deshacer el split** si aún no se generó.

### Paso 3: Generar (`generar.py` + `generar_archivo.py`)

1. Se verifica que no haya líneas con `sin_maestro=True` (bloqueo de generación).
2. Se construye el XLS de salida en memoria con `xlwt`.
3. El XLS se entrega a cada destino seleccionado (Drive, descarga).
4. Si todos los destinos exitosos: estado → `generado`, `version_actual += 1`, se crea `CorteVersion`.
5. Se envía correo de notificación (`generado` o `regenerado`).

---

## 8. Sistema de adaptadores de formato

**Propósito**: desacoplar la lógica de parsing del resto del sistema. Si en el futuro el sistema contable cambia el formato del archivo, solo hay que crear un nuevo adaptador sin tocar nada más.

### Interfaz base (`core/adaptadores/base.py`)

```python
class AdaptadorFormato(ABC):
    nombre: str                                          # identificador en mayúsculas

    def validar(self, ruta_archivo: Path) -> None:       # lanza ValueError si es inválido
    def parse(self, ruta_archivo: Path) -> list[DocumentoInterno]:  # retorna documentos
```

### Modelo interno (`core/adaptadores/modelo_interno.py`)

Es el formato neutral que usan todos los adaptadores para comunicarse con el dominio:

```python
@dataclass
class LineaInterna:
    producto_codigo: str      # código de 13 dígitos ya armado
    lote_raw: str             # lote sin limpiar (limpieza se aplica después)
    cantidad_origen: Decimal
    descripcion_origen: str   # descripción del archivo de origen

@dataclass
class DocumentoInterno:
    factura: str
    nit: str
    codigo_ciudad: str
    lineas: list[LineaInterna]
```

### Registro de adaptadores (`core/adaptadores/registry.py`)

- El decorador `@registrar` registra automáticamente un adaptador al importarse su módulo.
- `obtener("PLANTILLA")` devuelve una instancia del adaptador.
- `disponibles()` lista los adaptadores registrados.
- El registro hace **auto-discovery**: al importarse por primera vez, escanea subdirectorios de `adaptadores/` e importa los `__init__.py`.

### Adaptador PLANTILLA (`core/adaptadores/plantilla/adaptador.py`)

El único adaptador implementado. Lee archivos `.xlsx` exportados del sistema contable con esta estructura:

- **Hoja**: `Hoja1`
- **Fila 5**: encabezados de columnas
- **Fila 6 en adelante**: datos

La búsqueda de columnas es **tolerante**: usa búsqueda parcial por contenido (si el encabezado contiene el texto esperado, se acepta), y convierte a mayúsculas antes de comparar.

#### Función `_armar_codigo_producto`

Construye el código de 13 dígitos que se usa para buscar en el catálogo:

```
LÍNEA PRODUCTO (3 dígitos) + GRUPO PRODUCTO (4 dígitos) + CÓDIGO PRODUCTO (6 dígitos)
Ejemplo: 150 + 5 + 5  →  "150" + "0005" + "000005"  =  "1500005000005"
```

#### Función `limpiar_lote` (`core/adaptadores/plantilla/limpieza.py`)

Aplica estas transformaciones en orden:
1. **Comilla inicial**: `'122090426` → `122090426`
2. **Slash**: corta desde el `/` inclusive → `122/A` → `122`
3. **Puntos al inicio**: `.122` → `122`
4. **Espacios**: elimina todos los espacios internos
5. **Guion terminal solo**: `122-` → `122-1`
6. **Punto al final**: se conserva tal cual (es parte del lote)

---

## 9. Lógica de filtrado del archivo de entrada

Al parsear el Excel, cada fila se evalúa contra **cuatro filtros en cascada**. Si falla cualquiera, la fila se descarta silenciosamente.

```
Fila del Excel
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│ Filtro 1: TIPO DE COMPROBANTE debe estar en CODIGOS_PERMITIDOS │
│   {"F": 1, "H": 5, "S": 1, "T": 10}                        │
│   Ejemplo: tipo "Z" → descartado                             │
└──────────────────────────────────┬──────────────────────────┘
                                   │ pasa
                                   ▼
┌─────────────────────────────────────────────────────────────┐
│ Filtro 2: CÓDIGO COMPROBANTE debe coincidir con el esperado  │
│   Ejemplo: tipo "T" esperaba código 10, llegó "5" → descartado │
└──────────────────────────────────┬──────────────────────────┘
                                   │ pasa
                                   ▼
┌─────────────────────────────────────────────────────────────┐
│ Filtro 3: CUENTA CONTABLE debe comenzar con "14"             │
│   Ejemplo: cuenta "413535" → descartado                      │
└──────────────────────────────────┬──────────────────────────┘
                                   │ pasa
                                   ▼
┌─────────────────────────────────────────────────────────────┐
│ Filtro 4: DÉBITO O CRÉDITO debe ser "C" (Crédito)           │
│   Ejemplo: valor "D" → descartado                            │
└──────────────────────────────────┬──────────────────────────┘
                                   │ pasa
                                   ▼
                          Fila incluida en el resultado
```

### Tabla de tipos y códigos permitidos

| Tipo comprobante | Código esperado | Descripción |
|---|---|---|
| `F` | `1` | Factura de venta |
| `H` | `5` | Remisión |
| `S` | `1` | Devolución / nota |
| `T` | `10` | Traslado entre bodegas |

> **Importante**: el campo `tipo_comprobante` que el usuario escribe en el formulario de carga es solo **informativo** (se guarda en el `Corte` y se muestra en la lista). El filtro real siempre usa el diccionario `CODIGOS_PERMITIDOS` aplicado fila por fila al Excel.

> **Nota sobre T+10 con D**: Las líneas de tipo `T` código `10` con `DÉBITO O CRÉDITO = D` son **descartadas** por el Filtro 4. Si se requiere incluir débitos para traslados, debe modificarse el filtro en `adaptador.py` línea 209.

---

## 10. Servicios de dominio

### `cargar.py` — Subida del archivo

**Función principal**: `cargar_archivo(archivo, usuario, formato_origen, numero_corte, es_adicional, tipo_comprobante, fecha) → (Corte, ResultadoProcesamiento)`

**Excepciones que puede lanzar**:
- `ErrorDuplicado(corte_existente_id)`: el mismo archivo ya fue subido.
- `ErrorSugerirAdicional(numero_corte, fecha)`: ya existe ese corte ese día, sugiere marcarlo adicional.
- `ErrorCombinacionFechaCorte`: combinación fecha+número+letra ya existe.
- `ErrorValidacionAdaptador`: el archivo no tiene la estructura esperada.
- `ErrorCarga`: error genérico de carga.

**Función auxiliar**: `_siguiente_letra_adicional(fecha, numero_corte)` — devuelve la siguiente letra libre (A, B, C, D, E) para cortes adicionales.

---

### `procesar.py` — Creación de documentos en BD

**Función principal**: `procesar_documentos_internos(corte, documentos) → ResultadoProcesamiento`

1. Carga en bulk todos los productos y ciudades referenciados (una sola consulta de cada uno).
2. Para cada `DocumentoInterno`: crea un `Documento` en BD.
3. Para cada `LineaInterna`: resuelve el producto en el catálogo y crea una `Linea`:
   - Si el producto existe y está activo: `sin_maestro=False`.
   - Si el producto existe pero está inactivo: `sin_maestro=False`, `inactivo=True`.
   - Si el producto no existe: `sin_maestro=True`; genera descripción `"(sin maestra) ..."`.
4. Usa `bulk_create` para insertar todo en dos consultas (documentos + líneas).

**Dataclass de resultado**:
```python
@dataclass
class ResultadoProcesamiento:
    corte: Corte
    documentos_creados: int
    lineas_creadas: int
    lineas_sin_maestro: int
    lineas_inactivas: int
    productos_nuevos_detectados: list[str]  # códigos sin maestra
```

---

### `generar.py` — Orquestación de la generación

**Función principal**: `generar_y_entregar(corte, destinos, usuario, motivo) → dict`

Precondiciones que valida:
- No hay líneas con `sin_maestro=True`.
- La lista de destinos no está vacía.
- Todos los destinos existen en el registro.

Retorna un dict con: `success`, `resultados` (por destino), `archivo_bytes`, `nombre_archivo`, `version`, `errores`.

---

### `generar_archivo.py` — Construcción del XLS de salida

**Función principal**: `generar_xls(corte) → bytes`

- Agrupa los documentos por ciudad (`doc.ciudad.nombre_archivo`).
- Crea una **pestaña por ciudad** en el XLS (nombre truncado a 31 chars, límite de Excel).
- Columnas del XLS de salida (en orden):

| Columna | Fuente |
|---|---|
| `punto` | `ParametroSalida["punto"]` |
| `identificacion` | `ParametroSalida["identificacion"]` |
| `nombre` | `ParametroSalida["nombre"]` |
| `ciudad` | `ciudad.nombre_archivo` |
| `direccion` | `ParametroSalida["direccion"]` |
| `tipo_documento_referencia` | `ParametroSalida["tipo_doc_ref"]` |
| `documento_referencia` | `doc.factura + doc.factura_sufijo` |
| `fecha_envio` | vacío |
| `hora_envio` | vacío |
| `bodega_alistamiento` | vacío |
| `sector_alistamiento` | vacío |
| `area_alistamiento` | vacío |
| `clasificador1` | `doc.clasificador1` |
| `clasificador2` | `doc.factura + doc.factura_sufijo` |
| `observaciones` | `doc.observaciones` |
| `articulo` | `linea.referencia_snapshot` |
| `lote` | `linea.lote` |
| `estado_articulo` | `ParametroSalida["estado_articulo"]` |
| `sscc`, `sscc_completo` | vacío |
| `cantidad` | `linea.cantidad_unidades` (entero si es exacto) |
| `campo1`, `campo2` | vacío |
| `valor` | vacío |
| `descripcion` | `linea.descripcion_snapshot` |
| `dato_adicional` | vacío |
| `zona`, `prioridad`, `telefono`, `email`, `Proveedor` | vacío |

---

### `split.py` — Dividir y reunir documentos

**`partir_documento(documento_origen, lineas_ids_a_mover, usuario) → Documento`**

- Crea un nuevo `Documento` con la factura `{factura_original}{letra}` (ej: `1430462000A`).
- Mueve las líneas seleccionadas al nuevo documento.
- El nuevo documento hereda `ciudad`, `clasificador1`, `observaciones` del original.
- Registra auditoría de tipo `split`.

**`deshacer_split(documento_nuevo, usuario)`**

- Solo funciona si el corte está en `en_revision`.
- Devuelve todas las líneas al documento original.
- Elimina el documento hijo.
- Registra auditoría de tipo `deshacer_split`.

---

### `bloqueo.py` — Lock optimista por usuario

Evita que dos usuarios editen el mismo corte simultáneamente.

| Función | Descripción |
|---|---|
| `intentar_tomar_bloqueo(corte, usuario)` | Toma el lock si está libre o expirado. Devuelve `True`/`False`. |
| `refrescar_bloqueo(corte, usuario)` | Extiende el lock 30 minutos más. |
| `liberar_bloqueo(corte, usuario, forzado_por_admin)` | Libera el lock. Si es forzado, registra auditoría. |
| `info_bloqueo(corte)` | Devuelve info del lock actual o `None` si está libre/expirado. |

El lock expira automáticamente a los **30 minutos** (constante `TIMEOUT_BLOQUEO`).

---

### `corte_por_hora.py` — Sugerencia automática de corte

`sugerir_corte(ahora?) → int`

- Hora < 12:00 Bogotá → devuelve `1` (Corte 1)
- Hora ≥ 12:00 Bogotá → devuelve `2` (Corte 2)

---

### `nombrado.py` — Nombre del archivo de salida

`nombre_archivo_corte(corte, siguiente_version?) → str`

Ejemplos:
- Primera vez: `"JUN 11 corte 1.xls"`
- Segunda versión: `"JUN 11 corte 1 (v2).xls"`

---

### `auditoria.py` (cortes) — Registro de cambios

`registrar_auditoria(usuario, objeto_tipo, objeto_id, tipo_evento, campo?, valor_anterior?, valor_nuevo?) → Auditoria`

Crea un registro en la tabla `Auditoria`. Se llama en cada operación de edición, generación o split.

---

## 11. Sistema de adaptadores de destino

**Propósito**: desacoplar la entrega del XLS de su generación. Se puede añadir un nuevo destino (ej: FTP, email con adjunto) sin cambiar la lógica de generación.

### Interfaz base (`core/adaptadores/destinos/base.py`)

```python
@dataclass
class ResultadoEntrega:
    ok: bool
    referencia: str = ""   # URL o identificador del archivo entregado
    error: str = ""        # descripción del error si ok=False

class AdaptadorDestino(ABC):
    codigo: str            # identificador interno (ej: "drive")
    nombre_mostrar: str    # texto para el usuario

    def entregar(self, archivo_bytes: bytes, nombre_archivo: str, corte: Corte) -> ResultadoEntrega:
```

### Destino: `descarga` (`destinos/descarga.py`)

Retorna `ResultadoEntrega(ok=True, referencia="descarga")`. La vista `GenerarCorteView` detecta este destino y construye una respuesta HTTP con `Content-Disposition: attachment`.

### Destino: `drive` (`destinos/drive.py`)

Sube el archivo a Google Drive usando una **cuenta de servicio**:

1. Lee credenciales desde el path en `DRIVE_SERVICE_ACCOUNT_JSON`.
2. Determina la carpeta destino: `[DRIVE_ROOT_FOLDER_ID] / [MES en mayúsculas] / [día]`.
3. Crea las carpetas si no existen (función `_buscar_o_crear_carpeta`).
4. Sube el archivo con reintentos (hasta 3 intentos, esperas de 1, 3 y 10 segundos).
5. Retorna la URL de vista web del archivo (`webViewLink`).

### Registro de destinos (`destinos/registry.py`)

Es un diccionario estático (no usa autodiscovery como el de formatos):

```python
DESTINOS_DISPONIBLES = {
    "descarga": AdaptadorDestinoDescarga,
    "drive": AdaptadorDestinoDrive,
}
```

---

## 12. Vistas y URLs

### URLs del proyecto

| URL | Vista | Nombre |
|---|---|---|
| `/` | Redirect a lista | `home` |
| `/admin/` | Admin de Django | — |
| `/admin-auditoria/` | Lista de auditoría | `admin_auditoria` |
| `/admin-auditoria/config/` | Panel de configuración | `panel_config` |
| `/cortes/` | Lista de cortes | `lista_cortes` |
| `/cortes/cargar/` | Subir nuevo corte | `cargar_corte` |
| `/cortes/<pk>/` | Detalle de un corte | `detalle_corte` |
| `/cortes/<pk>/editar/` | Editar (AJAX POST) | `editar_corte` |
| `/cortes/<pk>/split/` | Partir documento (AJAX POST) | `split_documento` |
| `/cortes/<pk>/deshacer-split/` | Deshacer split (AJAX POST) | `deshacer_split` |
| `/cortes/<pk>/forzar-liberacion/` | Liberar lock (AJAX POST) | `forzar_liberacion` |
| `/cortes/<pk>/generar/` | Generar XLS (POST) | `generar_corte` |
| `/cortes/<pk>/presencia/` | Ping de presencia (GET/POST) | `presencia_corte` |
| `/cortes/salir/` | Logout | `logout` |

### Vistas principales

**`ListaCortesView`**: muestra los cortes de los últimos 30 días agrupados por fecha y número de corte. Paginación de 20 elementos.

**`CargarCorteView`**: formulario GET/POST. En GET sugiere el número de corte según la hora. En POST llama a `cargar_archivo` y maneja todos los errores con mensajes específicos.

**`DetalleCorteView`**: serializa todos los documentos y líneas del corte a JSON embebido en el template para que el frontend JavaScript los muestre y gestione.

**`EditarCorteView`** (AJAX): recibe `{tipo, id, campo, valor}` por POST JSON. Valida permisos, actualiza el campo y registra auditoría.

**`GenerarCorteView`** (AJAX): recibe lista de `destinos` y `motivo`. Si el destino incluye `descarga`, devuelve el binario directamente como response HTTP en lugar de JSON.

**`PresenciaPingView`**: GET devuelve lista de usuarios activos en el corte (pings en los últimos 25 segundos). POST registra/actualiza la presencia del usuario actual.

---

## 13. Formularios

### `CargarCorteForm`

| Campo | Tipo | Validaciones |
|---|---|---|
| `archivo` | FileField | Máx 10 MB, extensión `.xlsx` o `.xls` |
| `formato_origen` | ChoiceField | Solo `"PLANTILLA"` disponible |
| `numero_corte` | ChoiceField | `1` ó `2` |
| `es_adicional` | BooleanField | Opcional, default `False` |
| `tipo_comprobante` | CharField(80) | Opcional, solo informativo |

---

## 14. Roles y permisos de usuario

El sistema usa los **Grupos de Django** para controlar permisos:

| Grupo | Puede hacer |
|---|---|
| `facturacion` | Subir archivos (cargar cortes) |
| `almacenamiento` | Ver detalle, editar documentos, generar XLS, split/deshacer, presencia |
| `admin` | Todo lo anterior + forzar liberación de locks |
| Superusuario Django | Acceso total incluyendo el admin de Django |

Los mixins en `views.py`:
- `EsFacturacionOAdminMixin`: permite `facturacion` o `admin`
- `EsAlmacenamientoOAdminMixin`: permite `almacenamiento` o `admin`

La sesión expira a las **8 horas** (`SESSION_COOKIE_AGE = 8 * 3600`).

---

## 15. Sistema de notificaciones por correo

**Archivo**: `core/servicios/notificaciones.py`

### Tres eventos que disparan correo

| Función | Evento | Cuándo |
|---|---|---|
| `notificar_corte_generado(corte)` | `corte_generado` | Primera vez que se genera el XLS (versión 1) |
| `notificar_corte_regenerado(corte)` | `corte_regenerado` | Cuando se regenera (versión > 1) — incluye motivo |
| `notificar_sin_maestra_detectado(corte, codigos)` | `sin_maestro_detectado` | Al cargar, si hay productos sin maestra |

### Configuración

- Los destinatarios se configuran en el admin en `NotificacionDestinatarios`, uno por evento.
- Los correos van separados por coma o salto de línea.
- Si el registro no existe o está inactivo, no se envía nada (sin error).
- En modo `DEBUG=True`: los correos se imprimen en consola (no se envían).
- En staging: el asunto tiene prefijo `[STAGING] `.
- Los fallos de envío se registran en `Auditoria` con tipo `notificacion_fallida`.

### Configuración SMTP (en `.env`)

```
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=sistema@proasepsis.com
EMAIL_HOST_PASSWORD=...
DEFAULT_FROM_EMAIL=Despacha <sistema@proasepsis.com>
```

---

## 16. Registro de auditoría

Cada operación relevante del sistema deja huella en la tabla `Auditoria`. Las vistas de auditoría están en `/admin-auditoria/`.

**Lo que se audita**:
- Toda edición de campo en `Documento` o `Linea`
- Generación y regeneración de XLS
- Split y deshacer split
- Forzar liberación de bloqueo
- Fallos de notificación

El campo `metadata` (JSONField) permite guardar datos adicionales sin esquema fijo.

---

## 17. Configuración y variables de entorno

El archivo `.env` (copiar desde `.env.example`) controla toda la configuración:

| Variable | Descripción | Ejemplo |
|---|---|---|
| `SECRET_KEY` | Clave secreta Django (obligatoria) | cadena aleatoria larga |
| `DEBUG` | Modo debug | `False` en producción |
| `ALLOWED_HOSTS` | Hosts permitidos | `despacha.proasepsis.com` |
| `CSRF_TRUSTED_ORIGINS` | Orígenes CSRF de confianza | `https://despacha.proasepsis.com` |
| `DB_NAME` | Nombre de la BD | `despacha` |
| `DB_USER` | Usuario de la BD | `despacha` |
| `DB_PASSWORD` | Contraseña de la BD | — |
| `DB_HOST` | Host de la BD | `db` (nombre del servicio Docker) |
| `DB_PORT` | Puerto de la BD | `5432` |
| `ENVIRONMENT` | `production` ó `staging` | `production` |
| `EMAIL_HOST` | Servidor SMTP | `smtp.gmail.com` |
| `EMAIL_PORT` | Puerto SMTP | `587` |
| `EMAIL_HOST_USER` | Usuario SMTP | `sistema@proasepsis.com` |
| `EMAIL_HOST_PASSWORD` | Contraseña SMTP | — |
| `DEFAULT_FROM_EMAIL` | Remitente de correos | `Despacha <sistema@proasepsis.com>` |
| `DRIVE_SERVICE_ACCOUNT_JSON` | Path al JSON de la cuenta de servicio Google | `/secrets/sa.json` |
| `DRIVE_ROOT_FOLDER_ID` | ID de la carpeta raíz en Google Drive | ID del folder |
| `DJANGO_SUPERUSER_USERNAME` | Usuario superadmin (se crea al iniciar el contenedor) | `admin` |
| `DJANGO_SUPERUSER_EMAIL` | Email del superadmin | — |
| `DJANGO_SUPERUSER_PASSWORD` | Contraseña del superadmin | — |

---

## 18. Despliegue con Docker

```bash
# 1. Copiar y configurar variables de entorno
cp .env.example .env
# editar .env con los valores reales

# 2. Levantar los servicios (PostgreSQL + aplicación web)
docker compose up --build

# La aplicación queda disponible en http://localhost:8000

# 3. Comandos útiles dentro del contenedor
docker compose exec web python manage.py migrate          # aplicar migraciones
docker compose exec web python manage.py createsuperuser  # crear admin manualmente
docker compose exec web python manage.py test             # correr pruebas
docker compose exec web python manage.py collectstatic    # recopilar estáticos
```

**Servicios Docker**:
- `db`: PostgreSQL 15
- `web`: Django con Gunicorn

Los archivos estáticos los sirve **WhiteNoise** directamente desde Django (sin nginx).

---

## 19. Pruebas automatizadas

Las pruebas usan `settings_test.py` que configura SQLite en memoria y no requiere servicios externos.

```bash
# Correr todas las pruebas
DJANGO_SETTINGS_MODULE=despacha.settings_test python manage.py test

# Correr un módulo específico
DJANGO_SETTINGS_MODULE=despacha.settings_test python manage.py test cortes.tests.test_procesar

# Correr una prueba específica
DJANGO_SETTINGS_MODULE=despacha.settings_test python manage.py test \
  cortes.tests.test_procesar.ProcesarDocumentosTest.test_lote_se_limpia_al_procesar
```

**Módulos de prueba existentes**:

| Archivo | Qué prueba |
|---|---|
| `core/tests/test_adaptador_plantilla_filtro.py` | Lógica de filtrado y parseo del adaptador PLANTILLA |
| `core/tests/test_auditoria.py` | Registro de auditoría |
| `core/tests/test_lectura_lote_string.py` | Preservación del lote como string |
| `core/tests/test_limpieza_lote.py` | Función `limpiar_lote` con todos sus casos |
| `core/tests/test_notificaciones.py` | Envío de notificaciones por correo |
| `cortes/tests/test_procesar.py` | Servicio `procesar_documentos_internos` |
| `cortes/tests/test_vista_cargar.py` | Vista de carga de cortes |

---

## 20. Cómo extender el sistema

### Agregar un nuevo tipo de comprobante permitido

Editar `CODIGOS_PERMITIDOS` en `core/adaptadores/plantilla/adaptador.py`:

```python
CODIGOS_PERMITIDOS = {"F": 1, "H": 5, "S": 1, "T": 10, "Y": 10}
#                                                          ↑ nuevo tipo
```

### Agregar un nuevo formato de archivo de entrada

1. Crear directorio `core/adaptadores/<nombre_formato>/`.
2. Crear `__init__.py` con una clase que herede de `AdaptadorFormato` y use el decorador `@registrar`.
3. Implementar `validar(ruta)` y `parse(ruta) → list[DocumentoInterno]`.
4. Agregar el formato al campo `formato_origen` en `CargarCorteForm` (choices).

### Agregar un nuevo destino de entrega

1. Crear clase en `core/adaptadores/destinos/` que herede de `AdaptadorDestino`.
2. Implementar `entregar(bytes, nombre, corte) → ResultadoEntrega`.
3. Registrar en el diccionario `DESTINOS_DISPONIBLES` en `destinos/registry.py`.

### Agregar un nuevo parámetro de salida

1. Ir al Admin Django → Parámetros de salida → Agregar.
2. En `generar_archivo.py`, leer el parámetro con `params.get("clave_nueva", "valor_default")`.

### Cambiar los valores del clasificador o prioridad

Los valores disponibles en la interfaz están definidos en `DetalleCorteView.get_context_data`:

```python
"clasificador1_opciones": ["EMBALAR", "NO EMBALAR", "PREGUNTAR"],
"prioridad_opciones": ["PRIORIDAD", "NO PRIORIDAD"],
```

También en el modelo `Documento` si se desea validación a nivel de BD.

---

*Fin del documento. Para preguntas sobre el negocio detrás de las decisiones técnicas, consultar con Sergio Ospitia.*
