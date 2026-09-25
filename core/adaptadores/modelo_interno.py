from dataclasses import dataclass, field
from datetime import datetime
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
    sucursal: str = ""
    lineas: list[LineaInterna] = field(default_factory=list)
    # Hora local de Bogotá (sin tz) en que SIIGO registró el documento; None si la fuente no la trae
    actualizado_en: datetime | None = None
