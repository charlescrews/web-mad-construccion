"""RGPD técnico en la web: plazos y encargados en la política, información básica junto a cada formulario y nada de terceros sin consentimiento.

    python -m unittest discover -s tests -t . -v
"""
import re
import unittest

from tests.test_build import PRODUCTS, Site

SHOP = {"api": "https://api.cliente.es", "comprar": True}
COMPLETE = [
    {"servicio": "alojamiento", "nombre": "Proveedor VPS", "pais": "Alemania"},
    {"servicio": "email", "nombre": "Proveedor SMTP", "pais": "Francia"},
    {"servicio": "pagos", "nombre": "Pasarela", "pais": "Irlanda"},
    {"servicio": "mantenimiento", "nombre": "La Taza Roja", "pais": "España"},
]


class PrivacyTests(unittest.TestCase):
    def setUp(self):
        self.sites = []

    def tearDown(self):
        for s in self.sites:
            s.cleanup()

    def site(self, privacidad=None, page_html: str = "", css: str = "", products=PRODUCTS, **kw) -> Site:
        cfg = {"privacidad": privacidad} if privacidad is not None else {}
        s = Site(products=products, **cfg, **kw)
        self.sites.append(s)
        if page_html:
            (s.dir / "content" / "es" / "video.md").write_text(f"---\ntitle: Vídeo\ndescription: Vídeo\n---\n\n{page_html}\n", encoding="utf-8")
        if css:
            with (s.dir / "static" / "style.css").open("a", encoding="utf-8") as f:
                f.write("\n" + css + "\n")
        return s

    def built(self, s: Site) -> Site:
        code, out = s.build()
        self.assertEqual(code, 0, out)
        return s

    def test_politica_con_plazos_encargados_y_transferencias(self):
        enc = COMPLETE + [{"servicio": "medicion", "nombre": "Analítica Inc.", "pais": "EE. UU.", "garantia": "Marco de Privacidad de Datos UE-EE. UU."}]
        s = self.built(self.site({"contacto_meses": 18, "pedidos_anios": 7, "encargados": enc}, catalog=SHOP))
        priv = s.read("privacidad/index.html")
        self.assertIn("Conservamos el mensaje 18 meses", priv)
        self.assertIn("7 años desde el cierre del año", priv)
        self.assertIn("pasarela de pago (Pasarela, Irlanda)", priv)
        self.assertIn("mantenimiento técnico de la web (La Taza Roja, España)", priv)
        self.assertIn("Analítica Inc. (EE. UU.): Marco de Privacidad de Datos UE-EE. UU.", priv)
        self.assertNotIn("Proveedor SMTP (Francia):", priv, "solo las transferencias fuera del EEE")
        self.assertIn("en el plazo de un mes", priv)
        self.assertIn("retirarlo cuando quieras", priv)
        en = s.read("en/privacy/index.html")
        self.assertIn("for 18 months", en)
        self.assertIn("payment gateway (Pasarela, Irlanda)", en)

    def test_transferencia_sin_garantia_se_marca_y_todo_en_la_ue_no_la_menciona(self):
        s = self.built(self.site({"encargados": COMPLETE + [{"servicio": "email", "nombre": "Correo Corp", "pais": "EE. UU."}]}))
        self.assertIn("Correo Corp (EE. UU.): [CONFIRMAR", s.read("privacidad/index.html"))
        s2 = self.built(self.site({"encargados": COMPLETE}))
        self.assertNotIn("Transferencias internacionales", s2.read("privacidad/index.html"))

    def test_proveedores_de_ia_nombrados_principal_y_respaldo_y_transferencia_solo_si_salen_del_eee(self):
        bot = {"script": "https://bots.lataza.es/widget.js", "bot": "x", "transferencia": "cláusulas contractuales tipo"}
        ue = [{"nombre": "Amazon Web Services (Amazon Bedrock)", "pais": "UE (Alemania)"}, {"nombre": "Google Cloud (Vertex AI)", "pais": "UE"}]
        s = self.built(self.site({"encargados": COMPLETE}, chatbot={**bot, "proveedores_ia": ue}))
        priv = s.read("privacidad/index.html")
        self.assertIn("con Amazon Web Services (Amazon Bedrock) (UE (Alemania)) y Google Cloud (Vertex AI) (UE) como proveedores de inteligencia "
                      "artificial y subencargados (el segundo solo responde si el primero no está disponible); los datos se tratan dentro del "
                      "Espacio Económico Europeo.", priv)
        self.assertNotIn("transferencia internacional de datos: cláusulas", priv, "todo en el EEE: no hay transferencia")
        self.assertIn("the data is processed within the European Economic Area", s.read("en/privacy/index.html"))
        # Con el respaldo fuera del EEE, transferencia (y sin garantía, [CONFIRMAR]).
        fuera = [ue[0], {"nombre": "Anthropic", "pais": "EE. UU."}]
        s2 = self.built(self.site({"encargados": COMPLETE}, chatbot={**bot, "proveedores_ia": fuera}))
        self.assertIn("y Anthropic (EE. UU.) como proveedores de inteligencia artificial", s2.read("privacidad/index.html"))
        self.assertIn("transferencia internacional de datos: cláusulas contractuales tipo.", s2.read("privacidad/index.html"))
        s3 = self.built(self.site({"encargados": COMPLETE}, chatbot={**bot, "transferencia": "", "proveedores_ia": [fuera[1]]}))
        self.assertIn("con Anthropic (EE. UU.) como proveedor de inteligencia artificial y subencargado; esto puede implicar una transferencia "
                      "internacional de datos: [CONFIRMAR", s3.read("privacidad/index.html"))
        # Sin nombrarlos, como antes, y check.py lo recuerda.
        s4 = self.built(self.site({"encargados": COMPLETE}, chatbot=bot))
        self.assertIn("con un proveedor de inteligencia artificial como subencargado; esto puede implicar", s4.read("privacidad/index.html"))
        self.assertIn("chatbot.proveedores_ia vacío", s4.check()[1])
        self.assertNotIn("proveedores_ia vacío", s.check()[1])
        # Teléfono: la plataforma de telefonía y los proveedores nombrados.
        s5 = self.built(self.site({"encargados": COMPLETE}, chatbot={**bot, "proveedores_ia": ue}, asistente_voz={"activo": True}))
        self.assertIn("con la plataforma de telefonía como subencargado y Amazon Web Services (Amazon Bedrock) (UE (Alemania)) y Google Cloud",
                      s5.read("privacidad/index.html"))
        self.assertIn("(el segundo solo responde si el primero no está disponible); esto puede implicar una transferencia internacional",
                      s5.read("privacidad/index.html"), "la telefonía sale del EEE aunque la IA no")
        for malo in ([{"nombre": "X"}], [{"nombre": "X", "pais": " "}], {"nombre": "X", "pais": "UE"}):
            code, out = self.site(chatbot={**bot, "proveedores_ia": malo}).build()
            self.assertNotEqual(code, 0, malo)
            self.assertIn("chatbot.proveedores_ia: lista de {nombre, pais}", out)

    def test_plazos_y_encargados_no_validos_paran_la_web(self):
        for priv, msg in (({"pedidos_anios": 4}, "pedidos_anios"), ({"contacto_meses": 0}, "contacto_meses"),
                          ({"encargados": [{"servicio": "nube", "nombre": "X", "pais": "España"}]}, "servicio"),
                          ({"encargados": [{"servicio": "otro", "nombre": "X", "pais": "España", "dominios": ["https://x.com"]}]}, "dominios")):
            code, out = self.site(priv).build()
            self.assertNotEqual(code, 0, priv)
            self.assertIn(msg, out)

    def test_informacion_basica_junto_al_formulario_de_contacto_y_al_de_compra(self):
        s = self.built(self.site({"contacto_meses": 9, "encargados": COMPLETE}, catalog=SHOP))
        form = re.search(r'<form class="contact-form".*?</form>', s.read("contacto/index.html"), re.S).group(0)
        info = re.search(r'class="meta small form-info">(.*?)</p>', form).group(1)
        for part in ("Responsable: Panadería La Espiga", "Finalidad: contestar tu mensaje", "Base: tu consentimiento", "9 meses", 'href="/privacidad/"'):
            self.assertIn(part, info)
        buy = re.search(r'<form class="buy".*?</form>', s.read("productos/hogaza/index.html"), re.S).group(0)
        self.assertRegex(buy, r'form-info">Responsable: .*Finalidad: gestionar tu pedido.*href="/privacidad/"')

    def test_check_rechaza_google_fonts_videos_y_recursos_de_terceros(self):
        cases = [
            ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter">', "", "Google Fonts"),
            ('<iframe src="https://www.youtube.com/embed/abc123" title="Vídeo"></iframe>', "", "recurso de terceros sin consentimiento <iframe>"),
            ('<img src="https://cdn.imagenes.example/foto.webp" alt="Foto del obrador">', "", "recurso de terceros sin consentimiento <img>"),
            ("", '@import url("https://fonts.googleapis.com/css2?family=Inter");', "hoja de estilos"),
            ('<script src="https://cdn.otro.example/x.js"></script>', "", "recurso de terceros sin consentimiento <script>"),
        ]
        for html_, css, msg in cases:
            s = self.built(self.site({"encargados": COMPLETE}, page_html=html_, css=css))
            code, out = s.check()
            self.assertNotEqual(code, 0, f"{html_ or css}\n{out}")
            self.assertIn(msg, out)

    def test_check_deja_lo_propio_y_lo_declarado(self):
        enc = COMPLETE + [{"servicio": "otro", "nombre": "CDN de imágenes", "pais": "Alemania", "dominios": ["cdn.imagenes.example"]}]
        s = self.built(self.site({"encargados": enc}, page_html='<img src="https://cdn.imagenes.example/foto.webp" alt="Foto del obrador">\n\n'
                                                                  '<img src="https://www.ejemplo-cliente.es/img/logo.svg" alt="Logo">'))
        code, out = s.check()
        self.assertNotIn("recurso de terceros", out)
        self.assertEqual(code, 0, out)

    def test_entrega_sin_encargados_o_sin_el_de_un_servicio_activo_falla(self):
        s = self.built(self.site({"encargados": []}))
        code, out = s.check()
        self.assertIn("falta privacidad.encargados", out)
        r = __import__("subprocess").run([__import__("sys").executable, "tools/check.py", "--release"], cwd=s.dir, capture_output=True, text=True)
        self.assertIn("ERROR: site.json: falta privacidad.encargados", r.stdout)
        shop = self.built(self.site({"encargados": [e for e in COMPLETE if e["servicio"] != "pagos"]}, catalog=SHOP))
        code, out = shop.check()
        self.assertIn("sin el servicio «pagos»", out)


if __name__ == "__main__":
    unittest.main()
