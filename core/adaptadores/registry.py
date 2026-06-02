from importlib import import_module
from pathlib import Path

from .base import AdaptadorFormato

_REGISTRO: dict[str, type[AdaptadorFormato]] = {}
_descubiertos = False


def _descubrir():
    global _descubiertos
    if _descubiertos:
        return
    _descubiertos = True

    dir_actual = Path(__file__).parent
    for child in dir_actual.iterdir():
        if child.is_dir() and not child.name.startswith("_"):
            init = child / "__init__.py"
            if init.exists():
                try:
                    import_module(f"core.adaptadores.{child.name}")
                except Exception:
                    pass


def registrar(clase: type[AdaptadorFormato]) -> type[AdaptadorFormato]:
    _REGISTRO[clase.nombre] = clase
    return clase


def obtener(nombre: str) -> AdaptadorFormato:
    _descubrir()
    if nombre not in _REGISTRO:
        raise ValueError(f"Adaptador de formato desconocido: {nombre}")
    return _REGISTRO[nombre]()


def disponibles() -> list[str]:
    _descubrir()
    return sorted(_REGISTRO.keys())
