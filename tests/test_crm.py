"""CRM y fidelización en la web: boletín con doble confirmación, casillas del pedido, programa de puntos y privacidad.

    python -m unittest discover -s tests -t . -v
"""
import re
import unittest

from tests.test_build import PRODUCTS, Site

SHOP = {"api": "https://api.cliente.es", "comprar": True}
NEWS = "https://api.cliente.es/api/boletin"
BASES = "https://www.ejemplo-cliente.es/bases-programa/"


class CrmTests(unittest.TestCase):
    def setUp(self):
        self.sites = []

    def tearDown(self):
        for s in self.sites:
            s.cleanup()

    def site(self, crm: dict | None = None, products=PRODUCTS, catalog=SHOP, boletin_page=False, bases_page=False) -> Site:
        s = Site(products=products, catalog=catalog, crm=crm or {})
        self.sites.append(s)
        if boletin_page:
            (s.dir / "content" / "es" / "novedades.md").write_text(
                "---\ntitle: Novedades\ndescription: Boletín\nnav: 40\n---\n\n:::boletin\n## Recibe nuestras novedades\nUna vez al mes.\n:::\n", encoding="utf-8")
        if bases_page:
            (s.dir / "content" / "es" / "bases.md").write_text(
                "---\ntitle: Bases del programa de puntos\ndescription: Bases\nslug: bases-programa\nnoindex: true\n---\n\nBases.\n", encoding="utf-8")
        return s

    def test_sin_crm_la_web_es_la_de_siempre(self):
        s = self.site()
        code, out = s.build()
        self.assertEqual(code, 0, out)
        ficha = s.read("productos/hogaza/index.html")
        for name in ("consent_news", "consent_optout", "aviso_ofertas", "programa", 'name="vale"'):
            self.assertNotIn(name, ficha)
        priv = s.read("privacidad/index.html")
        self.assertNotIn("Boletín", priv)
        self.assertNotIn("Programa de puntos", priv)
        s2 = self.site(boletin_page=True)
        code, out = s2.build()
        self.assertNotEqual(code, 0, "bloque :::boletin sin endpoint")
        self.assertIn("crm.boletin", out)

    def test_boletin_casilla_sin_marcar_informacion_basica_y_pagina_de_aviso(self):
        s = self.site({"boletin": NEWS}, boletin_page=True)
        code, out = s.build()
        self.assertEqual(code, 0, out)
        page = s.read("novedades/index.html")
        form = re.search(r'<form class="newsletter".*?</form>', page, re.S).group(0)
        self.assertIn(f'action="{NEWS}"', form)
        self.assertRegex(form, r'<input type="checkbox" name="consent" value="yes" required>', "casilla obligatoria")
        self.assertNotRegex(form, r'name="consent"[^>]*checked', "nunca marcada de antemano")
        self.assertIn('name="website"', form, "campo trampa contra bots")
        self.assertIn('name="origen" value="/novedades/"', form, "queda dónde se apuntó (prueba del consentimiento)")
        self.assertIn('name="redirect" value="https://www.ejemplo-cliente.es/boletin-revisa-tu-email/"', form)
        self.assertIn("Responsable:", form)
        self.assertIn('href="/privacidad/"', form)
        self.assertIn("confirmes por email", form)
        self.assertIn("Revisa tu email", s.read("boletin-revisa-tu-email/index.html"))
        priv = s.read("privacidad/index.html")
        self.assertIn("<strong>Boletín y novedades.</strong>", priv)
        self.assertIn("enlace que te enviamos", priv)
        self.assertIn("lista de exclusión", priv)
        self.assertIn("No usamos píxeles", priv)
        self.assertEqual(s.check()[0], 0, s.check()[1])
        bad = self.site({"boletin": "http://api.cliente.es/api/boletin"}, boletin_page=True)
        self.assertNotEqual(bad.build()[0], 0, "el boletín solo por https")

    def test_casillas_del_pedido_sin_marcar_y_una_sola_forma_de_pedir_permiso(self):
        s = self.site({"novedades_en_pedido": True})
        self.assertEqual(s.build()[0], 0)
        ficha = s.read("productos/hogaza/index.html")
        self.assertRegex(ficha, r'<input type="checkbox" name="consent_news" value="yes">')
        self.assertNotIn("aviso_ofertas", ficha)

        s2 = self.site({"ofertas_clientes": True, "aviso_version": "2026-10"})
        self.assertEqual(s2.build()[0], 0)
        f2 = s2.read("productos/hogaza/index.html")
        self.assertIn('<input type="hidden" name="aviso_ofertas" value="2026-10">', f2, "la versión del aviso viaja con el pedido")
        self.assertRegex(f2, r'<input type="checkbox" name="consent_optout" value="yes">', "oposición con una casilla sin marcar")
        self.assertIn("productos parecidos", f2)
        self.assertNotIn("consent_news", f2)
        priv = s2.read("privacidad/index.html")
        self.assertIn("art. 21.2 de la LSSI", priv)
        self.assertIn("puedes oponerte", priv)

        both = self.site({"novedades_en_pedido": True, "ofertas_clientes": True})
        code, out = both.build()
        self.assertNotEqual(code, 0)
        self.assertIn("no las dos", out)

    def test_programa_de_puntos_casilla_vale_privacidad_y_bases_publicadas(self):
        s = self.site({"programa": {"bases_url": BASES}}, bases_page=True)
        code, out = s.build()
        self.assertEqual(code, 0, out)
        ficha = s.read("productos/hogaza/index.html")
        self.assertRegex(ficha, r'<input type="checkbox" name="programa" value="yes">')
        self.assertIn(f'href="{BASES}"', ficha)
        self.assertIn('name="vale"', ficha)
        self.assertIn("<strong>Programa de puntos.</strong>", s.read("privacidad/index.html"))
        self.assertEqual(s.check()[0], 0, s.check()[1])

        sin_bases = self.site({"programa": {"bases_url": BASES}})
        self.assertEqual(sin_bases.build()[0], 0)
        code, out = sin_bases.check()
        self.assertNotEqual(code, 0, "las bases del programa tienen que estar publicadas")
        self.assertIn("bases", out)
        self.assertNotEqual(self.site({"programa": {"bases_url": "http://x.es/bases"}}).build()[0], 0)


if __name__ == "__main__":
    unittest.main()
