# Despacha — Archivo de entrada y salida

## 0. Tipos de comprobante que recibimos (`TIPO DE COMPROBANTE`)

Solo se procesan filas cuyo tipo sea uno de estos 4. Cualquier otra letra
se descarta. Cada tipo exige además un `CÓDIGO COMPROBANTE` específico.

| Tipo | Código comprobante exigido | Débito/Crédito aceptado | Particularidad |
|---|---|---|---|
| `F` | `1` | solo `C` | el más común; documento estándar |
| `H` | `5` | solo `C` | — |
| `S` | `1` | solo `C` | mismo código que `F` (`1`), pero letra distinta |
| `T` | `10` o `25` | `C` **o** `D` | traslados — es el único tipo que acepta ambos lados (débito y crédito); código `25` se sumó luego del `10` original |

Todos, sin excepción, también deben cumplir las reglas generales de fila:
`CUENTA CONTABLE` empieza por `14` y la descripción no contiene la palabra
`TRANSPORTE`.

El código no documenta el significado de negocio de cada letra (`F`, `H`,
`S`) más allá de estas reglas de filtro; si necesitas esa equivalencia
contable, hay que confirmarla con quien definió la plantilla de origen.

## 1. Archivo de entrada

Excel, hoja **`Hoja1`**, encabezados en la **fila 5**. Las 14 columnas de
abajo son obligatorias (búsqueda por nombre, coincidencia parcial); si falta
una, el archivo se rechaza al cargar.

| Campo | Tipo | Ejemplo | Restricción |
|---|---|---|---|
| `NÚMERO DE DOCUMENTO` | texto/número | `FE45231` | obligatorio, fila vacía en esta columna se ignora |
| `TIPO DE COMPROBANTE` | texto (1 letra) | `F` | debe ser `F`, `H`, `S` o `T`; cualquier otro valor se descarta |
| `CÓDIGO COMPROBANTE` | número | `1` | debe coincidir con el tipo: `F→1`, `H→5`, `S→1`, `T→10 o 25` |
| `CUENTA CONTABLE` | texto/número | `1435050001` | debe empezar por `14` |
| `DÉBITO O CRÉDITO` | texto (1 letra) | `C` | debe ser `C`; el tipo `T` (traslado) acepta `C` o `D` |
| `LÍNEA PRODUCTO` | número | `150` | numérico; se rellena a 3 dígitos |
| `GRUPO PRODUCTO` | número | `5` | numérico; se rellena a 4 dígitos |
| `CÓDIGO PRODUCTO` | número | `5` | numérico; se rellena a 6 dígitos |
| `CANTIDAD` | decimal | `12.5` | si no es numérico se toma como `0` |
| `LOTE` | texto | `L2024-08` / `L2024-08.` | ver limpieza abajo |
| `NIT` | texto/número | `900123456-1` | libre, máx. 20 caracteres al guardar |
| `CÓDIGO DE LA CIUDAD` | texto/número | `11001` | debe existir en el catálogo de ciudades para asociar ciudad |
| `DESCRIPCIÓN DE LA SECUENCIA` | texto | `CREMA DE MANOS 200ML` | si contiene la palabra `TRANSPORTE`, la fila entera se descarta |
| `SUCURSAL` | texto/número | `01` | libre, máx. 20 caracteres al guardar |

**Código de producto** (derivado, no es una columna): `LÍNEA(3) + GRUPO(4) +
CÓDIGO(6)` → 13 caracteres. Ejemplo: `150, 5, 5` → `1500005000005`. Debe
existir en el catálogo de productos; si no, la línea queda "sin maestro" y
bloquea la generación del archivo de salida hasta corregirse.

**Limpieza del `LOTE`**, en este orden exacto:
1. Quita comilla inicial (`'`).
2. Corta todo desde el primer `/` en adelante.
3. Quita puntos al inicio.
4. Quita todos los espacios.
5. Si termina en `-` sola, la reemplaza por `-1`.
6. El punto final se conserva tal cual venga (se decide si se muestra o no
   ya en el archivo de salida, columna `lote`).

## 2. Archivo de salida

- Formato: **`.xls`** (Excel 97-2003).
- Nombre: `MMM D corte N.xls`, ej. `SEP 1 corte 2.xls`; desde la versión 2
  agrega sufijo ` (vN)`, ej. `SEP 1 corte 2 (v2).xls`.
- Una **hoja por ciudad** (máx. 31 caracteres por nombre de hoja).
- Una **fila por producto** dentro de cada documento/factura.
- No se genera si queda alguna línea "sin maestro" (producto no cruzado).

### Columnas (orden fijo, 31 en total)

| # | Columna | Ejemplo | Tipo/Origen |
|---|---|---|---|
| 1 | `punto` | `BODEGA PRINCIPAL` | texto fijo (parámetro configurado) |
| 2 | `identificacion` | `900123456` | texto fijo (parámetro configurado) |
| 3 | `nombre` | `MI EMPRESA SAS` | texto fijo (parámetro configurado) |
| 4 | `ciudad` | `BOGOTA` | texto, catálogo de ciudades |
| 5 | `direccion` | `CALLE 10 # 5-20` | texto fijo (parámetro configurado) |
| 6 | `tipo_documento_referencia` | `FE` | texto fijo (parámetro configurado) |
| 7 | `documento_referencia` | `FE45231A` | texto: número de documento + sufijo |
| 8 | `fecha_envio` | *(vacío)* | — |
| 9 | `hora_envio` | *(vacío)* | — |
| 10 | `bodega_alistamiento` | *(vacío)* | — |
| 11 | `sector_alistamiento` | *(vacío)* | — |
| 12 | `area_alistamiento` | *(vacío)* | — |
| 13 | `clasificador1` | `EMBALAR` | texto, máx. 20 |
| 14 | `clasificador2` | `FE45231A` | texto: número de documento + sufijo |
| 15 | `observaciones` | `PRIORIDAD` | texto, máx. 20 |
| 16 | `articulo` | `1500005000005` | texto: código de producto (13 car.) |
| 17 | `lote` | `L2024-08` | texto: lote limpio, con/sin punto final |
| 18 | `estado_articulo` | `BUEN ESTADO` | texto fijo (parámetro configurado) |
| 19 | `sscc` | *(vacío)* | — |
| 20 | `sscc_completo` | *(vacío)* | — |
| 21 | `cantidad` | `24` / `12.50` | número: entero si es exacto, si no 2 decimales |
| 22 | `campo1` | *(vacío)* | — |
| 23 | `campo2` | *(vacío)* | — |
| 24 | `valor` | *(vacío)* | — |
| 25 | `descripcion` | `CREMA DE MANOS 200ML` | texto: descripción del producto |
| 26 | `dato_adicional` | *(vacío)* | — |
| 27 | `zona` | *(vacío)* | — |
| 28 | `prioridad` | *(vacío)* | — |
| 29 | `telefono` | *(vacío)* | — |
| 30 | `email` | *(vacío)* | — |
| 31 | `Proveedor` | *(vacío)* | — |

### Campos estáticos (parámetro configurado)

Estos 6 valores no vienen del archivo de entrada ni cambian por fila: se
configuran una sola vez (panel de administración, `Parámetros de salida`) y
se repiten igual en **todas** las filas de **todos** los cortes hasta que
alguien los cambie.

| Campo | Qué representa | Ejemplo |
|---|---|---|
| `punto` | Punto/bodega de despacho del remitente | `BODEGA PRINCIPAL` |
| `identificacion` | NIT o identificación del remitente (la empresa que despacha) | `900123456` |
| `nombre` | Razón social del remitente | `MI EMPRESA SAS` |
| `direccion` | Dirección del remitente | `CALLE 10 # 5-20` |
| `tipo_documento_referencia` | Tipo de documento que identifica cada envío | `FE` |
| `estado_articulo` | Estado físico del artículo despachado | `BUEN ESTADO` |

Si no hay un parámetro configurado para una clave, la columna sale vacía
(no falla la generación).

### Columnas siempre vacías

Las columnas marcadas `(vacío)` (8–12, 19–20, 22–24, 26–31) pertenecen al
layout fijo de 31 columnas que exige el sistema receptor, pero Despacha no
tiene dato para llenarlas (no aplican al proceso actual) — quedan
reservadas y en blanco en cada fila.
