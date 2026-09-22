# Manual del Administrador — Despacha

> Este manual cubre todos los flujos del sistema desde el rol administrador. El administrador puede hacer todo lo que hacen los roles `facturacion` y `almacenamiento`, más las funciones exclusivas de administración descritas aquí.

---

## Tabla de contenidos

1. [Acceso al sistema](#1-acceso-al-sistema)
2. [Roles y permisos](#2-roles-y-permisos)
3. [Flujo completo de un corte](#3-flujo-completo-de-un-corte)
4. [Liberación forzada de bloqueos](#4-liberación-forzada-de-bloqueos)
5. [Gestión de usuarios (Django Admin)](#5-gestión-de-usuarios-django-admin)
6. [Configuración del sistema](#6-configuración-del-sistema)
7. [Notificaciones por correo](#7-notificaciones-por-correo)
8. [Reglas de clasificación automática](#8-reglas-de-clasificación-automática)
9. [Auditoría](#9-auditoría)
10. [Recursos del servidor](#10-recursos-del-servidor)

---

## 1. Acceso al sistema

Ingrese a la URL del sistema con sus credenciales de administrador.

![Pantalla de login](./imagenes/admin-login.png)

> **Nota:** Si olvidó su contraseña, un superusuario puede restablecerla desde el panel de administración de Django (`/admin/`).

---

## 2. Roles y permisos

El sistema usa grupos de Django para controlar el acceso. Cada usuario debe pertenecer al menos a un grupo.

| Grupo | Puede cargar cortes | Puede editar y generar | Puede forzar liberación | Accede a configuración |
|---|---|---|---|---|
| `facturacion` | ✅ | ❌ | ❌ | ❌ |
| `almacenamiento` | ❌ | ✅ | ❌ | ❌ |
| `admin` | ✅ | ✅ | ✅ | ✅ |

> Un usuario puede pertenecer a varios grupos simultáneamente.

---

## 3. Flujo completo de un corte

### 3.1 Cargar un corte

Navegue al menú **Cargar corte** (disponible para `facturacion` y `admin`).

![Formulario de carga](./imagenes/admin-cargar-form.png)

**Campos del formulario:**

| Campo | Descripción |
|---|---|
| **Archivo** | Archivo `.xls` / `.xlsx` en formato Plantilla. |
| **Fecha** | Fecha del corte de facturación. |
| **Número de corte** | `1` = tarde, `2` = mañana. El sistema sugiere el valor según la hora actual (antes de las 12:00 sugiere 2). |
| **Formato** | Seleccione el formato del archivo. Actualmente solo existe **PLANTILLA**. |
| **Es adicional** | Marque esta casilla si ya existe un corte para esa fecha y número. Se asigna automáticamente una letra (A, B, C…). Máximo 5 adicionales por fecha+número. |

**Errores comunes al cargar:**

- *Archivo duplicado*: el mismo archivo ya fue cargado (detectado por SHA-256). No se permite volver a cargarlo.
- *Combinación fecha+corte ya existe*: use la opción "Es adicional".
- *Error de validación*: el archivo no cumple el formato esperado (encabezados incorrectos, hoja incorrecta).

Después de cargar exitosamente el corte queda en estado **Cargado** y aparece en la lista.

![Lista de cortes tras carga](./imagenes/admin-lista-post-carga.png)

---

### 3.2 Revisar un corte

Haga clic sobre cualquier corte en la lista para abrir la vista de detalle.

![Vista detalle del corte](./imagenes/admin-detalle-corte.png)

#### Bloqueo de edición

Al abrir un corte en estado **En revisión**, el sistema intenta tomar un bloqueo de 30 minutos a su nombre. Si otro usuario ya tiene el bloqueo activo verá un aviso con el nombre del usuario y el tiempo restante.

![Aviso de bloqueo activo](./imagenes/admin-bloqueo-activo.png)

> Como administrador puede **forzar la liberación** del bloqueo (ver sección 4).

#### Presencia en tiempo real

En la parte superior de la vista de detalle aparecen los avatares de los usuarios que están viendo el corte en este momento (actualizados cada 10 segundos).

![Indicador de presencia](./imagenes/admin-presencia.png)

#### Editar campos de un documento

Cada fila de documento tiene campos editables en línea:

| Campo | Descripción |
|---|---|
| **Clasificador 1** | Instrucción de embalaje. Valores típicos: `EMBALAR`, `PREGUNTAR`, `NO EMBALAR`. |
| **Observaciones** | Prioridad u observación libre. |
| **Subsanar novedad** | Indicador de que hay una novedad que resolver. |
| **Sufijo factura** | Letra que se agrega al final del número de factura en el XLS de salida (ej. `A`). |

![Edición en línea de documento](./imagenes/admin-editar-documento.png)

#### Editar cantidad de una línea

Dentro de cada documento puede ajustar la **cantidad de unidades** de cada línea individualmente. Todos los cambios quedan registrados en auditoría.

![Edición de cantidad en línea](./imagenes/admin-editar-linea.png)

#### Líneas sin maestra

Las líneas marcadas en rojo con el indicador **sin maestra** no tienen producto en el catálogo. **No es posible generar un corte que tenga líneas sin maestra.** Debe resolverlas antes de generar:

- Contacte al equipo de productos para agregar el producto al catálogo.
- O inactívelo si no corresponde al despacho.

![Línea sin maestra](./imagenes/admin-sin-maestra.png)

---

### 3.3 Dividir un documento (Split)

Si un documento tiene líneas que deben ir en facturas separadas puede dividirlo:

1. Seleccione las líneas que desea mover a un nuevo documento marcando los checkboxes.
2. Haga clic en **Dividir documento**.
3. El sistema crea un documento nuevo con el sufijo `A` (o `B`, `C`…) en la factura.

![Selección de líneas para split](./imagenes/admin-split-seleccion.png)

![Resultado del split](./imagenes/admin-split-resultado.png)

> El split solo es reversible mientras el corte esté en estado **En revisión**.

#### Deshacer un split

Haga clic en **Deshacer split** en el documento hijo (el que tiene sufijo). Esto mueve las líneas de vuelta al documento original y elimina el documento hijo.

---

### 3.4 Generar el XLS

Cuando todos los documentos están revisados y no hay líneas sin maestra, haga clic en **Generar**.

![Botón generar](./imagenes/admin-boton-generar.png)

El sistema:
1. Valida que no existan líneas `sin_maestro`.
2. Genera el archivo XLS con una hoja por ciudad.
3. Lo entrega a cada destino configurado (descarga directa y/o Google Drive).
4. Incrementa el número de versión del corte.
5. Cambia el estado a **Generado**.
6. Envía notificaciones por correo a los destinatarios configurados.

![Estado generado](./imagenes/admin-estado-generado.png)

> Si el corte ya fue generado antes, el nuevo archivo se llama `MMM D corte N (vN).xls` con el número de versión incrementado.

---

## 4. Liberación forzada de bloqueos

Exclusivo del rol `admin`.

Si un usuario tomó el bloqueo de un corte y no puede liberarlo (cerró el navegador, se fue, etc.):

1. Abra el detalle del corte bloqueado.
2. Haga clic en **Forzar liberación**.
3. El bloqueo se libera inmediatamente y queda registrado en auditoría.

![Forzar liberación](./imagenes/admin-forzar-liberacion.png)

> El bloqueo también expira automáticamente después de **30 minutos** de inactividad, sin necesidad de forzarlo.

---

## 5. Gestión de usuarios (Django Admin)

Acceda a `/admin/` con su cuenta de superusuario.

![Panel Django Admin](./imagenes/admin-django-admin.png)

### Crear un usuario

1. En el panel admin vaya a **Autenticación y autorización → Usuarios → Agregar usuario**.
2. Defina usuario y contraseña.
3. En la pantalla de edición asigne el usuario al grupo correspondiente (`facturacion`, `almacenamiento` o `admin`).

![Asignación de grupos](./imagenes/admin-asignar-grupo.png)

### Cambiar contraseña

En la pantalla de edición del usuario haga clic en **Este formulario de cambio de contraseña**.

### Desactivar un usuario

Desmarque la casilla **Activo** en la pantalla de edición. El usuario no podrá iniciar sesión pero su historial de auditoría se conserva.

---

## 6. Configuración del sistema

Acceda desde el menú **Configuración** (visible solo para `admin`).

![Menú configuración](./imagenes/admin-menu-config.png)

### Parámetros de salida

Son los valores fijos que se imprimen en cada fila del XLS generado. Se configuran en `/admin/core/parametrosalida/`.

| Clave | Descripción | Ejemplo |
|---|---|---|
| `punto` | Punto de venta o bodega | `001` |
| `identificacion` | NIT o cédula de la empresa | `900123456-1` |
| `nombre` | Razón social | `Despacha S.A.S` |
| `direccion` | Dirección física | `Calle 123 # 45-67` |
| `tipo_doc_ref` | Tipo de documento de referencia | `FV` |
| `estado_articulo` | Estado del artículo en el sistema destino | `A` |
| `ciudad_default` | Ciudad cuando la línea no tiene ciudad asignada | `BOGOTA` |

![Parámetros de salida](./imagenes/admin-parametros-salida.png)

---

## 7. Notificaciones por correo

Configure en `/admin/core/notificaciondestinatarios/` los correos que reciben cada tipo de evento.

| Evento | Cuándo se envía |
|---|---|
| `corte_generado` | Al generar un corte por primera vez |
| `corte_regenerado` | Al generar una versión adicional de un corte ya generado |
| `sin_maestro_detectado` | Al cargar un corte que contiene líneas sin producto en el catálogo |

**Formato de correos:** separe las direcciones con comas o saltos de línea.

![Configuración de notificaciones](./imagenes/admin-notificaciones.png)

> En ambiente `staging` el asunto de los correos lleva el prefijo `[STAGING]` para diferenciarlo de producción.

---

## 8. Reglas de clasificación automática

Configure en `/admin/core/reglaclasificacion/`.

Las reglas asignan automáticamente el valor de **Clasificador 1** u **Observaciones** en los documentos al momento de cargar el corte, basándose en condiciones del archivo origen.

| Campo | Descripción |
|---|---|
| **Nombre** | Identificador único de la regla |
| **Campo destino** | `clasificador1` u `observaciones` |
| **Valor por defecto** | Valor que se asigna cuando la regla aplica |
| **Prioridad** | Número menor = mayor prioridad. Se evalúan en orden. |
| **Activa** | Desmarque para deshabilitar sin eliminar |

![Reglas de clasificación](./imagenes/admin-reglas.png)

---

## 9. Auditoría

Acceda desde el menú **Auditoría**.

Registra todas las acciones del sistema: ediciones, generaciones, splits, liberaciones forzadas, intentos de login fallidos y notificaciones fallidas.

![Vista de auditoría](./imagenes/admin-auditoria.png)

### Filtros disponibles

| Filtro | Descripción |
|---|---|
| **Factura / valor** | Busca por número de factura en documentos, o por texto en valores del campo Cambio |
| **Desde / Hasta** | Rango de fechas |
| **Evento** | Tipo de acción: Edición, Creación, Split, etc. |
| **Objeto** | Tipo de entidad: Corte, Documento, Linea, User, etc. |

### Exportar CSV

Haga clic en **↓ Exportar CSV** para descargar todos los registros del filtro actual. El archivo incluye: fecha, usuario, tipo de objeto, ID/factura, campo, valores anterior y nuevo, tipo de evento.

> Los documentos aparecen con su **número de factura** en la columna ID, no con el ID interno.

---

## 10. Recursos del servidor

En la pantalla de **Configuración** (parte inferior) se muestra el estado actual del servidor:

| Indicador | Descripción |
|---|---|
| **Disco** | Uso del disco en el volumen de datos (usado / total) |
| **RAM** | Memoria usada / total del proceso |
| **CPU Load** | Carga promedio en 1, 5 y 15 minutos |

![Panel de recursos](./imagenes/admin-recursos.png)

> Estos valores son informativos. Si el disco supera el 85% de uso contacte al equipo de infraestructura.

---

*Manual generado para Despacha v1 — actualizar ante cambios en el sistema.*
