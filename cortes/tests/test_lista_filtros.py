from datetime import date, timedelta
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone

from cortes.models import Corte, Documento


def _corte(usuario, fecha, numero=1, estado="en_revision", hash_extra=""):
    return Corte.objects.create(
        archivo="test.xlsx",
        hash_sha256=f"hash{fecha}{numero}{hash_extra}",
        usuario_carga=usuario,
        fecha=fecha,
        numero_corte=numero,
        estado=estado,
    )


def _doc(corte, factura, nit="800000"):
    return Documento.objects.create(corte=corte, factura=factura, nit=nit)


class FiltroListaTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u1", password="pw")
        self.user2 = User.objects.create_user(username="u2", password="pw")
        self.client.force_login(self.user)

        hoy = timezone.localdate()
        hace_60 = hoy - timedelta(days=60)

        # corte reciente (dentro de 30 días)
        self.corte_reciente = _corte(self.user, hoy, numero=1, estado="generado", hash_extra="r")
        _doc(self.corte_reciente, "FAC001", nit="900111")

        # corte antiguo (fuera de 30 días)
        self.corte_antiguo = _corte(self.user2, hace_60, numero=2, estado="en_revision", hash_extra="a")
        _doc(self.corte_antiguo, "FAC999", nit="800555")

    def _get(self, params=""):
        return self.client.get(reverse("lista_cortes") + params)

    def test_sin_filtros_solo_30_dias(self):
        r = self._get()
        self.assertEqual(r.status_code, 200)
        ids = [c.pk for c in r.context["cortes"]]
        self.assertIn(self.corte_reciente.pk, ids)
        self.assertNotIn(self.corte_antiguo.pk, ids)

    def test_busqueda_q_trae_corte_antiguo(self):
        r = self._get("?q=FAC999")
        self.assertEqual(r.status_code, 200)
        ids = [c.pk for c in r.context["cortes"]]
        self.assertIn(self.corte_antiguo.pk, ids)
        self.assertNotIn(self.corte_reciente.pk, ids)

    def test_busqueda_q_por_nit(self):
        r = self._get("?q=900111")
        ids = [c.pk for c in r.context["cortes"]]
        self.assertIn(self.corte_reciente.pk, ids)

    def test_filtro_estado(self):
        r = self._get("?estado=generado")
        ids = [c.pk for c in r.context["cortes"]]
        self.assertIn(self.corte_reciente.pk, ids)
        self.assertNotIn(self.corte_antiguo.pk, ids)

    def test_filtro_usuario(self):
        r = self._get(f"?usuario={self.user2.pk}")
        ids = [c.pk for c in r.context["cortes"]]
        self.assertIn(self.corte_antiguo.pk, ids)
        self.assertNotIn(self.corte_reciente.pk, ids)

    def test_filtro_desde(self):
        hace_70 = (timezone.localdate() - timedelta(days=70)).isoformat()
        r = self._get(f"?desde={hace_70}")
        ids = [c.pk for c in r.context["cortes"]]
        self.assertIn(self.corte_antiguo.pk, ids)
        self.assertIn(self.corte_reciente.pk, ids)

    def test_filtros_activos_en_contexto(self):
        r = self._get("?q=FAC999")
        self.assertTrue(r.context["filtros_activos"])
        self.assertIn("total_filtrado", r.context)

    def test_sin_filtros_no_hay_total(self):
        r = self._get()
        self.assertFalse(r.context["filtros_activos"])
        self.assertNotIn("total_filtrado", r.context)
