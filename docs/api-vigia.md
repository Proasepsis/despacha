# API Vigia

API HTTPS de solo lectura para consultar cortes generados y sus datos finales.
No expone ingestas SIIGO crudas ni cortes pendientes de revision.

## Endpoints

Produccion:

```text
GET https://despacha.proasepsis.com.co/api/v1/vigia/cortes
GET https://despacha.proasepsis.com.co/api/v1/vigia/cortes/{id}
GET https://despacha.proasepsis.com.co/api/v1/vigia/documentos
```

Staging desde el laboratorio:

```text
GET https://despacha.proasepsis.com.co/api/v1/vigia-staging/cortes
GET https://despacha.proasepsis.com.co/api/v1/vigia-staging/cortes/{id}
GET https://despacha.proasepsis.com.co/api/v1/vigia-staging/documentos
```

## Autenticacion

Cada consumidor recibe un token diferente. El token se muestra una sola vez y
Despacha conserva unicamente su hash SHA-256.

```http
Authorization: Bearer vigia_<identificador>_<secreto>
```

Nunca envie el token en la URL, archivos de codigo, tickets o mensajes. Guardelo
en un gestor de secretos. Para crear una credencial:

```bash
docker exec despacha-web-1 python manage.py crear_credencial_vigia api-vigia
```

Para limitarla a una IP o red y para rotarla:

```bash
docker exec despacha-web-1 python manage.py crear_credencial_vigia \
  api-vigia --rotar --ip 203.0.113.10/32
```

## Listar cortes

```bash
curl --fail --silent \
  -H "Authorization: Bearer $VIGIA_API_TOKEN" \
  "https://despacha.proasepsis.com.co/api/v1/vigia/cortes?actualizado_desde=2026-09-22T00:00:00Z&page_size=50"
```

Filtros opcionales:

- `fecha_desde` y `fecha_hasta`: `YYYY-MM-DD`.
- `actualizado_desde`: fecha y hora ISO-8601 para sincronizacion incremental.
  El sistema actualiza este campo al generar, regenerar o editar un corte, por
  lo que una consulta incremental no omite cambios publicados.
- `page_size`: entre 1 y 100; predeterminado 50.
- `cursor`: valor opaco entregado en `next_cursor`.

Sin filtros se retornan los ultimos 30 dias. Si `has_more` es `true`, repita la
consulta con el mismo filtro y `cursor=<next_cursor>`.

## Documentos del dia

Entrega todos los documentos (facturas, remisiones, traslados u otros
comprobantes) de los cortes generados de un dia, cada uno con sus lineas
completas y los datos del corte al que pertenecen.

```bash
curl --fail --silent \
  -H "Authorization: Bearer $VIGIA_API_TOKEN" \
  "https://despacha.proasepsis.com.co/api/v1/vigia/documentos?fecha=2026-08-25&page_size=50"
```

Parametros:

- `fecha`: `YYYY-MM-DD`. Sin este parametro se usa el dia actual de Bogota.
- `tipo`: opcional; filtra por tipo de comprobante (`F`, `S`, `T`, `H`).
- `page_size`: entre 1 y 500; predeterminado 200.
- `documento_cursor`: valor opaco entregado en `next_cursor`.

Cada documento incluye `factura`, `tipo_comprobante`, `nit`, `sucursal`,
`ciudad`, el bloque `corte` (id, numero, version) y sus `lineas` con los
campos finales Vigia. Si `has_more` es `true`, repita la consulta con el
mismo filtro y `documento_cursor=<next_cursor>`.

## Consultar un corte

```bash
curl --fail --silent \
  -H "Authorization: Bearer $VIGIA_API_TOKEN" \
  https://despacha.proasepsis.com.co/api/v1/vigia/cortes/277
```

La respuesta contiene documentos y lineas. Cada linea incluye exactamente los
campos finales utilizados para generar el archivo Vigia: `articulo`, `lote`,
`cantidad`, clasificadores, punto, ciudad y demas columnas de salida.

Los documentos se pagan internamente para acotar la respuesta:

- `page_size`: documentos por pagina; entre 1 y 500, predeterminado 200.
- `documento_cursor`: valor opaco entregado en `documentos_next_cursor`.

Si `documentos_has_more` es `true`, repita la consulta con el mismo
`page_size` y `documento_cursor=<documentos_next_cursor>`.

El endpoint retorna `ETag`. En consultas posteriores puede enviar
`If-None-Match`; si el corte no cambio recibira `304 Not Modified` sin cuerpo.

## Consumo desde herramientas

### Python (requests)

```python
import os
import requests

session = requests.Session()
session.headers["Authorization"] = f"Bearer {os.environ['VIGIA_API_TOKEN']}"

response = session.get(
    "https://despacha.proasepsis.com.co/api/v1/vigia/cortes",
    params={"actualizado_desde": "2026-09-22T00:00:00Z"},
    timeout=30,
)
response.raise_for_status()

base_url = "https://despacha.proasepsis.com.co"
for corte in response.json()["results"]:
    detail = session.get(base_url + corte["path"], timeout=30)
    detail.raise_for_status()
    procesar(detail.json()["data"])
```

### Documentos del dia con paginacion

```python
import os
import requests

token = os.environ["VIGIA_API_TOKEN"]
headers = {"Authorization": f"Bearer {token}"}
base = "https://despacha.proasepsis.com.co/api/v1/vigia"
params = {"fecha": "2026-08-25", "page_size": 100}

while True:
    response = requests.get(f"{base}/documentos", headers=headers, params=params, timeout=30)
    response.raise_for_status()
    body = response.json()
    for documento in body["documentos"]:
        procesar(documento)  # documento incluye corte, nit, tipo y lineas
    if not body["has_more"]:
        break
    params["documento_cursor"] = body["next_cursor"]
```

### Jupyter

```python
%pip install requests python-dotenv
```

```python
import os
import requests
from dotenv import load_dotenv

load_dotenv()  # guarde VIGIA_API_TOKEN en un archivo .env local
headers = {"Authorization": f"Bearer {os.environ['VIGIA_API_TOKEN']}"}

payload = requests.get(
    "https://despacha.proasepsis.com.co/api/v1/vigia/documentos",
    headers=headers,
    params={"fecha": "2026-08-25"},
    timeout=30,
).json()

payload["documentos"][0].keys()
```

### VSCode con REST Client

1. Instale la extension `humao.rest-client`.
2. Cree el archivo `docs/rest/api-vigia.http` incluido en el repositorio.
3. Defina el token en las variables del archivo y pulse `Send Request` sobre
   cada bloque; la respuesta aparece en el panel lateral.

### PyCharm (HTTP Client)

1. Abra el mismo archivo `docs/rest/api-vigia.http`.
2. PyCharm lo reconoce como `HTTP Request`; defina el token en `{{token}}`.
3. Pulse el icono verde de ejecucion junto a cada peticion.

### Postman

1. Importe `docs/postman/api-vigia.postman_collection.json`.
2. Pegue el token en la variable `token` de la coleccion.
3. Las peticiones `Documentos del dia`, `Listar cortes` y `Detalle` quedan listas.

## Codigos HTTP

- `200`: consulta correcta.
- `304`: recurso sin cambios al usar `If-None-Match`.
- `400`: filtro o cursor invalido.
- `401`: token ausente, revocado o incorrecto.
- `403`: IP no autorizada para esa credencial.
- `404`: corte inexistente o todavia no generado.
- `405`: metodo diferente de `GET`.
- `429`: limite de solicitudes excedido (nginx permite 10 por segundo por token, con rafaga de 20).
- `500`: error interno; reintente con espera exponencial.

## Rotacion

1. Cree una credencial nueva o rote la existente.
2. Actualice el secreto en api-vigia.
3. Verifique una consulta exitosa.
4. Desactive la credencial anterior desde el administrador de Despacha.
