"""Idioma siempre a la vista y aviso a quien navega en otro idioma de la web (static/idioma.js), sin redirigir a nadie.

    python -m unittest tests.test_idioma -v
"""
import shutil
import sys
import unittest
from pathlib import Path

from tests.test_build import Site

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import axe  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
    HAS_PW = True
except ImportError:
    HAS_PW = False
HAS_AXE = (ROOT / "node_modules" / "axe-core" / "axe.min.js").exists()


def sitio(languages=("es", "en"), **cfg):
    s = Site(languages=list(languages), **cfg)
    shutil.rmtree(s.dir / "content")
    paginas = {"es": (("home", "", "Inicio"), ("contacto", "", "Contacto")),
               "en": (("home", "", "Home"), ("contacto", "contact", "Contact"))}
    for lang in languages:
        d = s.dir / "content" / lang
        d.mkdir(parents=True)
        for i, (key, slug, title) in enumerate(paginas[lang]):
            cab = f"key: {key}\n" + (f"slug: {slug}\n" if slug else "") + f"title: {title}\n" + (f"nav: {i * 10}\n" if key != "home" else "")
            (d / f"{key}.md").write_text(f"---\n{cab}description: Página de prueba.\n---\n\nTexto de {title}.\n", encoding="utf-8")
    return s


class Generacion(unittest.TestCase):
    def build(self, **kw):
        s = sitio(**kw)
        self.addCleanup(s.cleanup)
        code, out = s.build()
        self.assertEqual(code, 0, out)
        return s

    def test_selector_fuera_del_menu_con_nombre_completo_y_abreviado(self):
        h = self.build().read("index.html")
        cab = h.split('<header class="site-header">')[1].split("</header>")[0]
        self.assertIn('<div class="lang-switch"><a class="lang" href="/en/" hreflang="en" lang="en"><span class="lang-largo">English</span>'
                      '<span class="lang-corto" aria-hidden="true">EN</span></a></div>', cab)
        for nav in cab.split("<nav")[1:]:
            self.assertNotIn('class="lang"', nav.split("</nav>")[0], "el idioma ya no va escondido en el menú")
        self.assertIn('href="/" hreflang="es" lang="es"><span class="lang-largo">Español</span>', self.build().read("en/index.html"))

    def test_aviso_oculto_en_el_otro_idioma_y_script(self):
        s = self.build()
        es, en = s.read("index.html"), s.read("en/index.html")
        self.assertIn('<div class="aviso-idioma" role="region" aria-label="Language" lang="en" data-idioma="en" hidden>', es)
        self.assertIn('This page is also available in English. <a href="/en/" hreflang="en">View in English</a>', es)
        self.assertIn('<button type="button" class="linkish" data-cerrar-idioma>Close</button>', es)
        self.assertIn("Esta página también está en español. <a href=\"/\" hreflang=\"es\">Ver en español</a>", en)
        self.assertIn('<script src="/idioma.js" defer></script>', es)

    def test_un_solo_idioma_sin_selector_ni_aviso(self):
        s = sitio(languages=["es"])
        self.addCleanup(s.cleanup)
        code, out = s.build()
        self.assertEqual(code, 0, out)
        h = s.read("index.html")
        for x in ("lang-switch", "aviso-idioma", "idioma.js"):
            self.assertNotIn(x, h)


@unittest.skipUnless(HAS_PW and HAS_AXE, "faltan Playwright o axe-core (pip install playwright; npm ci)")
class Navegador(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = sitio()
        code, out = cls.s.build()
        assert code == 0, out
        (cls.s.dir / "node_modules").symlink_to(ROOT / "node_modules")
        cls.srv, cls.base = axe.serve(cls.s.dir / "public")
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.srv.shutdown()
        cls.s.cleanup()

    def page(self, locale, w=390):
        c = self.browser.new_context(viewport={"width": w, "height": 800}, locale=locale)
        self.addCleanup(c.close)
        p = c.new_page()
        p.route("**/*", lambda r: r.continue_() if r.request.url.startswith(self.base) else r.abort())
        errores = []
        p.on("pageerror", lambda e: errores.append(str(e)))
        self.addCleanup(lambda: self.assertEqual(errores, []))
        return p

    def ver(self, p, path):
        p.goto(self.base + path)
        p.wait_for_load_state("load")
        return p.is_visible(".aviso-idioma")

    def test_navegador_en_ingles_ve_el_aviso_y_puede_ir_a_la_version_inglesa(self):
        p = self.page("en-GB")
        self.assertTrue(self.ver(p, "/"))
        self.assertFalse(self.ver(p, "/en/"), "en su idioma no hay aviso")
        self.ver(p, "/")
        p.click(".aviso-idioma a")
        p.wait_for_url(self.base + "/en/")

    def test_navegador_en_espanol_no_ve_aviso_en_espanol_y_si_en_ingles(self):
        p = self.page("es-ES")
        self.assertFalse(self.ver(p, "/"))
        self.assertTrue(self.ver(p, "/en/"))
        self.assertIn("Ver en español", p.inner_text(".aviso-idioma"))

    def test_otro_idioma_que_la_web_no_tiene_no_ve_aviso(self):
        p = self.page("de-DE")
        self.assertFalse(self.ver(p, "/"))
        self.assertFalse(self.ver(p, "/en/"))

    def test_preferencia_por_orden(self):
        # Prefiere español antes que inglés: en la página española no se le avisa aunque también entienda inglés.
        c = self.browser.new_context(locale="es-ES", extra_http_headers={"Accept-Language": "es-ES,en;q=0.8"})
        self.addCleanup(c.close)
        p = c.new_page()
        p.add_init_script("Object.defineProperty(navigator, 'languages', {get: () => ['es-ES', 'en-GB']})")
        self.assertFalse(self.ver(p, "/"))
        p2 = self.page("en-GB")
        p2.add_init_script("Object.defineProperty(navigator, 'languages', {get: () => ['en-GB', 'es-ES']})")
        self.assertTrue(self.ver(p2, "/"))

    def test_cerrar_lo_oculta_el_resto_de_la_visita(self):
        p = self.page("en-GB")
        self.assertTrue(self.ver(p, "/"))
        p.click("[data-cerrar-idioma]")
        self.assertFalse(p.is_visible(".aviso-idioma"))
        self.assertFalse(self.ver(p, "/contacto/"), "no vuelve a salir al cambiar de página")

    def test_selector_visible_en_el_movil_sin_abrir_el_menu_y_sin_desbordar(self):
        for w in (320, 360, 1280):
            p = self.page("es-ES", w)
            p.goto(self.base + "/")
            self.assertTrue(p.is_visible(".lang-switch .lang"), w)
            self.assertLessEqual(p.evaluate("document.documentElement.scrollWidth"), w, w)
            alto = p.locator(".lang-switch .lang").bounding_box()["height"]
            self.assertGreaterEqual(alto, 24, "tamaño mínimo de objetivo [WCAG 2.5.8]")
            if w < 800:
                self.assertTrue(p.is_visible(".lang-corto"))
                self.assertGreaterEqual(alto, 44)
            nombre = p.evaluate("document.querySelector('.lang-switch .lang').textContent.trim()")
            self.assertIn("English", nombre)

    def test_axe_con_el_aviso_visible(self):
        # El contexto de axe usa el idioma por defecto de Chromium (inglés): en «/» el aviso está visible durante la revisión.
        self.assertEqual(axe.run([self.base + "/", self.base + "/en/"], local=True, browser=self.browser, viewport=(360, 800)), [])


if __name__ == "__main__":
    unittest.main()
