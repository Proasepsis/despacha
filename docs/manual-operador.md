# Manual del Operador — Despacha

> Este manual está dirigido a los usuarios con rol **`facturacion`** (cargan archivos) y **`almacenamiento`** (revisan y generan cortes). Si usted tiene ambos roles puede realizar todos los flujos descritos aquí.

---

## Tabla de contenidos

1. [Acceso al sistema](#1-acceso-al-sistema)
2. [Qué puede hacer según su rol](#2-qué-puede-hacer-según-su-rol)
3. [La lista de cortes](#3-la-lista-de-cortes)
4. [Flujo Facturación: cargar un corte](#4-flujo-facturación-cargar-un-corte)
5. [Flujo Almacenamiento: revisar un corte](#5-flujo-almacenamiento-revisar-un-corte)
6. [Flujo Almacenamiento: dividir un documento](#6-flujo-almacenamiento-dividir-un-documento)
7. [Flujo Almacenamiento: generar el XLS](#7-flujo-almacenamiento-generar-el-xls)
8. [Estados de un corte](#8-estados-de-un-corte)
9. [Preguntas frecuentes](#9-preguntas-frecuentes)

---

## 1. Acceso al sistema

Ingrese a la URL del sistema con el usuario y contraseña que le asignó el administrador.

![Pantalla de inicio de sesión](./imagenes/op-login.png)

> Si su cuenta no tiene acceso a alguna función, verá el mensaje *"No tienes permiso para realizar esta acción"*. Contacte al administrador para revisar su rol.

---

## 2. Qué puede hacer según su rol

| Acción | `facturacion` | `almacenamiento` |
|---|---|---|
| Ver la lista de cortes | ✅ | ✅ |
| Ver el detalle de un corte | ✅ | ✅ |
| **Cargar un archivo** | ✅ | ❌ |
| Editar documentos y líneas | ❌ | ✅ |
| Dividir / deshacer división | ❌ | ✅ |
| **Generar el XLS** | ❌ | ✅ |

---

## 3. La lista de cortes

Al iniciar sesión verá la lista de todos los cortes ordenados por fecha.

![Lista de cortes](./imagenes/op-lista-cortes.png)

**Columnas:**

| Columna | Descripción |
|---|---|
| **Fecha** | Fecha del corte de facturación |
| **Corte** | `1` (tarde) o `2` (mañana). Las letras A, B, C… indican cortes adicionales. |
| **Estado** | Ver sección [8. Estados](#8-estados-de-un-corte) |
| **Documentos** | Cantidad de facturas en el corte |
| **Líneas** | Total de líneas de producto |
| **Sin maestra** | Líneas sin producto en el catálogo (en rojo si hay alguna) |
| **Versión** | Número de veces que se ha generado el XLS |
| **Cargado por** | Usuario que subió el archivo |

**Filtros disponibles:**

Puede filtrar la lista por estado, número de corte o rango de fechas usando la barra de filtros en la parte superior.

![Filtros lista de cortes](./imagenes/op-filtros-lista.png)

---

## 4. Flujo Facturación: cargar un corte

> **Requiere rol:** `facturacion`

### Paso 1 — Ir a "Cargar corte"

Haga clic en el botón **+ Cargar corte** en la lista o en el menú principal.

![Botón cargar corte](./imagenes/op-boton-cargar.png)

### Paso 2 — Completar el formulario

![Formulario de carga](./imagenes/op-form-carga.png)

| Campo | Qué ingresar |
|---|---|
| **Archivo** | Seleccione el archivo `.xls` o `.xlsx` recibido. Debe estar en el formato Plantilla. |
| **Fecha** | Fecha del corte. |
| **Número de corte** | El sistema sugiere automáticamente: **2** si es antes de las 12:00, **1** si es después. Puede cambiarlo si es necesario. |
| **Formato** | Deje la opción por defecto (PLANTILLA). |
| **Es adicional** | Solo marque esta casilla si el administrador le indica que debe cargar un corte adicional para una fecha y número que ya existe. |

### Paso 3 — Enviar

Haga clic en **Cargar**. Si todo está bien el sistema lo lleva a la lista de cortes donde verá el nuevo corte en estado **En revisión**.

![Corte recién cargado](./imagenes/op-corte-cargado.png)

### ¿Qué pasa si hay un error?

| Mensaje de error | Qué significa | Qué hacer |
|---|---|---|
| *"Este archivo ya fue cargado"* | El mismo archivo se subió antes | Verifique que es el archivo correcto |
| *"Ya existe un corte para esta fecha y número"* | Ya hay un corte con esa combinación | Marque "Es adicional" o verifique la fecha/número |
| *"El archivo no es válido"* | El archivo no tiene el formato esperado | Revise que el archivo viene de la fuente correcta |

> Después de cargar, si el sistema detecta productos sin maestra, enviará automáticamente un correo de alerta al equipo de productos.

---

## 5. Flujo Almacenamiento: revisar un corte

> **Requiere rol:** `almacenamiento`

### Paso 1 — Abrir el corte

En la lista haga clic sobre el corte que desea revisar. El estado debe ser **En revisión**.

![Clic en corte para revisar](./imagenes/op-abrir-corte.png)

### Paso 2 — Tomar el bloqueo

Al abrir el corte, el sistema le asigna automáticamente un **bloqueo de edición** por 30 minutos. Esto evita que otro usuario edite al mismo tiempo.

![Indicador de bloqueo propio](./imagenes/op-bloqueo-propio.png)

> Si otro usuario ya tiene el bloqueo verá un aviso con su nombre. Solo puede ver el corte, no editarlo. Espere a que expire (máximo 30 min) o pida al administrador que lo libere.

![Aviso bloqueo de otro usuario](./imagenes/op-bloqueo-otro.png)

> **Presencia:** en la parte superior puede ver qué otros usuarios están viendo el mismo corte en este momento.

### Paso 3 — Revisar los documentos

La vista de detalle muestra una lista de documentos (facturas). Cada documento tiene sus líneas de producto desplegadas.

![Vista detalle con documentos](./imagenes/op-detalle-documentos.png)

#### Editar campos del documento

Haga clic en el campo que desea cambiar para editarlo en línea:

| Campo | Valores comunes |
|---|---|
| **Clasificador 1** | `EMBALAR`, `PREGUNTAR`, `NO EMBALAR` |
| **Observaciones** | Texto libre de prioridad u observación |
| **Subsanar novedad** | Marque si hay una novedad que resolver |
| **Sufijo factura** | Una letra que se suma al número de factura en el archivo XLS (ej. `A` → factura `58594A`) |

![Edición de campo en documento](./imagenes/op-editar-campo.png)

Presione **Enter** o haga clic fuera del campo para guardar. El cambio queda registrado en auditoría.

#### Editar cantidad de una línea

Dentro de cada documento puede ajustar la **cantidad de unidades** de cada línea:

1. Haga clic en el número de la cantidad.
2. Ingrese el nuevo valor.
3. Presione **Enter** para guardar.

![Edición de cantidad en línea](./imagenes/op-editar-cantidad.png)

#### Líneas sin maestra (en rojo)

Las líneas marcadas como **sin maestra** no tienen producto en el catálogo. El corte **no se puede generar** mientras existan estas líneas.

![Línea sin maestra](./imagenes/op-sin-maestra.png)

> Informe al administrador o al equipo de productos para que agreguen el producto. Una vez agregado debe recargar la página para ver si la línea se resolvió.

---

## 6. Flujo Almacenamiento: dividir un documento

> **Requiere rol:** `almacenamiento` | Solo disponible en estado **En revisión**

Use esta función cuando las líneas de un documento deben ir en facturas separadas en el XLS de salida.

### Paso 1 — Seleccionar líneas

Dentro del documento marque los checkboxes de las líneas que desea separar.

![Selección de líneas para dividir](./imagenes/op-split-seleccion.png)

### Paso 2 — Dividir

Haga clic en **Dividir documento**. El sistema crea un nuevo documento con la misma factura más una letra (`A`, `B`, etc.).

![Documento hijo creado](./imagenes/op-split-resultado.png)

### Deshacer la división

Si se equivocó, haga clic en **Deshacer split** en el documento hijo (el que tiene la letra en la factura). Las líneas vuelven al documento original y el documento hijo se elimina.

> Solo puede deshacer mientras el corte está en estado **En revisión**.

---

## 7. Flujo Almacenamiento: generar el XLS

> **Requiere rol:** `almacenamiento`

### Antes de generar, verifique:

- [ ] No hay líneas marcadas como **sin maestra** (se muestran en rojo).
- [ ] Los campos de todos los documentos están correctamente revisados.
- [ ] Las cantidades de las líneas son correctas.

### Paso 1 — Hacer clic en Generar

En la vista de detalle del corte haga clic en el botón **Generar**.

![Botón Generar](./imagenes/op-boton-generar.png)

### Paso 2 — Confirmar

El sistema le pedirá confirmación. Haga clic en **Confirmar** para continuar.

### Paso 3 — Descarga automática

Si el destino configurado incluye descarga directa, el navegador descargará automáticamente el archivo XLS.

![Descarga del archivo](./imagenes/op-descarga.png)

El nombre del archivo tiene el formato: `MMM D corte N.xls`
(ej. `Jun 17 corte 2.xls`). Si ya se generó antes: `Jun 17 corte 2 (v2).xls`.

### Después de generar

- El corte pasa al estado **Generado**.
- Se incrementa el número de versión.
- Se envía un correo automático a los destinatarios configurados.
- El archivo también se sube a Google Drive si está configurado.

![Corte en estado generado](./imagenes/op-estado-generado.png)

> **¿Necesita volver a generar?** Puede volver a generar un corte ya generado si hay correcciones. El sistema crea una nueva versión del archivo. El estado vuelve a **Generado** con versión incrementada.

---

## 8. Estados de un corte

| Estado | Color | Qué significa |
|---|---|---|
| **Cargado** | Gris | El archivo fue subido pero aún no procesado completamente |
| **En revisión** | Amarillo | Listo para revisar y editar |
| **Generado** | Verde | El XLS fue generado exitosamente |
| **Con error** | Rojo | Ocurrió un error durante la carga o generación. Contacte al administrador. |

---

## 9. Preguntas frecuentes

**¿Por qué no puedo editar el corte si tengo rol almacenamiento?**
Otro usuario tiene el bloqueo activo. Verá su nombre y el tiempo restante. Espere a que expire o pida al administrador que fuerce la liberación.

**¿Por qué no aparece el botón "Generar"?**
Verifique que el corte está en estado **En revisión** y que su usuario tiene rol `almacenamiento` o `admin`. Si hay líneas sin maestra el botón puede estar deshabilitado.

**Cargué el archivo equivocado, ¿puedo borrarlo?**
No es posible borrar cortes desde la interfaz. Contacte al administrador.

**¿Qué es el "sufijo de factura"?**
Es una letra que se concatena al número de factura en el XLS de salida. Se usa cuando una factura necesita identificarse con un código adicional en el sistema de destino.

**¿Dónde queda el archivo generado?**
En el navegador (descarga directa) y/o en la carpeta de Google Drive configurada por el administrador, organizada por mes y día.

**¿Puedo ver quién hizo un cambio?**
Los administradores tienen acceso a la **Auditoría** donde se registra cada cambio con usuario, fecha y valor anterior/nuevo. Si necesita consultar un cambio pida al administrador que lo revise.

---

*Manual generado para Despacha v1 — actualizar ante cambios en el sistema.*
