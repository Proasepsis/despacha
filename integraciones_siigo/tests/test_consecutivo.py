import uuid
from datetime import date, datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from cortes.forms import CargarCorteForm
from cortes.models import Corte, Documento
from cortes.servicios.cargar import ErrorCarga, ErrorDuplicado
from cortes.servicios.cargar_ingesta import cargar_ingesta
from integraciones_siigo.models import IngestionSiigo


def _fila(numero, tipo="F", codigo="001", hora="230000", fecha="20261013"):
    # Por defecto cae fuera de cualquier franja del 15-oct: solo entra si no se filtra por hora
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


def _ingesta(filas):
    return IngestionSiigo.objects.create(
        extraction_id=uuid.uuid4(), schema_version="1.0", source="siigo",
        window_start=date(2026, 10, 15), window_end=date(2026, 10, 15),
        generated_at=datetime(2026, 10, 15, 17, 0), raw_sha256="a" * 64, raw_size_bytes=1,
        content_sha256="b" * 64, rows_sha256=uuid.uuid4().hex * 2, row_count=len(filas),
        payload={"rows": filas},
    )


class DesdeConsecutivoTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user("operador", password="x")

    def _cargar(self, filas, desde, **kw):
        corte, _ = cargar_ingesta(
            _ingesta(filas), self.usuario, numero_corte=1, desde_consecutivo=desde, **kw
        )
        return sorted(corte.documentos.values_list("factura", flat=True))

    def test_corta_desde_el_consecutivo_indicado_e_incluye_ese_numero(self):
        filas = [_fila(n) for n in (56933, 56934, 56935, 56940)]
        self.assertEqual(self._cargar(filas, {("F", 1): 56935}), ["56935", "56940"])

    def test_no_filtra_por_franja_horaria(self):
        # La hora de estas filas cae fuera de la franja del corte 1 del 15-oct
        self.assertEqual(self._cargar([_fila(56935)], {("F", 1): 56935}), ["56935"])

    def test_serie_sin_consecutivo_entra_completa(self):
        filas = [_fila(56934), _fila(5, tipo="T", codigo="010")]
        self.assertEqual(self._cargar(filas, {("F", 1): 56935}), ["5"])

    def test_traslados_10_y_25_son_series_independientes(self):
        filas = [
            _fila(729, tipo="T", codigo="010"),
            _fila(788, tipo="T", codigo="025"),
            _fila(790, tipo="T", codigo="025"),
        ]
        self.assertEqual(self._cargar(filas, {("T", 25): 790}), ["729", "790"])

    def test_sin_documentos_desde_ese_consecutivo_se_rechaza(self):
        with self.assertRaises(ErrorCarga):
            self._cargar([_fila(56934)], {("F", 1): 56935})

    def test_guarda_el_codigo_de_comprobante(self):
        corte, _ = cargar_ingesta(
            _ingesta([_fila(788, tipo="T", codigo="025")]), self.usuario,
            numero_corte=1, desde_consecutivo={("T", 25): 700},
        )
        doc = corte.documentos.get()
        self.assertEqual((doc.tipo_comprobante, doc.codigo_comprobante), ("T", "25"))

    def test_misma_extraccion_con_otro_consecutivo_es_otro_corte_pero_repetido_es_duplicado(self):
        ing = _ingesta([_fila(n) for n in (56935, 56940)])
        cargar_ingesta(ing, self.usuario, numero_corte=1, desde_consecutivo={("F", 1): 56935})

        corte2, _ = cargar_ingesta(
            ing, self.usuario, numero_corte=1, es_adicional=True, desde_consecutivo={("F", 1): 56940}
        )
        self.assertEqual(list(corte2.documentos.values_list("factura", flat=True)), ["56940"])

        with self.assertRaises(ErrorDuplicado):
            cargar_ingesta(
                ing, self.usuario, numero_corte=1, es_adicional=True,
                desde_consecutivo={("F", 1): 56940},
            )

    def test_sin_consecutivo_todo_sigue_igual_que_antes(self):
        ing = _ingesta([_fila(1, hora="090000", fecha="20261015")])
        corte, _ = cargar_ingesta(ing, self.usuario, numero_corte=2)
        self.assertEqual(corte.documentos.count(), 1)


class FormularioYPreviaTests(TestCase):
    def test_formulario_arma_el_diccionario_de_consecutivos(self):
        form = CargarCorteForm({
            "formato_origen": "API_SIIGO", "numero_corte": "1",
            "desde_F1": "56935", "desde_T25": "788",
        })
        form.is_valid()
        self.assertEqual(form.desde_consecutivo(), {("F", 1): 56935, ("T", 25): 788})

    def test_formulario_sin_consecutivos_devuelve_vacio(self):
        form = CargarCorteForm({"formato_origen": "API_SIIGO", "numero_corte": "1"})
        form.is_valid()
        self.assertEqual(form.desde_consecutivo(), {})

    def test_previa_muestra_rango_y_ultimo_cargado_por_serie(self):
        usuario = get_user_model().objects.create_user("fac", password="x")
        usuario.groups.add(Group.objects.get_or_create(name="facturacion")[0])
        self.client.force_login(usuario)
        corte = Corte.objects.create(
            archivo="p.xlsx", hash_sha256="z" * 64, usuario_carga=usuario,
            fecha=date(2026, 10, 14), numero_corte=2, estado="generado",
        )
        for n in ("56933", "56930"):
            Documento.objects.create(corte=corte, factura=n, tipo_comprobante="F", codigo_comprobante="1")
        ing = _ingesta([_fila(56935), _fila(56940), _fila(788, tipo="T", codigo="025")])

        r = self.client.get(reverse("previa_ingesta", args=[ing.pk]))

        self.assertEqual(r.status_code, 200)
        series = {s["serie"]: s for s in r.json()["series"]}
        self.assertEqual(
            (series["F-1"]["documentos"], series["F-1"]["desde"], series["F-1"]["hasta"],
             series["F-1"]["ultimo_cargado"]),
            (2, "56935", "56940", "56933"),
        )
        self.assertEqual(series["T-25"]["ultimo_cargado"], None)
