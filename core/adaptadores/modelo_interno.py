from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class LineaInterna:
    producto_codigo: str
    lote_raw: str
    cantidad_origen: Decimal
    descripcion_origen: str = ""


@dataclass
class DocumentoInterno:
    factura: str
    nit: str = ""
    codigo_ciudad: str = ""
    tipo_comprobante: str = ""
    lineas: list[LineaInterna] = field(default_factory=list)
