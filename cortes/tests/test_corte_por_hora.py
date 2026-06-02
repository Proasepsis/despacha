from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, TestCase

from cortes.servicios.corte_por_hora import sugerir_corte

BOGOTA = ZoneInfo("America/Bogota")


class CortePorHoraTest(SimpleTestCase):
    def test_madrugada_corte_1(self):
        self.assertEqual(sugerir_corte(datetime(2026, 5, 6, 0, 0, tzinfo=BOGOTA)), 1)

    def test_maniana_corte_1(self):
        self.assertEqual(sugerir_corte(datetime(2026, 5, 6, 6, 30, tzinfo=BOGOTA)), 1)

    def test_antes_del_mediodia_corte_1(self):
        self.assertEqual(sugerir_corte(datetime(2026, 5, 6, 11, 59, tzinfo=BOGOTA)), 1)

    def test_mediodia_en_punto_corte_2(self):
        self.assertEqual(sugerir_corte(datetime(2026, 5, 6, 12, 0, tzinfo=BOGOTA)), 2)

    def test_pasado_mediodia_corte_2(self):
        self.assertEqual(sugerir_corte(datetime(2026, 5, 6, 12, 1, tzinfo=BOGOTA)), 2)

    def test_noche_corte_2(self):
        self.assertEqual(sugerir_corte(datetime(2026, 5, 6, 23, 59, tzinfo=BOGOTA)), 2)

    def test_sin_timezone_asume_bogota(self):
        self.assertEqual(sugerir_corte(datetime(2026, 5, 6, 8, 0)), 1)

    def test_sin_timezone_tarde(self):
        self.assertEqual(sugerir_corte(datetime(2026, 5, 6, 14, 0)), 2)
