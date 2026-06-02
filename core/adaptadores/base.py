from abc import ABC, abstractmethod
from pathlib import Path
from .modelo_interno import DocumentoInterno


class AdaptadorFormato(ABC):
    nombre: str

    @abstractmethod
    def validar(self, ruta_archivo: Path) -> None:
        """Lanza ValueError si el archivo no cumple la estructura esperada."""

    @abstractmethod
    def parse(self, ruta_archivo: Path) -> list[DocumentoInterno]:
        """Lee el archivo y devuelve la lista de documentos en el modelo interno."""
