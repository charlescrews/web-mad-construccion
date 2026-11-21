"""Pedido preparado por el asistente (site.json > catalog.asistente; skill asistente-conectado-cliente).

    python -m unittest tests.test_asistente -v
"""
import json
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs

from tests.test_build import PRODUCTS, Site

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import axe  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
    HAS_PW = True
except ImportError:
    HAS_PW = False
HAS_AXE = (ROOT / "node_modules" / "axe-core" / "axe.min.js").exists()

SHOP = {"api": "https://api.cliente.es", "comprar": True, "asistente": True,
        "envio": [{"id": "recogida", "nombre": "Recogida en tienda"}, {"id": "envio", "nombre": "Envío"}]}
BOT = {"script": "https://bots.cliente.es/widget.js", "bot": "la-espiga", "conservacion_dias": 0, "transferencia": "Cláusulas contractuales tipo"}
PID = "AbCdEfGhIjKlMnOpQrStUv"


class Build(unittest.TestCase):
    def setUp(self):
        self.sites = []

    def tearDown(self):
        for s in self.sites:
            s.cleanup()

    def site(self, **k) -> Site:
        s = Site(**k)
        self.sites.append(s)
        return s

    def test_pagina_del_pedido_preparado(self):
        s = self.site(products=PRODUCTS, catalog=SHOP, chatbot=BOT)
        code, out = s.build()
        self.assertEqual(code, 0, out)
        p = s.read("pedido/index.html")
        self.assertIn('<meta name="robots" content="noindex, follow">', p, "no se indexa")
        self.assertIn('<form class="buy" action="https://api.cliente.es/api/checkout" method="post">', p)
        self.assertIn('<input type="hidden" name="propuesta" value="">', p)
        self.assertIn('<select name="envio">', p, "mismo método de entrega que la ficha")
        self.assertIn('data-api="https://api.cliente.es"', p)
        self.assertIn('<script src="/catalogo.js" defer>', p)
        self.assertIn("no está hecho ni pagado hasta que pagues", p)
        self.assertNotIn("/pedido/", s.read("sitemap.xml"))
        priv = s.read("privacidad/index.html")
        self.assertIn("código aleatorio, sin datos personales", priv)
        self.assertIn("sin pasar por la inteligencia artificial", priv)
        self.assertEqual(s.check()[0], 0, s.check()[1])

    def test_sin_compra_no_hay_pedido_preparado(self):
        s = self.site(products=PRODUCTS, catalog={"api": "https://api.cliente.es", "asistente": True})
        code, out = s.build()
        self.assertNotEqual(code, 0)
        self.assertIn("catalog.asistente necesita", out)
        s2 = self.site(products=PRODUCTS, catalog={"api": "https://api.cliente.es", "comprar": True}, chatbot=BOT)
        self.assertEqual(s2.build()[0], 0)
        self.assertFalse((s2.dir / "public" / "pedido").exists(), "sin asistente: la web de siempre")
        self.assertNotIn("código aleatorio", s2.read("privacidad/index.html"))

    def test_check_avisa_si_no_hay_asistente_que_lo_use(self):
        s = self.site(products=PRODUCTS, catalog=SHOP)
        self.assertEqual(s.build()[0], 0)
        code, out = s.check()
        self.assertIn("catalog.asistente sin chatbot", out)


class DatosParaElAsistente(unittest.TestCase):
    """/asistente.json y los cierres (mejora 4 de los asistentes: conocimiento al día desde la web)."""
    HOY = {"LTR_HOY": "2026-12-20"}
    CIERRES = [{"desde": "2026-11-01", "motivo": {"es": "Todos los Santos"}},
               {"desde": "2026-12-24", "hasta": "2026-12-26", "motivo": {"es": "Navidad", "en": "Christmas"}},
               {"desde": "2027-08-01", "hasta": "2027-08-15", "motivo": "Vacaciones"}]

    def setUp(self):
        self.sites = []

    def tearDown(self):
        for s in self.sites:
            s.cleanup()

    def site(self, cierres=None, **k) -> Site:
        s = Site(**k)
        site = json.loads((s.dir / "site.json").read_text(encoding="utf-8"))
        site["company"]["cierres"] = cierres if cierres is not None else self.CIERRES
        (s.dir / "site.json").write_text(json.dumps(site, ensure_ascii=False), encoding="utf-8")
        (s.dir / "content" / "es" / "oculta.md").write_text("---\ntitle: Oculta\ndescription: x\nnoindex: true\n---\n\nTexto interno.\n", encoding="utf-8")
        self.sites.append(s)
        return s

    def test_asistente_json_solo_con_lo_publicado(self):
        s = self.site(products=PRODUCTS, chatbot=BOT)
        code, out = s.build(self.HOY)
        self.assertEqual(code, 0, out)
        d = json.loads(s.read("asistente.json"))
        self.assertEqual(d["generado"], "2026-12-20")
        self.assertEqual([c["desde"] for c in d["cierres"]], ["2026-12-24", "2027-08-01"], "los cierres pasados no van")
        self.assertEqual(d["cierres"][1]["motivo"], {"es": "Vacaciones"})
        self.assertEqual(d["empresa"]["horario"]["es"], "Lunes a sábado, de 7:30 a 14:00")
        self.assertEqual({p["sku"] for p in d["productos"]}, {"hogaza", "agotado", "suelto"})
        claves = {p["clave"] for p in d["paginas"] if p["idioma"] == "es"}
        self.assertIn("home", claves)
        self.assertNotIn("oculta", claves, "lo que no se indexa tampoco va al asistente")
        txt = json.dumps(d, ensure_ascii=False)
        for privado in ("B00000000", "Registro Mercantil", ":::", "![", "@productos"):
            self.assertNotIn(privado, txt)
        s2 = self.site(products=PRODUCTS)
        self.assertEqual(s2.build(self.HOY)[0], 0)
        self.assertFalse((s2.dir / "public" / "asistente.json").exists(), "sin asistente, no se publica")

    def test_cierres_en_el_contacto_y_avisos(self):
        s = self.site(products=PRODUCTS, chatbot=BOT)
        self.assertEqual(s.build(self.HOY)[0], 0)
        c = s.read("contacto/index.html")
        self.assertIn("<dt>Próximos cierres</dt><dd>24 de diciembre – 26 de diciembre: Navidad</dd></dl>", c, "solo los de los próximos 90 días")
        self.assertNotIn("Todos los Santos", c)
        self.assertIn("Upcoming closures", s.read("en/contact/index.html"))
        code, out = s.check(self.HOY)
        self.assertIn("el cierre que acabó el 2026-11-01 ya pasó", out)
        for bad in ([{"desde": "24/12/2026"}], [{"desde": "2026-12-26", "hasta": "2026-12-24"}]):
            code, out = self.site(cierres=bad, products=PRODUCTS).build(self.HOY)
            self.assertNotEqual(code, 0)
            self.assertIn("company.cierres[0]", out)


class CierresDelPanel(unittest.TestCase):
    """company.cierres_api: los cierres que el negocio apunta en el panel de la plantilla C."""

    def setUp(self):
        import http.server
        import threading
        body = json.dumps({"ok": True, "cierres": [
            {"desde": "2026-12-24", "hasta": "2026-12-26", "motivo": {"es": "Navidad", "en": "Christmas"}},
            {"desde": "2027-01-06", "hasta": "2027-01-06", "motivo": {"es": "Reyes", "xx": "<script>"}}]}).encode()

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}/api/cierres"
        self.sites = []

    def tearDown(self):
        self.srv.shutdown()
        for s in self.sites:
            s.cleanup()

    def site(self, api: str, cierres=None) -> Site:
        s = Site(products=PRODUCTS, chatbot=BOT)
        site = json.loads((s.dir / "site.json").read_text(encoding="utf-8"))
        site["company"]["cierres_api"] = api
        site["company"]["cierres"] = cierres or []
        (s.dir / "site.json").write_text(json.dumps(site, ensure_ascii=False), encoding="utf-8")
        self.sites.append(s)
        return s

    def test_cierres_del_panel_en_la_web_y_en_asistente_json(self):
        s = self.site(self.url, [{"desde": "2026-12-24", "hasta": "2026-12-26", "motivo": {"es": "Navidad"}}])
        code, out = s.build({"LTR_HOY": "2026-12-01"})
        self.assertEqual(code, 0, out)
        c = s.read("contacto/index.html")
        self.assertEqual(c.count("Navidad"), 1, "el mismo cierre en site.json y en el panel sale una vez")
        self.assertIn("6 de enero: Reyes", c)
        d = json.loads(s.read("asistente.json"))
        self.assertEqual([x["desde"] for x in d["cierres"]], ["2026-12-24", "2027-01-06"])
        self.assertNotIn("<script>", json.dumps(d), "solo los idiomas de la web")

    def test_sin_cierres_no_se_publica(self):
        self.srv.shutdown()
        self.srv.server_close()
        code, out = self.site(self.url).build({"LTR_HOY": "2026-12-01"})
        self.assertNotEqual(code, 0)
        self.assertIn("no se pudieron leer los cierres", out)
        code, out = self.site("http://api.cliente.es/api/cierres").build()
        self.assertIn("cierres_api debe ser https", out)


@unittest.skipUnless(HAS_PW and HAS_AXE, "faltan Playwright o axe-core (pip install playwright; npm ci)")
class Navegador(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = Site(products=PRODUCTS, catalog=SHOP, chatbot=BOT,
                     accesibilidad={"estado": "total", "fecha_evaluacion": "2026-10-18", "descripcion_servicio": "Pan por encargo."})
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

    def page(self, proposal_status=200, body=None):
        c = self.browser.new_context()
        self.addCleanup(c.close)
        self.posted = []
        self.errors = []

        def route(r):
            u = r.request.url
            if u.startswith(self.base):
                return r.continue_()
            if u == f"https://api.cliente.es/api/asistente/propuestas/{PID}":
                return r.fulfill(status=proposal_status, content_type="application/json", headers={"access-control-allow-origin": "*"},
                                 body=json.dumps(body if body is not None else {
                                     "ok": True, "tipo": "cesta", "moneda": "eur", "total_cents": 1380,
                                     "lineas": [{"sku": "hogaza", "nombre": "Hogaza <b>de</b> trigo", "cantidad": 2, "precio_cents": 450, "total_cents": 900},
                                                {"sku": "suelto", "nombre": "Sin categoría", "cantidad": 3, "precio_cents": 160, "total_cents": 480}]}))
            if u == "https://api.cliente.es/api/checkout":
                self.posted.append(r.request.post_data)
                return r.fulfill(status=200, content_type="text/html", body="<!doctype html><title>Pago</title><p>pago</p>")
            if u == "https://bots.cliente.es/widget.js":  # el widget del asistente tiene sus propias pruebas (plantilla-bot)
                return r.fulfill(status=200, content_type="text/javascript", body="")
            return r.abort()
        c.route("**/*", route)
        c.add_init_script("try{localStorage.setItem('ltr_consent', JSON.stringify({v: 1, analitica: false, publicidad: false, at: new Date().toISOString()}))}catch(e){}")
        p = c.new_page()
        p.on("console", lambda m: self.errors.append(m.text) if m.type == "error" else None)
        p.on("pageerror", lambda e: self.errors.append(str(e)))
        return p

    def test_pinta_la_propuesta_y_paga_con_sus_productos_y_su_id(self):
        p = self.page()
        p.goto(f"{self.base}/pedido/?propuesta={PID}")
        p.locator(".prepared-order:not([hidden])").wait_for()
        lines = p.locator(".prepared-lines li").all_text_contents()
        self.assertEqual([x.replace(" ", " ") for x in lines], ["2 × Hogaza <b>de</b> trigo · 9,00 €", "3 × Sin categoría · 4,80 €"], "texto, nunca HTML")
        self.assertEqual(p.locator(".prepared-total").text_content().replace(" ", " "), "13,80 €")
        # axe sobre la página ya rellena (con la propuesta pintada y el formulario visible), no sobre la vacía.
        p.add_script_tag(content=axe.AXE.read_text(encoding="utf-8"))
        res = p.evaluate("tags => axe.run(document, {runOnly: {type: 'tag', values: tags}, resultTypes: ['violations']})", axe.TAGS)
        self.assertEqual([(v["id"], v["help"]) for v in res["violations"]], [])
        p.locator("form.buy button[type=submit]").click()
        p.wait_for_url("https://api.cliente.es/api/checkout")
        sent = parse_qs(self.posted[0])
        self.assertEqual(sent["sku"], ["hogaza", "suelto"])
        self.assertEqual(sent["qty"], ["2", "3"])
        self.assertEqual(sent["propuesta"], [PID])
        self.assertEqual(sent["envio"], ["recogida"])
        self.assertEqual(self.errors, [])

    def test_caducada_inventada_o_sin_conexion_lleva_al_catalogo(self):
        for status, url, attr in ((404, f"/pedido/?propuesta={PID}", "data-gone"), (200, "/pedido/?propuesta=corta", "data-none"),
                                  (500, f"/pedido/?propuesta={PID}", "data-error"), (200, "/pedido/", "data-none")):
            p = self.page(proposal_status=status, body={"ok": False} if status != 200 else None)
            p.goto(self.base + url)
            want = p.locator("section.prepared").get_attribute(attr)
            p.wait_for_function("w => document.querySelector('section.prepared .status').textContent === w", arg=want)
            self.assertTrue(p.locator(".prepared-order").is_hidden(), url)
            self.assertEqual(p.locator("section.prepared a[href='/productos/']").count(), 1)

    def test_320_px_sin_desplazamiento_horizontal(self):
        p = self.page()
        p.set_viewport_size({"width": 320, "height": 640})
        p.goto(f"{self.base}/pedido/?propuesta={PID}")
        p.locator(".prepared-order:not([hidden])").wait_for()
        self.assertFalse(p.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth + 1"))


if __name__ == "__main__":
    unittest.main()
