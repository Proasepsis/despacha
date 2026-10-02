import uuid
from datetime import date, datetime, timezone

from django.test import TestCase

from cortes.forms import CargarCorteForm
from integraciones_siigo.models import IngestionSiigo
from integraciones_siigo.tests.test_cargar_ingesta import _fila


def _ingesta(filas, generada, cut=None):
    return IngestionSiigo.objects.create(
        extraction_id=uuid.uuid4(), schema_version="1.1", source="siigo",
        window_start=date(2026, 9, 24), window_end=date(2026, 9, 25), generated_at=generada,
        raw_sha256="a" * 64, raw_size_bytes=1, content_sha256="b" * 64,
        rows_sha256=uuid.uuid4().hex * 2, row_count=len(filas), payload={"rows": filas, **({"cut": cut} if cut else {})},
    )


class SelectIngestasTest(TestCase):
    def test_solo_lista_ingestas_con_documentos_y_muestra_la_hora_de_extraccion(self):
        valida = _ingesta([_fila("1"), _fila("1"), _fila("2")], datetime(2026, 9, 25, 16, 0, 8, tzinfo=timezone.utc),
                          cut={"nombre": "corte_1"})
        _ingesta([], datetime(2026, 9, 25, 21, 0, tzinfo=timezone.utc))  # sin movimiento
        _ingesta([{**_fila("3"), "codigo_bodega": "100"}], datetime(2026, 9, 26, 16, 0, tzinfo=timezone.utc))  # otra bodega

        campo = CargarCorteForm().fields["ingestion"]

        assert list(campo.queryset) == [valida]
        assert campo.label_from_instance(valida) == "25/09/2026 11:00 · Corte 2 · 2 documentos"

    def test_recuperaciones_se_distinguen_por_dia(self):
        recuperacion = _ingesta([_fila("1")], datetime(2026, 9, 26, 2, 49, tzinfo=timezone.utc), cut={"nombre": "recuperacion"})

        etiqueta = CargarCorteForm().fields["ingestion"].label_from_instance(recuperacion)

        assert etiqueta == "25/09/2026 21:49 · Recuperación del 24/09 · 1 documento"


class NumeroPorIngestaTest(TestCase):
    def test_mapea_cada_extraccion_a_su_numero_de_corte_despacha(self):
        manana = _ingesta([_fila("1")], datetime(2026, 9, 25, 16, 0, tzinfo=timezone.utc), cut={"nombre": "corte_1"})
        tarde = _ingesta([_fila("2")], datetime(2026, 9, 25, 21, 0, tzinfo=timezone.utc), cut={"nombre": "corte_2"})
        _ingesta([_fila("3")], datetime(2026, 9, 26, 2, 0, tzinfo=timezone.utc), cut={"nombre": "extra"})

        assert CargarCorteForm().numero_por_ingesta == {str(manana.pk): 2, str(tarde.pk): 1}

    def test_la_pagina_de_carga_entrega_el_mapa_al_js(self):
        from django.contrib.auth.models import Group, User
        from django.urls import reverse

        manana = _ingesta([_fila("1")], datetime(2026, 9, 25, 16, 0, tzinfo=timezone.utc), cut={"nombre": "corte_1"})
        user = User.objects.create_user("fac")
        user.groups.add(Group.objects.get_or_create(name="facturacion")[0])
        self.client.force_login(user)

        html = self.client.get(reverse("cargar_corte")).content.decode()

        assert f'<script id="numero-por-ingesta" type="application/json">{{"{manana.pk}": 2}}</script>' in html
        assert 'id="aviso-numero"' in html
