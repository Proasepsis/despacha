from django.test import SimpleTestCase

from core.adaptadores.plantilla.limpieza import limpiar_lote


class LimpiezaLoteTest(SimpleTestCase):
    def test_comilla_inicial(self):
        self.assertEqual(limpiar_lote("'121570226"), "121570226")

    def test_comilla_y_espacios(self):
        self.assertEqual(limpiar_lote("'121570226 "), "121570226")

    def test_comilla_y_espacios_varios(self):
        self.assertEqual(limpiar_lote("'04471225  "), "04471225")

    def test_guion_terminal_solo(self):
        self.assertEqual(limpiar_lote("121300226-"), "121300226-1")

    def test_guion_terminal_solo_otro(self):
        self.assertEqual(limpiar_lote("121760326-"), "121760326-1")

    def test_slash_corta_todo(self):
        self.assertEqual(limpiar_lote("15F22/2579"), "15F22")

    def test_slash_corta_otro(self):
        self.assertEqual(limpiar_lote("15F22/2590"), "15F22")

    def test_puntos_al_inicio_y_espacios(self):
        self.assertEqual(limpiar_lote("...15C25  "), "15C25")

    def test_un_punto_al_inicio(self):
        self.assertEqual(limpiar_lote(".15C25    "), "15C25")

    def test_espacios_internos(self):
        self.assertEqual(limpiar_lote("1 5L 23   "), "15L23")

    def test_punto_final_se_conserva(self):
        self.assertEqual(limpiar_lote("120010925."), "120010925.")

    def test_sin_punto_final_no_se_agrega(self):
        self.assertEqual(limpiar_lote("120010925"), "120010925")

    def test_alfanumerico_limpio(self):
        self.assertEqual(limpiar_lote("15C25"), "15C25")

    def test_espacios_al_final(self):
        self.assertEqual(limpiar_lote("0383B26   "), "0383B26")

    def test_guion_numero_valido_espacio_final(self):
        self.assertEqual(limpiar_lote("3090925-1 "), "3090925-1")

    def test_guion_numero_dos_digitos(self):
        self.assertEqual(limpiar_lote("3050925-10"), "3050925-10")

    def test_vacio(self):
        self.assertEqual(limpiar_lote(""), "")

    def test_solo_espacios(self):
        self.assertEqual(limpiar_lote("    "), "")

    def test_none(self):
        self.assertEqual(limpiar_lote(None), "")

    def test_idempotencia(self):
        casos = [
            "'121570226 ",
            "121300226-",
            "15F22/2579",
            "...15C25  ",
            "1 5L 23   ",
            "120010925.",
            "120010925",
            "15C25",
            "",
            "    ",
        ]
        for caso in casos:
            limpio = limpiar_lote(caso)
            self.assertEqual(limpiar_lote(limpio), limpio, f"Falla idempotencia en: {repr(caso)}")
