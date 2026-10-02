import os
import time
from xml.sax.saxutils import escape, quoteattr

import requests

from cortes.servicios.generar_archivo import COLUMNAS, cargar_parametros_salida, construir_fila_salida

from .base import AdaptadorDestino, ResultadoEntrega


# ponytail: sobre SOAP 1.1 armado a mano con el mismo contenido del XLS (una <Fila> por línea).
# Cuando llegue el WSDL del cliente, ajustar _armar_sobre a su esquema (o pasar a zeep si es complejo).
def _armar_sobre(corte, nombre_archivo: str, namespace: str, operacion: str) -> str:
    params = cargar_parametros_salida()
    filas = []
    for doc in corte.documentos.select_related("ciudad").prefetch_related("lineas"):
        for linea in doc.lineas.all():
            valores = construir_fila_salida(doc, linea, params)
            campos = "".join(f"<{c}>{escape(str(valores.get(c, '')))}</{c}>" for c in COLUMNAS)
            filas.append(f"<Fila>{campos}</Fila>")

    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
        "<soap:Body>"
        f"<{operacion} xmlns={quoteattr(namespace)}>"
        f"<Corte fecha=\"{corte.fecha.isoformat()}\" numero=\"{corte.numero_corte}\""
        f" adicional={quoteattr(corte.adicional_letra)} version=\"{corte.version_actual + 1}\""
        f" archivo={quoteattr(nombre_archivo)}>"
        f"{''.join(filas)}"
        "</Corte>"
        f"</{operacion}>"
        "</soap:Body>"
        "</soap:Envelope>"
    )


class AdaptadorDestinoSoap(AdaptadorDestino):
    codigo = "soap"
    nombre_mostrar = "Enviar a Web Service SOAP"

    def __init__(self):
        self.url = os.environ.get("SOAP_URL", "")
        self.action = os.environ.get("SOAP_ACTION", "")
        self.namespace = os.environ.get("SOAP_NAMESPACE", "")
        self.operacion = os.environ.get("SOAP_OPERACION", "RecibirCorte")
        usuario = os.environ.get("SOAP_USUARIO", "")
        self.auth = (usuario, os.environ.get("SOAP_PASSWORD", "")) if usuario else None

    def entregar(self, archivo_bytes, nombre_archivo, corte):
        if not self.url:
            return ResultadoEntrega(ok=False, error="SOAP no configurado (SOAP_URL)")

        sobre = _armar_sobre(corte, nombre_archivo, self.namespace, self.operacion)
        headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": f'"{self.action}"'}

        for intento, espera in enumerate([1, 3, 10], start=1):
            try:
                resp = requests.post(
                    self.url, data=sobre.encode("utf-8"), headers=headers,
                    auth=self.auth, timeout=30,
                )
                # Un soap:Fault llega con HTTP 500: no se reintenta, el servicio rechazó el contenido.
                if "Fault>" in resp.text:
                    return ResultadoEntrega(ok=False, error=f"SOAP Fault: {resp.text[:500]}")
                resp.raise_for_status()
                return ResultadoEntrega(ok=True, referencia=nombre_archivo)
            except requests.RequestException as e:
                if intento == 3:
                    return ResultadoEntrega(
                        ok=False, error=f"Fallo al enviar a SOAP tras 3 intentos: {e}"
                    )
                time.sleep(espera)

        return ResultadoEntrega(ok=False, error="Error inesperado")
