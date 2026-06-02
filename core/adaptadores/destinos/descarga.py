from .base import AdaptadorDestino, ResultadoEntrega


class AdaptadorDestinoDescarga(AdaptadorDestino):
    codigo = "descarga"
    nombre_mostrar = "Descargar archivo"

    def entregar(self, archivo_bytes, nombre_archivo, corte):
        return ResultadoEntrega(ok=True, referencia=nombre_archivo)
