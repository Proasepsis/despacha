from .descarga import AdaptadorDestinoDescarga
from .drive import AdaptadorDestinoDrive

DESTINOS_DISPONIBLES = {
    "descarga": AdaptadorDestinoDescarga,
    "drive": AdaptadorDestinoDrive,
}
