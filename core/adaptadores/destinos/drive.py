import os
import time

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

from .base import AdaptadorDestino, ResultadoEntrega

MESES = [
    "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
    "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE",
]

_service_cache: dict[str, object] = {}


def _get_drive_service(sa_path: str):
    if sa_path not in _service_cache:
        creds = service_account.Credentials.from_service_account_file(
            sa_path, scopes=["https://www.googleapis.com/auth/drive"]
        )
        _service_cache[sa_path] = build("drive", "v3", credentials=creds)
    return _service_cache[sa_path]


class AdaptadorDestinoDrive(AdaptadorDestino):
    codigo = "drive"
    nombre_mostrar = "Subir a Google Drive"

    def __init__(self):
        sa_path = os.environ.get("DRIVE_SERVICE_ACCOUNT_JSON", "")
        self.root_id = os.environ.get("DRIVE_ROOT_FOLDER_ID", "")
        if sa_path and os.path.exists(sa_path):
            self.service = _get_drive_service(sa_path)
        else:
            self.service = None

    def entregar(self, archivo_bytes, nombre_archivo, corte):
        if self.service is None:
            return ResultadoEntrega(
                ok=False, error="Drive no configurado (DRIVE_SERVICE_ACCOUNT_JSON)"
            )

        nombre_mes = MESES[corte.fecha.month - 1]
        nombre_dia = str(corte.fecha.day)

        carpeta_mes_id = self._buscar_o_crear_carpeta(nombre_mes, self.root_id)
        carpeta_dia_id = self._buscar_o_crear_carpeta(nombre_dia, carpeta_mes_id)

        for intento, espera in enumerate([1, 3, 10], start=1):
            try:
                media = MediaInMemoryUpload(
                    archivo_bytes,
                    mimetype="application/vnd.ms-excel",
                    resumable=False,
                )
                file_metadata = {
                    "name": nombre_archivo,
                    "parents": [carpeta_dia_id],
                }
                uploaded = (
                    self.service.files()
                    .create(body=file_metadata, media_body=media, fields="id,webViewLink")
                    .execute()
                )
                return ResultadoEntrega(
                    ok=True,
                    referencia=uploaded.get("webViewLink", ""),
                )
            except Exception as e:
                if intento == 3:
                    return ResultadoEntrega(
                        ok=False,
                        error=f"Fallo al subir a Drive tras 3 intentos: {e}",
                    )
                time.sleep(espera)

        return ResultadoEntrega(ok=False, error="Error inesperado")

    def _buscar_o_crear_carpeta(self, nombre: str, parent_id: str) -> str:
        q = (
            f"name = '{nombre}' and mimeType = 'application/vnd.google-apps.folder' "
            f"and '{parent_id}' in parents and trashed = false"
        )
        results = (
            self.service.files()
            .list(q=q, fields="files(id, name)", pageSize=1)
            .execute()
        )
        files = results.get("files", [])
        if files:
            return files[0]["id"]

        folder_metadata = {
            "name": nombre,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        created = (
            self.service.files()
            .create(body=folder_metadata, fields="id")
            .execute()
        )
        return created["id"]
