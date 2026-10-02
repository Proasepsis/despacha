from .descarga import AdaptadorDestinoDescarga
from .drive import AdaptadorDestinoDrive
from .soap import AdaptadorDestinoSoap

DESTINOS_DISPONIBLES = {
    "descarga": AdaptadorDestinoDescarga,
    "drive": AdaptadorDestinoDrive,
    "soap": AdaptadorDestinoSoap,
}
