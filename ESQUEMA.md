# Despacha — esquema técnico (solo lo implementado y funcionando)

Django 5.2 + Postgres. Apps: `core`, `cortes` (dominio), `productos`, `clientes`. Propósito: subir spreadsheet de facturación → parsear → cruzar contra maestra de productos/clientes → editar en pantalla → generar XLS de salida por ciudad → entregar (descarga / Google Drive) → notificar por email.

## 1. Modelos

```
Corte(fecha, numero_corte∈{1,2}, adicional_letra="" | A-E, estado∈{cargado,en_revision,generado,con_error},
      version_actual:int, hash_sha256 (dedup), usuario_carga, bloqueado_por, bloqueado_hasta)
  unique(fecha, numero_corte, adicional_letra)
  display_corte -> "Corte {numero}{letra}"

CorteVersion(corte, numero, drive_url, archivo_hash, usuario, motivo)  # historial de generaciones
  unique(corte, numero)

Documento(corte, factura, nit, tipo_comprobante, sucursal, cliente→Cliente(nit) null,
          ciudad→productos.Ciudad null,
          clasificador1 default "EMBALAR", observaciones default "PRIORIDAD",
          subsanar_novedad:bool, factura_sufijo,
          creado_por_split_de→self null)

Linea(documento, referencia, lote, cantidad_origen:Decimal, cantidad_unidades:int,
      sin_maestro:bool, inactivo:bool,
      referencia_snapshot, descripcion_snapshot, unidad_empaque_snapshot,  # copia inmutable al momento del cargue
      movida_desde→Documento null,  # rastro de split
      punto_incluido:bool)
  tiene_punto_final -> lote.endswith(".")

Auditoria(fecha, usuario null, objeto_tipo, objeto_id, campo, valor_anterior, valor_nuevo,
          tipo_evento∈{edicion,regeneracion,split,deshacer_split,forzar_liberacion,creacion,
                       inactivacion,login_fallido,notificacion_fallida}, metadata:JSON)

PresenciaCorte(user, corte, visto_en)  unique(user,corte)  # presencia en tiempo real

# productos app
Producto(producto:13 chars PK, referencia, descripcion, unidad_empaque:int, activo:bool, revisado:bool)
Ciudad(codigo PK, nombre, nombre_archivo, activo)

# clientes app
Cliente(nit PK, sucursal, dv, nombre, tipo, direccion, ciudad, tel_1..4, apartado, clasificacion, forma_pago, dia)

# core app
ParametroSalida(clave PK, valor, descripcion)  # config key-value para el XLS
ReglaClasificacion(nombre, campo_destino∈{clasificador1,observaciones}, valor_por_defecto, activa, prioridad)  # definido, no consumido aún por ningún servicio
NotificacionDestinatarios(evento PK ∈{corte_generado,corte_regenerado,sin_maestro_detectado}, correos:"csv o newline", activo)
```

## 2. Ciclo de vida de un Corte

```
cargar_archivo() → Corte(estado=cargado) → adaptador.validar+parse → procesar_documentos_internos()
                 → estado=en_revision [+ notificar_sin_maestra_detectado si aplica]
[edición manual vía EditarCorteView, split/deshacer_split]
generar_y_entregar() → valida sin_maestro==0 → generar_xls() → entrega a cada destino
                     → version_actual+=1, estado=generado, CorteVersion, auditoría, email
error en cualquier paso → estado=con_error
```

## 3. `cortes/servicios/cargar.py` — `cargar_archivo(archivo, usuario, formato_origen, numero_corte, es_adicional, fecha=None)`

1. `hash_sha256(contenido)` → si existe Corte con ese hash → `ErrorDuplicado`.
2. `fecha = fecha or hoy`.
3. Si NO es_adicional y ya existe `Corte(fecha,numero_corte,adicional_letra="")` → `ErrorSugerirAdicional` (el front ofrece marcar "Es adicional").
4. Si es_adicional: letra = primera libre en "ABCDE" para (fecha,numero_corte); límite 5, si no hay libre → `ErrorCarga`.
5. Crea `Corte(estado="cargado")` (atómico; `IntegrityError` en el constraint único → `ErrorSugerirAdicional`/`ErrorCombinacionFechaCorte`).
6. Escribe el contenido a un archivo temporal, `adaptador.validar(path)`; si falla → borra el Corte creado y lanza `ErrorValidacionAdaptador`.
7. `adaptador.parse(path)` → `list[DocumentoInterno]`.
8. Doble chequeo de colisión de (fecha,numero,letra) tras el parse (por si hubo carrera) → borra y `ErrorCombinacionFechaCorte`.
9. `procesar_documentos_internos(corte, documentos)`; si lanza excepción → `estado=con_error` y re-lanza.
10. `estado=en_revision`; si hubo productos sin maestra → `notificar_sin_maestra_detectado`.

## 4. `cortes/servicios/procesar.py` — `procesar_documentos_internos(corte, documentos: list[DocumentoInterno]) -> ResultadoProcesamiento`

- Resuelve en bulk: `Producto` por código y `Ciudad` por código (1 query cada uno, no N+1).
- `bulk_create` de todos los `Documento`.
- Cruza `nit` normalizado (`re.sub(r"[.\-\s]","",nit)`) contra `Cliente` en bulk → `bulk_update(cliente)`.
- Por cada línea:
  - producto no existe en maestra → `sin_maestro=True`, `referencia=""`, `cantidad_unidades=round(cantidad_origen)`, `unidad_empaque_snapshot=1`, descripción `"(sin maestra) {desc}"` si desc>3 chars, si no `"(producto sin maestra)"`. Se acumula el código en `productos_nuevos_detectados`.
  - producto existe pero `activo=False` → `inactivo=True`, sí se resuelve normal.
  - producto existe y activo → `cantidad_unidades = round(cantidad_origen * producto.unidad_empaque)`, snapshots copiados de Producto.
  - `lote = limpiar_lote(lote_raw)` (ver adaptador plantilla, regla compartida).
- `bulk_create` de todas las líneas.

## 5. Adaptadores de formato — `core/adaptadores/`

Patrón registro: `AdaptadorFormato(ABC)` con `validar(path)`/`parse(path)->list[DocumentoInterno]`. `@registrar` en `registry.py` guarda en dict `{nombre: clase}`; `_descubrir()` importa cada subcarpeta de `core/adaptadores/` una sola vez (lazy, cacheado). `obtener(nombre)` instancia.

Modelo neutro (`modelo_interno.py`):
```
LineaInterna(producto_codigo, lote_raw, cantidad_origen:Decimal, descripcion_origen="")
DocumentoInterno(factura, nit="", codigo_ciudad="", tipo_comprobante="", sucursal="", lineas=[])
```

### `AdaptadorPlantilla` (`core/adaptadores/plantilla/adaptador.py`), nombre="PLANTILLA"

- Requiere hoja `"Hoja1"`, encabezados en fila 5 (búsqueda por *contains*, normalizado a mayúsculas/espacios simples — tolera texto extra en el header).
- Columnas esperadas: NÚMERO DE DOCUMENTO, TIPO DE COMPROBANTE, CÓDIGO COMPROBANTE, CUENTA CONTABLE, DÉBITO O CRÉDITO, LÍNEA/GRUPO/CÓDIGO PRODUCTO, CANTIDAD, LOTE, NIT, CÓDIGO DE LA CIUDAD, DESCRIPCIÓN DE LA SECUENCIA, SUCURSAL.
- Filtro de filas (todas deben cumplirse):
  - `NÚMERO DE DOCUMENTO` no vacío.
  - `"TRANSPORTE"` NO debe estar en la descripción (excluye esas filas).
  - `TIPO DE COMPROBANTE` ∈ {F,H,S,T} y `CÓDIGO COMPROBANTE` (como int) coincide: F→1, H→5, S→1, T→{10,25}.
  - `CUENTA CONTABLE` empieza con `"14"`.
  - `DÉBITO O CRÉDITO=="C"` — excepto tipo T (traslados), que acepta `"C"` o `"D"`.
- `producto_codigo = LÍNEA.zfill(3) + GRUPO.zfill(4) + CÓDIGO.zfill(6)` (13 chars); si alguna parte falta o no es numérica → código = `""` (línea queda sin_maestro).
- Filas se agrupan por `NÚMERO DE DOCUMENTO` → un `DocumentoInterno` por factura, líneas acumuladas.
- `limpiar_lote(lote_raw)` (función pura, `limpieza.py`), en este orden exacto:
  1. quitar comilla inicial (`'`)
  2. cortar todo desde `/` inclusive
  3. quitar puntos al inicio (`lstrip(".")`)
  4. quitar todos los espacios
  5. si termina solo en `-` (y len>1) → agregar `"1"` (`-` → `-1`)
  6. el punto final NO se toca (se conserva; se resuelve al generar el XLS vía `punto_incluido`).

Para agregar un formato nuevo: carpeta `core/adaptadores/<nombre>/__init__.py` que instancia y decora con `@registrar` una clase `AdaptadorFormato`.

## 6. Adaptadores de destino — `core/adaptadores/destinos/`

Registro estático (dict, no auto-discovery): `DESTINOS_DISPONIBLES = {"descarga": AdaptadorDestinoDescarga, "drive": AdaptadorDestinoDrive}`.
Interfaz: `AdaptadorDestino.entregar(bytes, nombre_archivo, corte) -> ResultadoEntrega(ok, referencia, error)`.

- **descarga**: no-op, devuelve `ok=True` con el nombre como referencia (el bytes real lo sirve la vista).
- **drive**: service account (`DRIVE_SERVICE_ACCOUNT_JSON` env → path a JSON, `DRIVE_ROOT_FOLDER_ID`). Servicio cacheado en dict global por path. Estructura de carpetas `ROOT/MES_NOMBRE/DÍA` (busca por query `name=... and mimeType=folder and parent=...`, crea si no existe). Sube con `MediaInMemoryUpload`, mimetype `application/vnd.ms-excel`. Reintenta 3 veces con backoff `[1,3,10]` segundos; al 3er fallo devuelve `ok=False` con el error. Si no hay service account configurado → `ok=False` sin intentar.

## 7. `cortes/servicios/generar.py` — `generar_y_entregar(corte, destinos:list[str], usuario, motivo="") -> dict`

- `corte.refresh_from_db()`.
- Bloquea si hay alguna `Linea(sin_maestro=True)` en el corte → `ValueError`.
- Valida que `destinos` no esté vacío y que cada clave exista en `DESTINOS_DISPONIBLES`.
- `generar_xls(corte)` → bytes; nombre = `nombre_archivo_corte(corte, version_actual+1)`.
- Entrega a cada destino, acumula resultados; si CUALQUIERA falla → `estado=con_error`, devuelve `success=False` (no incrementa versión, no notifica).
- Si todos ok → `version_actual+=1`, `estado=generado`, crea `CorteVersion` (guarda `drive_url` si vino de destino "drive"), registra auditoría (`creacion` si v1, si no `regeneracion`), envía `notificar_corte_generado` (v1) o `notificar_corte_regenerado` (v>1).

## 8. `cortes/servicios/generar_archivo.py` — `generar_xls(corte) -> bytes` (xlwt, formato .xls binario)

- Una hoja por `Ciudad.nombre_archivo` (fallback: `ParametroSalida["ciudad_default"]` si el documento no tiene ciudad asignada). Nombre de hoja truncado a 31 chars (límite de Excel).
- Cada fila = un par `(Documento, Linea)`. 31 columnas fijas, ver lista `COLUMNAS` en el archivo. Valores estáticos (`punto`, `identificacion`, `nombre`, `direccion`, `tipo_doc_ref`, `estado_articulo`) vienen de `ParametroSalida` (key-value, admin de Django).
- `documento_referencia = clasificador2 = factura + factura_sufijo`.
- `articulo = referencia_snapshot`, `descripcion = descripcion_snapshot`.
- `lote`: si `tiene_punto_final and not punto_incluido` → se quita el punto final al escribir (`rstrip(".")`); si `punto_incluido=True` se deja tal cual.
- `cantidad`: entero si es entero exacto, si no con 2 decimales (`_cantidad_a_str`).

`nombre_archivo_corte(corte, version=None)` (`nombrado.py`): `"{MES_ABREV} {día} corte {numero}"` + `" (vN)"` si versión>1, + `.xls`.

## 9. Bloqueo optimista — `cortes/servicios/bloqueo.py`

- `intentar_tomar_bloqueo(corte, usuario)`: éxito si libre, si expiró (`bloqueado_hasta < now`), o si ya lo tiene el mismo usuario. Fija `bloqueado_hasta = now + 30min`.
- `refrescar_bloqueo`: solo si el usuario actual es el dueño y no expiró; extiende 30min.
- `liberar_bloqueo(forzado_por_admin=False)`: limpia `bloqueado_por/hasta`; si `forzado_por_admin` registra auditoría `forzar_liberacion`.
- `info_bloqueo`: si expiró, lo limpia lazy (side-effect) y devuelve `None`; si vigente, devuelve `{usuario, usuario_id, desde, hasta}`.

## 10. Split de documento — `cortes/servicios/split.py`

- `partir_documento(doc_origen, lineas_ids, usuario)`: solo si `corte.estado=="en_revision"`. Verifica que todas las líneas pertenezcan al documento origen. Sufijo siguiente: primera letra libre A-Z tal que `factura+letra` no exista ya en ese corte. Crea `Documento` hijo (copia nit/tipo/sucursal/cliente/ciudad/clasificador1/observaciones, `creado_por_split_de=origen`). Mueve las líneas (`movida_desde=origen`, `documento=nuevo`) vía update masivo. Auditoría `split`.
- `deshacer_split(doc_nuevo, usuario)`: solo si `corte.estado=="en_revision"` y el doc tiene `creado_por_split_de`. Devuelve las líneas al original (`movida_desde=None`), borra el documento hijo. Auditoría `deshacer_split`.

## 11. Vistas y permisos (`cortes/views.py`)

Grupos Django: `facturacion` (cargar), `almacenamiento` (editar/generar/split), `admin` (todo + forzar liberación), `consultar` (solo lectura de auditoría, ver `core/views.py::EsAdminOConsultarMixin`).

- `ListaCortesView`: filtros por `q` (factura/nit icontains), `estado`, `usuario`, rango de fechas; sin filtros muestra últimos 30 días. Agrupa resultados por fecha→numero_corte para el template.
- `CargarCorteView` (grupo facturacion/admin): GET sugiere corte vía `sugerir_corte()`; POST llama `cargar_archivo`, maneja cada excepción de `cargar.py` con su propio render/redirect (`ErrorSugerirAdicional` re-renderiza con `sugerir_adicional=True` para que el usuario marque el checkbox).
- `DetalleCorteView`: serializa documentos+líneas a dict para el template/JS; calcula `es_editor` según grupos.
- `EditarCorteView` (grupo almacenamiento/admin), autosave por PATCH-like POST JSON `{tipo, id, campo, valor}`:
  - `tipo=documento`: campos editables `clasificador1, observaciones, subsanar_novedad, factura_sufijo`. `factura_sufijo` solo editable si `subsanar_novedad=True`; al desactivar `subsanar_novedad` se limpia el sufijo. `factura_sufijo` se guarda en mayúsculas.
  - `tipo=linea`: campos editables `cantidad_unidades` (>0, se redondea a entero), `punto_incluido` (bool).
  - Toda edición → `registrar_auditoria(tipo_evento="edicion")`.
- `SplitDocumentoView` / `DeshacerSplitView`: envuelven los servicios de split, devuelven JSON.
- `ForzarLiberacionView` (solo admin): libera el lock de otro usuario.
- `GenerarCorteView` (grupo almacenamiento/admin): `destinos` = lista de POST, `motivo` opcional; si "descarga" está entre los destinos y salió ok, la respuesta HTTP es directamente el archivo (`Content-Disposition: attachment`) en vez de JSON.
- `PresenciaPingView`: POST = upsert `PresenciaCorte.visto_en=now`; GET = purga presencias con `visto_en` < 25s y devuelve lista de usuarios activos con iniciales.
- `LogoutView`: POST-only, redirige a `admin:login`.

URLs (`cortes/urls.py`): `/`, `/cargar/`, `/<pk>/`, `/<pk>/editar/`, `/<pk>/split/`, `/<pk>/deshacer-split/`, `/<pk>/forzar-liberacion/`, `/<pk>/generar/`, `/<pk>/presencia/`, `/salir/`. Raíz del proyecto redirige a `lista_cortes`; `/admin-auditoria/` monta `core.urls`.

## 12. Auditoría y señales

- `core/servicios/auditoria.py::registrar(usuario, objeto_tipo, objeto_id, tipo_evento, campo="", valor_anterior=None, valor_nuevo=None, metadata=None)` — todo se castea a `str()`. `cortes/servicios/auditoria.py` re-exporta como `registrar_auditoria` (shim de compatibilidad).
- `cortes/signals`: `user_login_failed` → audita `login_fallido` con `{ip}` (respeta `X-Forwarded-For`).
- `productos/signals`: `post_save(Producto)` audita cambios de `unidad_empaque`/`activo` comparando contra `_pre_save_*` (atributo puesto en algún punto no visto aquí, probablemente en un `pre_save` o en el admin); `post_delete` audita `inactivacion`.
- `core/views.py::AuditoriaListView` (admin/consultar): filtros por texto (incluye búsqueda de factura → mapea a `objeto_id` de Documento), tipo_evento, objeto_tipo, usuario, rango de fecha; exporta CSV con `?export=csv`.
- `core/views.py::PanelConfigView` (solo admin): panel de solo-lectura con estado de Drive/SMTP/DEBUG/entorno y métricas de disco/RAM/load del servidor.

## 13. Notificaciones (`core/servicios/notificaciones.py`)

- Destinatarios por evento en `NotificacionDestinatarios.correos` (separados por coma o salto de línea), solo si `activo=True`.
- Asunto con prefijo `"[STAGING] "` si `ENVIRONMENT=staging`.
- `DEBUG=True` → backend consola; en tests, locmem (config Django estándar).
- Falla de envío → log + `registrar(tipo_evento="notificacion_fallida")`, no relanza (best-effort).
- Eventos: `notificar_corte_generado`, `notificar_corte_regenerado` (incluye motivo si existe), `notificar_sin_maestra_detectado` (lista de códigos sin maestra).

## 14. Comandos de importación (maestras externas)

- `python manage.py importar_productos <archivo.tsv> [--desde-interfase]`: TSV sin header real (salta líneas que empiecen con "PRODUCTO"), columnas `[codigo, descripcion, referencia, _, _, _, unidad_empaque]`. `codigo` debe ser 13 dígitos. `update_or_create` por `producto`; con `--desde-interfase` los nuevos quedan `revisado=False` (refresco masivo) y existentes se marcan `revisado=True`.
- `python manage.py importar_clientes <archivo.csv>`: CSV `;`-delimitado, salta encabezado, ≥16 columnas, `nit` normalizado igual que en `procesar.py` (`re.sub(r"[.\-\s]","",nit)`). `update_or_create` por `nit`.

## 15. Config / entorno relevante (solo lo que el código lee)

`SECRET_KEY` (obligatorio), `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `DB_*`, `ENVIRONMENT` (production|staging), `EMAIL_HOST_USER/PASSWORD/HOST/PORT/USE_TLS`, `DEFAULT_FROM_EMAIL`, `DRIVE_SERVICE_ACCOUNT_JSON`, `DRIVE_ROOT_FOLDER_ID`. `TIME_ZONE=America/Bogota`, `SESSION_COOKIE_AGE=8h`. Login vía `django.contrib.admin` (`LOGIN_URL=/admin/login/`), no hay vista de login propia.

## 16. Nota — código no consumido

`ReglaClasificacion` existe como modelo/admin pero ningún servicio la lee todavía (los defaults `"EMBALAR"`/`"PRIORIDAD"` están hardcodeados en `Documento`). Si se replica este sistema, decidir si esa tabla se conecta a `procesar.py` o se elimina.
