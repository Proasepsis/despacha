import uuid
from datetime import date, datetime

from django.contrib.auth import get_user_model
from django.test import TestCase

from cortes.models import Corte
from cortes.servicios.cargar import ErrorCarga, ErrorDuplicado
from cortes.servicios.cargar_ingesta import FORMATO_API_SIIGO, cargar_ingesta
from integraciones_siigo.models import IngestionSiigo


def _fila(numero="56321", fecha=None, hora=None):
    fila = {
        "tipo_comprobante": "F",
        "codigo_comprobante": "001",
        "numero_documento": numero,
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
    if fecha is not None:
        fila["fecha_actualizacion"] = fecha
        fila["hora_actualizacion"] = hora
    return fila


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


class FranjaHorariaTests(TestCase):
    """Corte 2 = [16:00 del día anterior, 11:00); Corte 1 = [11:00, 16:00)."""

    def setUp(self):
        self.usuario = get_user_model().objects.create_user("operador", password="x")

    def _ingesta(self, filas):
        return IngestionSiigo.objects.create(
            extraction_id=uuid.uuid4(), schema_version="1.0", source="siigo",
            window_start=date(2026, 9, 23), window_end=date(2026, 9, 24),
            generated_at=datetime(2026, 9, 24, 16, 0), raw_sha256="a" * 64, raw_size_bytes=1,
            content_sha256="b" * 64, rows_sha256=uuid.uuid4().hex * 2, row_count=len(filas),
            payload={"rows": filas},
        )

    def _facturas(self, corte):
        return sorted(corte.documentos.values_list("factura", flat=True))

    def test_cada_corte_toma_solo_su_franja(self):
        filas = [
            _fila("A_ayer_1559", 20260923, 155959),  # corte 1 de ayer: fuera de ambos
            _fila("B_ayer_1600", 20260923, 160000),  # corte 2
            _fila("C_hoy_0919", "20260924", "91931"),  # corte 2 (hora de 5 dígitos)
            _fila("D_hoy_1100", 20260924, 110000),  # corte 1
            _fila("E_hoy_1559", 20260924, 155959),  # corte 1
            _fila("F_hoy_1600", 20260924, 160000),  # corte 2 de mañana: fuera de ambos
            _fila("G_sin_hora"),  # sin hora: se conserva siempre
        ]
        corte2, _ = cargar_ingesta(self._ingesta(filas), self.usuario, numero_corte=2, fecha=date(2026, 9, 24))
        corte1, _ = cargar_ingesta(self._ingesta(filas), self.usuario, numero_corte=1, fecha=date(2026, 9, 24))

        assert self._facturas(corte2) == ["B_ayer_1600", "C_hoy_0919", "G_sin_hora"]
        assert self._facturas(corte1) == ["D_hoy_1100", "E_hoy_1559", "G_sin_hora"]

    def test_documento_usa_la_hora_de_su_primera_fila(self):
        filas = [_fila("X", 20260924, 110005), _fila("X", 20260924, 105958)]
        corte2, _ = cargar_ingesta(self._ingesta(filas), self.usuario, numero_corte=2, fecha=date(2026, 9, 24))
        assert self._facturas(corte2) == ["X"]

    def test_error_si_ningun_documento_cae_en_la_franja(self):
        filas = [_fila("Z", 20260924, 170000)]
        with self.assertRaises(ErrorCarga):
            cargar_ingesta(self._ingesta(filas), self.usuario, numero_corte=1, fecha=date(2026, 9, 24))
        assert Corte.objects.count() == 0

    def test_sin_numero_se_deduce_de_la_hora_de_extraccion(self):
        from datetime import timezone as tz
        filas = [_fila("M", 20260924, 90000), _fila("T", 20260924, 130000)]
        manana = self._ingesta(filas)
        manana.generated_at = datetime(2026, 9, 24, 16, 0, tzinfo=tz.utc)  # 11:00 Bogotá
        tarde = self._ingesta(filas)
        tarde.generated_at = datetime(2026, 9, 24, 21, 0, tzinfo=tz.utc)  # 16:00 Bogotá

        corte2, _ = cargar_ingesta(manana, self.usuario, fecha=date(2026, 9, 24))
        corte1, _ = cargar_ingesta(tarde, self.usuario, fecha=date(2026, 9, 24))

        assert (corte2.numero_corte, self._facturas(corte2)) == (2, ["M"])
        assert (corte1.numero_corte, self._facturas(corte1)) == (1, ["T"])


class Schema11Tests(TestCase):
    """Payloads v0.2 del extractor: traen ``cut`` y ya vienen filtrados por su ventana (desde, hasta]."""

    def setUp(self):
        self.usuario = get_user_model().objects.create_user("operador", password="x")

    def _ingesta(self, nombre, desde, hasta, filas):
        return IngestionSiigo.objects.create(
            extraction_id=uuid.uuid4(), schema_version="1.1", source="siigo",
            window_start=date(2026, 9, 23), window_end=date(2026, 9, 25),
            generated_at=datetime(2026, 9, 25, 21, 0), raw_sha256="a" * 64, raw_size_bytes=1,
            content_sha256="b" * 64, rows_sha256=uuid.uuid4().hex * 2, row_count=len(filas),
            payload={"rows": filas, "cut": {"nombre": nombre, "desde": desde, "hasta": hasta}},
        )

    def test_corte_1_del_extractor_es_el_corte_2_de_despacha_y_no_se_refiltra(self):
        # 11:00:03 cae fuera de la franja fija [16:00, 11:00) pero el extractor la incluyó: no se pierde
        filas = [_fila("A", "20260924", "160001"), _fila("B", "20260925", "110003")]
        ingesta = self._ingesta("corte_1", "2026-09-24T16:00:00-05:00", "2026-09-25T11:00:05-05:00", filas)

        corte, _ = cargar_ingesta(ingesta, self.usuario)

        assert (corte.numero_corte, corte.fecha) == (2, date(2026, 9, 25))
        assert sorted(corte.documentos.values_list("factura", flat=True)) == ["A", "B"]

    def test_corte_2_del_extractor_es_el_corte_1_de_despacha(self):
        # 16:00:00 exacto: el extractor lo pone en la tarde (hasta incluido); la franja fija lo habría descartado
        filas = [_fila("C", "20260925", "160000")]
        ingesta = self._ingesta("corte_2", "2026-09-25T11:00:05-05:00", "2026-09-25T16:00:00-05:00", filas)

        corte, _ = cargar_ingesta(ingesta, self.usuario)

        assert (corte.numero_corte, corte.fecha) == (1, date(2026, 9, 25))
        assert list(corte.documentos.values_list("factura", flat=True)) == ["C"]


class MismoNumeroDistintoTipoTests(TestCase):
    def test_factura_y_traslado_con_el_mismo_numero_son_documentos_distintos(self):
        usuario = get_user_model().objects.create_user("operador", password="x")
        factura = _fila("603")
        traslado = {**_fila("603"), "tipo_comprobante": "T", "codigo_comprobante": "10", "cantidad": 3}
        ingesta = IngestionSiigo.objects.create(
            extraction_id=uuid.uuid4(), schema_version="1.0", source="siigo",
            window_start=date(2026, 9, 25), window_end=date(2026, 9, 25),
            generated_at=datetime(2026, 9, 25, 12, 0), raw_sha256="a" * 64, raw_size_bytes=1,
            content_sha256="b" * 64, rows_sha256="e" * 64, row_count=2,
            payload={"rows": [factura, traslado]},
        )

        corte, _ = cargar_ingesta(ingesta, usuario, numero_corte=1)

        docs = {d.tipo_comprobante: d for d in corte.documentos.all()}
        assert set(docs) == {"F", "T"}
        assert docs["F"].lineas.get().cantidad_origen == 16
        assert docs["T"].lineas.get().cantidad_origen == 3


class IngestaVaciaTests(TestCase):
    def test_rows_vacio_no_crea_corte(self):
        usuario = get_user_model().objects.create_user("operador", password="x")
        ingesta = IngestionSiigo.objects.create(
            extraction_id=uuid.uuid4(), schema_version="1.1", source="siigo",
            window_start=date(2026, 9, 24), window_end=date(2026, 9, 25),
            generated_at=datetime(2026, 9, 25, 21, 0), raw_sha256="a" * 64, raw_size_bytes=1,
            content_sha256="b" * 64, rows_sha256="f" * 64, row_count=0,
            payload={"rows": [], "cut": {"nombre": "corte_2", "desde": "2026-09-25T11:00:05-05:00",
                                         "hasta": "2026-09-25T16:00:00-05:00"}},
        )
        with self.assertRaises(ErrorCarga):
            cargar_ingesta(ingesta, usuario)
        assert Corte.objects.count() == 0
