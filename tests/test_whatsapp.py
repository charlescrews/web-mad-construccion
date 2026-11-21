"""WhatsApp (skill whatsapp-cliente): enlace al WhatsApp del negocio y casilla de avisos del pedido.

Protecciones con test: la casilla nunca viene marcada; el móvil solo se pide si se marca (y el navegador lo dice en el campo);
el enlace es un enlace (nada de Meta se carga sin que la persona escriba); número mal escrito = la web no se genera; con avisos,
la política de privacidad lo explica y la entrega exige declarar a Meta como encargado.
"""
import json
import unittest

from tests.test_build import PRODUCTS, Site

try:
    from playwright.sync_api import sync_playwright
    HAS_PW = True
except ImportError:
    HAS_PW = False

BUY = {"api": "https://api.cliente.es", "comprar": True}


class WhatsApp(unittest.TestCase):
    def setUp(self):
        self.sites = []

    def tearDown(self):
        for s in self.sites:
            s.cleanup()

    def site(self, whatsapp_num=None, **cfg) -> Site:
        s = Site(products=PRODUCTS, catalog=BUY, **cfg)
        self.sites.append(s)
        if whatsapp_num is not None:
            d = json.loads((s.dir / "site.json").read_text(encoding="utf-8"))
            d["company"]["whatsapp"] = whatsapp_num
            (s.dir / "site.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        return s

    def test_sin_whatsapp_nada_cambia(self):
        s = self.site()
        self.assertEqual(s.build()[0], 0)
        self.assertNotIn("consent_whatsapp", s.read("productos/hogaza/index.html"))
        self.assertNotIn("wa.me", s.read("contacto/index.html"))
        self.assertNotIn("WhatsApp", s.read("privacidad/index.html"))

    def test_casilla_de_avisos_sin_marcar_y_privacidad(self):
        s = self.site(whatsapp={"avisos": True, "aviso_version": "pedido-v2"})
        code, out = s.build()
        self.assertEqual(code, 0, out)
        ficha = s.read("productos/hogaza/index.html")
        self.assertIn('<input type="checkbox" name="consent_whatsapp" value="yes">', ficha)
        self.assertNotRegex(ficha, r'name="consent_whatsapp"[^>]*checked', "nunca marcada por defecto")
        self.assertIn('<input type="hidden" name="aviso_whatsapp" value="pedido-v2">', ficha)
        self.assertRegex(ficha, r'<label class="wa-phone">Móvil para los avisos por WhatsApp<input type="tel" name="whatsapp"')
        self.assertNotRegex(ficha, r'name="whatsapp"[^>]*required', "el móvil no es obligatorio si no se marca la casilla")
        self.assertIn("respondiendo BAJA", ficha)
        priv = s.read("privacidad/index.html")
        self.assertIn("<strong>Avisos por WhatsApp.</strong>", priv)
        self.assertIn("Nunca te enviaremos publicidad por WhatsApp", priv)
        self.assertIn("<strong>WhatsApp updates.</strong>", s.read("en/privacy/index.html"))

    def test_entrega_exige_a_meta_como_encargado(self):
        enc = [{"servicio": "alojamiento", "nombre": "Proveedor", "pais": "España"}, {"servicio": "email", "nombre": "Correo", "pais": "España"},
               {"servicio": "pagos", "nombre": "Pasarela", "pais": "Irlanda"}]
        s = self.site(whatsapp={"avisos": True}, privacidad={"encargados": enc})
        self.assertEqual(s.build()[0], 0)
        r = __import__("subprocess").run(["python3", "-B", "tools/check.py", "--release"], cwd=s.dir, capture_output=True, text=True)
        self.assertIn("sin el servicio «whatsapp»", r.stdout)
        s2 = self.site(whatsapp={"avisos": True}, privacidad={"encargados": enc + [{"servicio": "whatsapp", "nombre": "Meta Platforms Ireland Ltd.", "pais": "Irlanda"}]})
        self.assertEqual(s2.build()[0], 0)
        r2 = __import__("subprocess").run(["python3", "-B", "tools/check.py", "--release"], cwd=s2.dir, capture_output=True, text=True)
        self.assertNotIn("«whatsapp»", r2.stdout)
        self.assertIn("mensajería por WhatsApp (Meta) (Meta Platforms Ireland Ltd., Irlanda)", s2.read("privacidad/index.html"))

    def test_enlace_al_whatsapp_del_negocio(self):
        s = self.site(whatsapp_num="+34 600 123 456")
        code, out = s.build()
        self.assertEqual(code, 0, out)
        contacto = s.read("contacto/index.html")
        self.assertIn('<a href="https://wa.me/34600123456">+34 600 123 456<span class="sr"> (abre WhatsApp)</span></a>', contacto)
        self.assertNotRegex(contacto, r'<(script|iframe|img)[^>]+(whatsapp|wa\.me|facebook)', "un enlace, nada que se cargue solo")
        self.assertIn("<strong>Si nos escribes por WhatsApp.</strong>", s.read("privacidad/index.html"))
        code, out = s.check()
        self.assertEqual(code, 0, out)

    def test_numero_o_version_no_validos_paran_la_web(self):
        for num in ("600 123", "+34600123456<script>", "whatsapp"):
            s = self.site(whatsapp_num=num)
            code, out = s.build()
            self.assertNotEqual(code, 0, num)
            self.assertIn("company.whatsapp no válido", out)
        s = self.site(whatsapp={"avisos": True, "aviso_version": "v1\"><script>"})
        code, out = s.build()
        self.assertNotEqual(code, 0)
        self.assertIn("whatsapp.aviso_version no válido", out)

    @unittest.skipUnless(HAS_PW, "falta Playwright")
    def test_marcar_la_casilla_pide_el_movil_en_el_campo(self):
        import functools
        import http.server
        import threading
        s = self.site(whatsapp={"avisos": True})
        self.assertEqual(s.build()[0], 0)
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a):
                pass
        h = functools.partial(Quiet, directory=str(s.dir / "public"))
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        enviados = []
        try:
            with sync_playwright() as p:
                b = p.chromium.launch()
                page = b.new_page()
                page.route("https://api.cliente.es/**", lambda r: (enviados.append(r.request.url), r.fulfill(status=200, body="{}")))
                page.goto(f"http://127.0.0.1:{srv.server_address[1]}/productos/hogaza/")
                form = page.locator("form.buy")
                box = form.locator("input[name=consent_whatsapp]").bounding_box()
                self.assertGreaterEqual(min(box["width"], box["height"]), 16, f"la casilla se ve y se pulsa bien: {box}")
                form.locator("input[name=consent_whatsapp]").check()
                self.assertTrue(form.locator("input[name=whatsapp]").evaluate("e => e.required"))
                form.locator("button[type=submit]").click()
                page.wait_for_timeout(300)
                self.assertFalse([u for u in enviados if u.endswith("/api/checkout")], "sin móvil no se envía el pedido")
                self.assertEqual(page.evaluate("document.activeElement.name"), "whatsapp", "el foco va al campo que falta")
                self.assertFalse(form.locator("input[name=whatsapp]").evaluate("e => e.validity.valid"))
                form.locator("input[name=consent_whatsapp]").uncheck()
                self.assertFalse(form.locator("input[name=whatsapp]").evaluate("e => e.required"), "sin casilla, el móvil no es obligatorio")
                b.close()
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
