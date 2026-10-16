import json
import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from cortes.models import Corte, Documento, DocumentoDescartado
from cortes.servicios.cargar import ErrorCarga, ErrorDuplicado
from cortes.servicios.cargar_ingesta import cargar_ingesta
from integraciones_siigo.models import IngestionSiigo

BOGOTA = ZoneInfo("America/Bogota")


def _fila(numero, tipo="F", codigo="001", hora="100000", fecha="20261015"):
    return {
        "tipo_comprobante": tipo,
        "codigo_comprobante": codigo,
        "numero_documento": str(numero),
        "cuenta_contable": "1430462000",
        "debito_credito": "C",
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
        "descripcion_secuencia": "ASEPTIGERM",
        "sucursal": "0",
        "fecha_actualizacion": fecha,
        "hora_actualizacion": hora,
    }


def _ingesta(filas, sufijo="c"):
    return IngestionSiigo.objects.create(
        extraction_id=uuid.uuid4(),
        schema_version="1.0",
        source="siigo",
        window_start=date(2026, 10, 15),
        window_end=date(2026, 10, 15),
        generated_at=datetime(2026, 10, 15, 12, 0, 0),
        raw_sha256="a" * 64,
        raw_size_bytes=100,
        content_sha256="b" * 64,
        rows_sha256=sufijo * 64,
        row_count=len(filas),
        payload={"rows": filas},
    )


class ConsecutivosBase(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user("operador", password="x")

    def _corte_previo(self, facturas, tipo="F", codigo="", estado="generado"):
        corte = Corte.objects.create(
            archivo="p.xlsx", hash_sha256="z" * 64, usuario_carga=self.usuario,
            fecha=date(2026, 10, 14), numero_corte=2, estado=estado,
        )
        for f in facturas:
            Documento.objects.create(
                corte=corte, factura=f, tipo_comprobante=tipo, codigo_comprobante=codigo
            )
        return corte


class SeleccionPorConsecutivoTests(ConsecutivosBase):
    def test_omite_documentos_ya_cargados(self):
        self._corte_previo(["56321"])
        ing = _ingesta([_fila(56321), _fila(56322)])

        corte, _ = cargar_ingesta(ing, self.usuario, numero_corte=1)

        self.assertEqual(list(corte.documentos.values_list("factura", flat=True)), ["56322"])

    def test_documento_previo_sin_codigo_cuenta_como_cargado(self):
        self._corte_previo(["56321"], codigo="")
        ing = _ingesta([_fila(56321, codigo="001")])

        with self.assertRaises(ErrorCarga):
            cargar_ingesta(ing, self.usuario, numero_corte=1)

    def test_mismo_numero_en_otra_serie_de_traslado_no_choca(self):
        self._corte_previo(["729"], tipo="T", codigo="10")
        ing = _ingesta([_fila(729, tipo="T", codigo="025")])

        corte, _ = cargar_ingesta(ing, self.usuario, numero_corte=1)

        doc = corte.documentos.get()
        self.assertEqual((doc.tipo_comprobante, doc.codigo_comprobante), ("T", "25"))

    def test_corte_con_error_no_cuenta_como_cargado(self):
        self._corte_previo(["56321"], estado="con_error")
        ing = _ingesta([_fila(56321)])

        corte, _ = cargar_ingesta(ing, self.usuario, numero_corte=1)

        self.assertEqual(corte.documentos.count(), 1)

    def test_documento_eliminado_a_proposito_no_reaparece(self):
        DocumentoDescartado.objects.create(
            tipo_comprobante="F", codigo_comprobante="1", factura="56322"
        )
        ing = _ingesta([_fila(56321), _fila(56322)])

        corte, _ = cargar_ingesta(ing, self.usuario, numero_corte=1)

        self.assertEqual(list(corte.documentos.values_list("factura", flat=True)), ["56321"])

    def test_sin_documentos_nuevos_se_rechaza(self):
        self._corte_previo(["56321"])
        ing = _ingesta([_fila(56321)])

        with self.assertRaises(ErrorCarga) as ctx:
            cargar_ingesta(ing, self.usuario, numero_corte=1)
        self.assertNotIsInstance(ctx.exception, ErrorDuplicado)

    def test_misma_ingesta_dos_veces_sigue_siendo_duplicado(self):
        ing = _ingesta([_fila(56321)])
        cargar_ingesta(ing, self.usuario, numero_corte=1)

        with self.assertRaises(ErrorDuplicado):
            cargar_ingesta(ing, self.usuario, numero_corte=1, es_adicional=True)

    def test_segunda_carga_trae_solo_lo_que_faltaba(self):
        ing = _ingesta([_fila(56321)])
        cargar_ingesta(ing, self.usuario, numero_corte=1)
        ing.payload = {"rows": [_fila(56321), _fila(56322)]}
        ing.rows_sha256 = "d" * 64
        ing.save()

        corte, _ = cargar_ingesta(ing, self.usuario, numero_corte=1, es_adicional=True)

        self.assertEqual(list(corte.documentos.values_list("factura", flat=True)), ["56322"])


class FiltroPorHoraTests(ConsecutivosBase):
    def setUp(self):
        super().setUp()
        self.ing = _ingesta([
            _fila(1, hora="090000"),
            _fila(2, hora="120000"),
            _fila(3, hora="160000"),
        ])

    def _facturas(self, **kw):
        corte, _ = cargar_ingesta(self.ing, self.usuario, numero_corte=1, **kw)
        return sorted(corte.documentos.values_list("factura", flat=True))

    def test_desde_excluye_la_manana(self):
        desde = datetime(2026, 10, 15, 11, 0, tzinfo=BOGOTA)
        self.assertEqual(self._facturas(desde=desde), ["2", "3"])

    def test_rango_desde_hasta_excluyente_en_desde_e_incluyente_en_hasta(self):
        desde = datetime(2026, 10, 15, 9, 0, tzinfo=BOGOTA)
        hasta = datetime(2026, 10, 15, 12, 0, tzinfo=BOGOTA)
        self.assertEqual(self._facturas(desde=desde, hasta=hasta), ["2"])

    def test_fila_sin_hora_no_entra_cuando_se_filtra(self):
        filas = [_fila(1), {**_fila(2), "fecha_actualizacion": None, "hora_actualizacion": None}]
        ing = _ingesta(filas, sufijo="e")
        desde = datetime(2026, 10, 15, 0, 0, tzinfo=BOGOTA)
        corte, _ = cargar_ingesta(ing, self.usuario, numero_corte=1, desde=desde)
        self.assertEqual(list(corte.documentos.values_list("factura", flat=True)), ["1"])


class PreviaYEliminacionTests(ConsecutivosBase):
    def setUp(self):
        super().setUp()
        grupo = Group.objects.get_or_create(name="facturacion")[0]
        self.usuario.groups.add(grupo)
        self.client.force_login(self.usuario)

    def test_previa_resume_por_serie(self):
        self._corte_previo(["56321"])
        ing = _ingesta([
            _fila(56321), _fila(56322), _fila(56325),
            _fila(729, tipo="T", codigo="025"),
        ])

        r = self.client.get(reverse("previa_ingesta", args=[ing.pk]))

        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["ya_cargados"], 1)
        series = {s["serie"]: s for s in data["series"]}
        self.assertEqual(
            (series["F-1"]["documentos"], series["F-1"]["desde"], series["F-1"]["hasta"]),
            (2, "56322", "56325"),
        )
        self.assertEqual(series["T-25"]["documentos"], 1)

    def test_eliminar_documento_lo_registra_como_descartado(self):
        corte = self._corte_previo(["56321", "56322"])
        corte.estado = "en_revision"
        corte.save()
        doc = corte.documentos.get(factura="56321")

        r = self.client.post(
            reverse("eliminar_documentos", args=[corte.pk]),
            json.dumps({"documento_ids": [doc.pk]}),
            content_type="application/json",
        )

        self.assertEqual(r.status_code, 200)
        self.assertTrue(
            DocumentoDescartado.objects.filter(tipo_comprobante="F", factura="56321").exists()
        )
