from dataclasses import dataclass
from abc import ABC, abstractmethod

from cortes.models import Corte


@dataclass
class ResultadoEntrega:
    ok: bool
    referencia: str = ""
    error: str = ""


class AdaptadorDestino(ABC):
    codigo: str
    nombre_mostrar: str

    @abstractmethod
    def entregar(
        self, archivo_bytes: bytes, nombre_archivo: str, corte: Corte
    ) -> ResultadoEntrega:
        ...
