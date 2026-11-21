"""Medición y aviso de cookies: en el HTML generado y, si Playwright está instalado, en un navegador de verdad.

    python -m unittest discover -s tests -t . -v
"""
import functools
import http.server
import json
import threading
import unittest

from tests.test_build import Site

MED = {"ga4": "G-TEST12345", "google_ads": "AW-123456789", "meta_pixel": "1234567890", "politica_actualizada": "2026-10-16"}

try:
    from playwright.sync_api import sync_playwright  # noqa: F401
    HAS_PW = True
except ImportError:
    HAS_PW = False


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.sites = []

    def tearDown(self):
        for s in self.sites:
            s.cleanup()

    def site(self, **cfg) -> Site:
        s = Site(**cfg)
        self.sites.append(s)
        (s.dir / "content" / "es" / "productos.md").write_text("---\ntitle: Productos\ndescription: x\nnav: 10\n---\n\nTexto.\n", encoding="utf-8")
        return s

    def test_sin_medicion_no_hay_aviso_ni_cookies(self):
        s = self.site()
        self.assertEqual(s.build()[0], 0)
        home = s.read("index.html")
        self.assertNotIn("consent.js", home)
        self.assertNotIn("Configurar cookies", home)
        self.assertFalse((s.dir / "public" / "politica-cookies").exists())
        self.assertIn("no usa cookies", s.read("privacidad/index.html"))

    def test_con_medicion_aviso_politica_y_privacidad(self):
        s = self.site(medicion=MED)
        code, out = s.build()
        self.assertEqual(code, 0, out)
        home = s.read("index.html")
        self.assertIn('<script src="/consent.js" data-ga4="G-TEST12345" data-ads="AW-123456789" data-meta="1234567890" data-policy="/politica-cookies/" defer>', home)
        self.assertIn("data-consent-open", home, "enlace permanente para cambiar o retirar el consentimiento")
        for tracker in ("googletagmanager.com", "connect.facebook.net", "gtag(", "fbq("):
            self.assertNotIn(tracker, home, "ninguna etiqueta en el HTML: solo las carga consent.js tras aceptar")
        politica = s.read("politica-cookies/index.html")
        for cookie in ("_ga", "_gcl_au", "_fbp", "ltr_consent"):
            self.assertIn(cookie, politica)
        self.assertIn("noindex", politica)
        priv = s.read("privacidad/index.html")
        self.assertNotIn("no usa cookies", priv, "no se puede decir que no hay cookies")
        self.assertIn("Marco de Privacidad de Datos UE-EE. UU.", priv)
        self.assertIn("/en/cookie-policy/", s.read("en/index.html"))
        self.assertEqual(s.check()[0], 0, s.check()[1])

    def test_solo_las_herramientas_configuradas(self):
        s = self.site(medicion={"ga4": "G-TEST12345"})
        self.assertEqual(s.build()[0], 0)
        politica = s.read("politica-cookies/index.html")
        self.assertIn("_ga", politica)
        self.assertNotIn("_fbp", politica)
        self.assertNotIn("Meta (Facebook", s.read("privacidad/index.html"))

    def test_identificadores_no_validos_detienen_la_generacion(self):
        for bad in ({"ga4": "UA-12345-1"}, {"ga4": "G-<script>"}, {"google_ads": "123"}, {"meta_pixel": "abc\"onload=x"}):
            with self.subTest(bad=bad):
                s = self.site(medicion=bad)
                code, out = s.build()
                self.assertNotEqual(code, 0)
                self.assertIn("medicion", out)

    def test_check_detecta_etiquetas_puestas_a_mano(self):
        s = self.site()
        (s.dir / "content" / "es" / "sobre.md").write_text(
            '---\ntitle: Sobre\ndescription: x\n---\n\n<script async src="https://www.googletagmanager.com/gtag/js?id=G-X"></script>\n', encoding="utf-8")
        self.assertEqual(s.build()[0], 0)
        code, out = s.check()
        self.assertNotEqual(code, 0)
        self.assertIn("etiqueta de medición sin consentimiento", out)


    def test_remarketing_solo_si_se_pide_y_entonces_se_explica(self):
        s = self.site(medicion=MED)
        self.assertEqual(s.build()[0], 0)
        self.assertNotIn("data-remarketing", s.read("index.html"))
        self.assertNotIn("remarketing", s.read("privacidad/index.html"))
        s = self.site(medicion={**MED, "remarketing": True})
        code, out = s.build()
        self.assertEqual(code, 0, out)
        self.assertIn('data-meta="1234567890" data-remarketing="1"', s.read("index.html"))
        self.assertIn("mostrarte anuncios nuestros en otras webs y redes según tu visita (remarketing)", s.read("privacidad/index.html"))
        self.assertIn("(remarketing)", s.read("politica-cookies/index.html"))
        self.assertIn("(remarketing)", s.read("en/privacy/index.html"))
        s = self.site(medicion={"ga4": "G-TEST12345", "politica_actualizada": "2026-10-16", "remarketing": True})
        code, out = s.build()
        self.assertNotEqual(code, 0)
        self.assertIn("remarketing necesita google_ads o meta_pixel", out)

    def test_check_detecta_utm_en_enlaces_internos(self):
        s = self.site()
        (s.dir / "content" / "es" / "sobre.md").write_text(
            "---\ntitle: Sobre\ndescription: x\n---\n\n[Productos](/productos/?utm_source=web&utm_medium=banner) · "
            "[Instagram](https://www.instagram.com/x?utm_source=web) · [Contacto](@contacto)\n", encoding="utf-8")
        self.assertEqual(s.build()[0], 0)
        code, out = s.check()
        self.assertNotEqual(code, 0)
        self.assertIn("enlace interno con UTM", out)
        self.assertNotIn("instagram.com/x?utm_source=web): pisa", out, "a otra web, sí se puede")
        (s.dir / "content" / "es" / "sobre.md").write_text(
            "---\ntitle: Sobre\ndescription: x\n---\n\n[Productos](https://www.ejemplo-cliente.es/productos/?gclid=abc) · [Contacto](@contacto)\n", encoding="utf-8")
        self.assertEqual(s.build()[0], 0)
        self.assertIn("enlace interno con UTM", s.check()[1], "también con el dominio completo y con identificadores de clic")
        (s.dir / "content" / "es" / "sobre.md").write_text("---\ntitle: Sobre\ndescription: x\n---\n\n[Productos](/productos/) · [Contacto](@contacto)\n",
                                                          encoding="utf-8")
        self.assertEqual(s.build()[0], 0)
        self.assertNotIn("enlace interno con UTM", s.check()[1])


FORM_JS = ("() => { const f = document.createElement('form'); f.className = 'contact-form'; f.addEventListener('submit', e => e.preventDefault()); "
           "document.body.appendChild(f); f.requestSubmit(); return Object.fromEntries([...f.querySelectorAll('input')].map(i => [i.name, i.value])); }")


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


@unittest.skipUnless(HAS_PW, "Playwright no instalado (pip install playwright && python -m playwright install chromium)")
class BrowserTests(unittest.TestCase):
    """El aviso en un navegador real: nada de Google ni Meta antes de aceptar; rechazar es igual de fácil; retirar borra las cookies."""

    @classmethod
    def setUpClass(cls):
        cls.site = Site(medicion=MED)
        (cls.site.dir / "content" / "es" / "productos.md").write_text("---\ntitle: Productos\ndescription: x\nnav: 10\n---\n\nTexto.\n", encoding="utf-8")
        assert cls.site.build()[0] == 0
        handler = functools.partial(_Quiet, directory=str(cls.site.dir / "public"))
        cls.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.httpd.shutdown()
        cls.site.cleanup()

    def page(self):
        ctx = self.browser.new_context()
        page = ctx.new_page()
        third = []
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        # Las etiquetas reales no se descargan: se responde con un script vacío y se apunta la petición.
        page.route("**/*", lambda r: (third.append(r.request.url), r.fulfill(status=200, content_type="text/javascript", body=""))
                   if not r.request.url.startswith(self.base) else r.continue_())
        self.addCleanup(ctx.close)
        return page, third, errors

    def test_nada_se_carga_antes_de_elegir_y_rechazar_es_igual_de_facil(self):
        page, third, errors = self.page()
        page.goto(self.base + "/?utm_source=newsletter&utm_campaign=otono")
        banner = page.locator(".consent")
        banner.wait_for()
        self.assertEqual(third, [], "ninguna petición a terceros antes de elegir")
        acc = page.locator('[data-consent="accept"]')
        rej = page.locator('[data-consent="reject"]')
        self.assertEqual(acc.get_attribute("class"), rej.get_attribute("class"), "mismo aspecto para aceptar y rechazar")
        box_a, box_r = acc.bounding_box(), rej.bounding_box()
        self.assertAlmostEqual(box_a["height"], box_r["height"], delta=1)
        rej.click()
        page.wait_for_timeout(300)
        self.assertEqual(third, [])
        self.assertEqual(page.evaluate("sessionStorage.getItem('ltr_attr')"), None, "sin consentimiento no se guarda el origen")
        page.goto(self.base + "/sobre/")
        page.wait_for_timeout(300)
        self.assertEqual(page.locator(".consent").count(), 0, "la elección se recuerda")
        self.assertEqual(third, [])
        self.assertEqual(errors, [])

    def test_aceptar_carga_las_etiquetas_y_guarda_el_origen(self):
        page, third, errors = self.page()
        page.goto(self.base + "/?utm_source=newsletter&utm_campaign=otono&gclid=abc&wbraid=CkKAAA_wb")
        page.locator('[data-consent="accept"]').click()
        page.wait_for_timeout(500)
        self.assertTrue(any("googletagmanager.com/gtag/js?id=G-TEST12345" in u for u in third), third)
        self.assertTrue(any("connect.facebook.net" in u for u in third), third)
        attr = json.loads(page.evaluate("sessionStorage.getItem('ltr_attr')"))
        self.assertEqual(attr["utm_campaign"], "otono")
        self.assertEqual(attr["gclid"], "abc")
        self.assertEqual(attr["wbraid"], "CkKAAA_wb", "clics de Google desde iPhone")
        consent_calls = page.evaluate("JSON.stringify(window.dataLayer.filter(a => a[0] === 'consent'))")
        self.assertIn('"default"', consent_calls)
        self.assertIn('"analytics_storage":"granted"', consent_calls)
        self.assertEqual(errors, [])

    def test_sin_remarketing_la_publicidad_solo_mide(self):
        page, third, errors = self.page()
        page.goto(self.base + "/")
        self.assertNotIn("remarketing", page.locator(".consent").inner_text())
        page.locator('[data-consent="accept"]').click()
        page.wait_for_timeout(300)
        calls = page.evaluate("JSON.stringify(window.dataLayer.filter(a => a[0] === 'consent' || a[0] === 'config'))")
        self.assertIn('"ad_user_data":"granted","ad_personalization":"denied"', calls)
        self.assertIn('"1":"AW-123456789","2":{"allow_ad_personalization_signals":false}', calls)
        self.assertIsNone(page.evaluate("JSON.parse(localStorage.getItem('ltr_consent')).rmk || null"))
        sent = page.evaluate(FORM_JS)
        self.assertEqual(sent.get("consent_publicidad"), "yes")
        self.assertNotIn("consent_remarketing", sent, "el servidor no lo usa para anuncios personalizados")
        self.assertEqual(errors, [])

    def test_con_remarketing_se_vuelve_a_preguntar_y_se_activa_al_aceptar(self):
        ctx = self.browser.new_context()
        self.addCleanup(ctx.close)
        page = ctx.new_page()
        errors, posts = [], []
        page.on("pageerror", lambda e: errors.append(str(e)))

        def route(r):
            url = r.request.url
            if not url.startswith(self.base):
                return r.fulfill(status=200, content_type="text/javascript", body="")
            resp = r.fetch()
            if "text/html" not in resp.headers.get("content-type", ""):
                return r.fulfill(response=resp)  # fuentes e imágenes son binarias: tal cual
            body = resp.text().replace('data-meta="1234567890"', 'data-meta="1234567890" data-remarketing="1"')
            return r.fulfill(response=resp, body=body)
        page.route("**/*", route)
        # Alguien aceptó la publicidad cuando la web no hacía remarketing: ese «sí» no lo cubre.
        page.add_init_script("if (!sessionStorage.getItem('x')) { sessionStorage.setItem('x', '1'); localStorage.setItem('ltr_consent', "
                             "JSON.stringify({ v: 1, analitica: true, publicidad: true, at: new Date().toISOString() })); }")
        page.goto(self.base + "/")
        self.assertTrue(page.locator(".consent").is_visible(), "se vuelve a preguntar")
        self.assertIn("mostrarte anuncios nuestros", page.locator(".consent").inner_text())
        page.locator('[data-consent="config"]').click()
        self.assertIn("(remarketing)", page.locator(".consent-options").inner_text())
        page.locator('[data-consent="accept"]').click()
        page.wait_for_timeout(300)
        calls = page.evaluate("JSON.stringify(window.dataLayer.filter(a => a[0] === 'consent' || a[0] === 'config'))")
        self.assertIn('"ad_personalization":"granted"', calls)
        self.assertIn('"1":"AW-123456789","2":{"allow_ad_personalization_signals":true}', calls)
        self.assertTrue(page.evaluate("JSON.parse(localStorage.getItem('ltr_consent')).rmk"))
        self.assertEqual(page.evaluate(FORM_JS).get("consent_remarketing"), "yes")
        self.assertEqual(errors, [])

    def submit_contact(self, page, posts):
        page.goto(self.base + "/contacto/")
        page.fill('input[name="name"]', "Ana")
        page.fill('input[name="email"]', "ana@example.com")
        page.fill('textarea[name="message"]', "Hola")
        page.check('input[name="consent"]')
        page.click("form.contact-form button[type=submit]")
        page.wait_for_timeout(400)
        return posts[-1] if posts else ""

    def test_el_formulario_lleva_origen_y_consentimiento_solo_si_se_acepto(self):
        for choice, expect in (("accept", True), ("reject", False)):
            with self.subTest(choice=choice):
                page, third, errors = self.page()
                posts = []
                page.route("**/api/contact", lambda r: (posts.append(r.request.post_data or ""), r.fulfill(status=200, body="ok")))
                page.goto(self.base + "/?utm_source=newsletter&utm_campaign=otono")
                page.locator(f'[data-consent="{choice}"]').click()
                body = self.submit_contact(page, posts)
                self.assertIn("name=Ana", body)
                if expect:
                    self.assertIn("utm_campaign=otono", body)
                    self.assertIn("consent_analitica=yes", body)
                else:
                    self.assertNotIn("utm_", body, "sin consentimiento no se envía el origen")
                    self.assertNotIn("consent_analitica=yes", body)

    def test_configurar_solo_analitica_y_retirar_despues(self):
        page, third, errors = self.page()
        page.goto(self.base + "/")
        page.locator('[data-consent="config"]').click()
        analitica = page.locator('input[name="analitica"]')
        publicidad = page.locator('input[name="publicidad"]')
        self.assertFalse(analitica.is_checked(), "nada marcado por defecto")
        self.assertFalse(publicidad.is_checked())
        analitica.check()
        page.locator('[data-consent="save"]').click()
        page.wait_for_timeout(400)
        self.assertTrue(any("googletagmanager.com" in u for u in third))
        self.assertFalse(any("facebook" in u for u in third), "sin publicidad no hay Meta")
        # Simula la cookie de Analytics y retira el consentimiento desde el pie.
        page.evaluate("document.cookie = '_ga=GA1.1.123.456; path=/'")
        page.locator("footer [data-consent-open]").click()
        page.locator('[data-consent="reject"]').click()
        page.wait_for_load_state()
        page.wait_for_timeout(300)
        self.assertNotIn("_ga=", page.evaluate("document.cookie"), "al retirarlo se borran las cookies de análisis")
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
