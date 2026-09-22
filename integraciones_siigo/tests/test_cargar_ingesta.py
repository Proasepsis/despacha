import uuid
from datetime import date, datetime

from django.contrib.auth import get_user_model
from django.test import TestCase

from cortes.models import Corte
from cortes.servicios.cargar import ErrorDuplicado
from cortes.servicios.cargar_ingesta import FORMATO_API_SIIGO, cargar_ingesta
from integraciones_siigo.models import IngestionSiigo


def _fila():
    return {
        "tipo_comprobante": "F",
        "codigo_comprobante": "001",
        "numero_documento": "56321",
        "cuenta_contable": "1430462000",
        "debito_credito": "C",
        "valor_secuencia": 1000,
        "comprobante_anulado": "N",
        "linea_producto": "165",
        "grupo_producto": "0015",
        "codigo_producto": "000025",
        "cantidad": 16,
        "codigo_bodega": "0400",
        "codigo_ubicacion": "005",
        "lote": "'120831225 ",
        "nit": "830007355",
        "codigo_ciudad": "0001",
        "descripcion_secuencia": "ASEPTIGERM JAB ANTIB ESP",
        "sucursal": "0",
    }


class CargarIngestaTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user("operador", password="x")
        self.ingestion = IngestionSiigo.objects.create(
            extraction_id=uuid.uuid4(),
            schema_version="1.0",
            source="siigo",
            window_start=date(2026, 7, 9),
            window_end=date(2026, 7, 9),
            generated_at=datetime(2026, 7, 9, 12, 0, 0),
            raw_sha256="a" * 64,
            raw_size_bytes=100,
            content_sha256="b" * 64,
            rows_sha256="c" * 64,
            row_count=1,
            payload={"rows": [_fila()]},
        )

    def test_crea_corte_desde_ingesta(self):
        corte, resultado = cargar_ingesta(self.ingestion, self.usuario, numero_corte=1)

        assert corte.formato_origen == FORMATO_API_SIIGO
        assert corte.estado == "en_revision"
        assert corte.documentos.count() == 1
        assert resultado.documentos_creados == 1
        assert resultado.lineas_creadas == 1

    def test_duplicado_se_rechaza(self):
        cargar_ingesta(self.ingestion, self.usuario, numero_corte=1)
        with self.assertRaises(ErrorDuplicado):
            cargar_ingesta(self.ingestion, self.usuario, numero_corte=1)

    def test_no_repite_misma_fotografia(self):
        cargar_ingesta(self.ingestion, self.usuario, numero_corte=1)
        assert Corte.objects.count() == 1
