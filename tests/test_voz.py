"""Asistente al teléfono (skill agente-voz-cliente, plantilla-bot > voz): aviso junto al teléfono y privacidad.

Protecciones con test: sin `asistente_voz` nada cambia; activo, el contacto avisa de que puede atender una IA y cómo pedir una persona;
la privacidad dice que no se graba, cuánto se guardan las transcripciones, para qué se usa el número y la transferencia; sin garantía
de transferencia ni encargado «telefonia» no se puede entregar; activo sin teléfono o con un plazo raro, la web no se genera.
"""
import subprocess
import sys
import unittest

from tests.test_build import PRODUCTS, Site

ENC = [{"servicio": "alojamiento", "nombre": "Proveedor", "pais": "España"}, {"servicio": "email", "nombre": "Correo", "pais": "España"}]
TWILIO = {"servicio": "telefonia", "nombre": "Twilio Ireland Limited", "pais": "Irlanda"}


class AsistenteVoz(unittest.TestCase):
    def setUp(self):
        self.sites = []

    def tearDown(self):
        for s in self.sites:
            s.cleanup()

    def site(self, **cfg) -> Site:
        s = Site(products=PRODUCTS, **cfg)
        self.sites.append(s)
        return s

    def release(self, s: Site) -> str:
        r = subprocess.run([sys.executable, "-B", "tools/check.py", "--release"], cwd=s.dir, capture_output=True, text=True)
        return r.stdout + r.stderr

    def test_sin_asistente_nada_cambia(self):
        s = self.site()
        self.assertEqual(s.build()[0], 0)
        self.assertNotIn("phone-ai", s.read("contacto/index.html"))
        self.assertNotIn("Asistente telefónico", s.read("privacidad/index.html"))
        self.assertNotIn("telefonía del asistente", s.read("privacidad/index.html"))

    def test_contacto_y_privacidad(self):
        s = self.site(asistente_voz={"activo": True, "transferencia": "cláusulas contractuales tipo de la Comisión Europea"},
                      privacidad={"encargados": ENC + [TWILIO]})
        code, out = s.build()
        self.assertEqual(code, 0, out)
        contacto = s.read("contacto/index.html")
        self.assertRegex(contacto, r'<a href="tel:[^"]+">[^<]+</a></dd><dd class="phone-ai">Puede atenderte un asistente automático con IA: di «persona» o pulsa 0')
        priv = s.read("privacidad/index.html")
        self.assertIn("<strong>Asistente telefónico.</strong>", priv)
        self.assertIn("La llamada no se graba y las transcripciones no se guardan una vez terminada la llamada", priv)
        self.assertIn("diciendo «persona» o pulsando 0", priv)
        self.assertIn("devolverte la llamada si nos lo pides y lo confirmas", priv)
        self.assertIn("transferencia internacional de datos: cláusulas contractuales tipo de la Comisión Europea", priv)
        self.assertIn("telefonía del asistente telefónico (llamadas, transcripción y voz) (Twilio Ireland Limited, Irlanda)", priv)
        en = s.read("en/privacy/index.html")
        self.assertIn("<strong>Phone assistant.</strong>", en)
        self.assertIn("Calls are not recorded", en)
        self.assertIn("phone-ai", s.read("en/contact/index.html"))
        rel = self.release(s)
        self.assertNotIn("«telefonia»", rel)
        self.assertNotIn("transferencia internacional según los contratos", rel)

    def test_conservacion_igual_que_el_servidor(self):
        s = self.site(asistente_voz={"activo": True, "conservacion_dias": 30, "transferencia": "x"})
        self.assertEqual(s.build()[0], 0)
        self.assertIn("las transcripciones se conservan de forma anonimizada durante 30 días", s.read("privacidad/index.html"))
        for bad in (91, -1, "30"):
            s2 = self.site(asistente_voz={"activo": True, "conservacion_dias": bad})
            code, out = s2.build()
            self.assertNotEqual(code, 0, bad)
            self.assertIn("asistente_voz.conservacion_dias", out)

    def test_sin_garantia_o_sin_encargado_no_se_entrega(self):
        s = self.site(asistente_voz={"activo": True}, privacidad={"encargados": ENC + [TWILIO]})
        self.assertEqual(s.build()[0], 0)
        self.assertIn("[CONFIRMAR: garantía de la transferencia internacional según los contratos de la plataforma de telefonía", s.read("privacidad/index.html"))
        self.assertIn("CONFIRMAR", self.release(s))
        # La del chat sirve si es el mismo proveedor de IA.
        s2 = self.site(asistente_voz={"activo": True}, chatbot={"script": "", "bot": "", "transferencia": "Marco de Privacidad de Datos UE-EE. UU."})
        self.assertEqual(s2.build()[0], 0)
        self.assertIn("transferencia internacional de datos: Marco de Privacidad de Datos UE-EE. UU.", s2.read("privacidad/index.html"))
        s3 = self.site(asistente_voz={"activo": True, "transferencia": "x"}, privacidad={"encargados": ENC})
        self.assertEqual(s3.build()[0], 0)
        self.assertIn("sin el servicio «telefonia»", self.release(s3))

    def test_activo_sin_telefono_no_se_genera(self):
        s = self.site(asistente_voz={"activo": True})
        import json
        d = json.loads((s.dir / "site.json").read_text(encoding="utf-8"))
        d["company"]["phone"] = ""
        (s.dir / "site.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        code, out = s.build()
        self.assertNotEqual(code, 0)
        self.assertIn("asistente_voz.activo sin company.phone", out)


if __name__ == "__main__":
    unittest.main()
