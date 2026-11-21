"""check.py --release no deja publicar con imágenes provisionales ni con el dominio de ejemplo, aunque el texto visible esté limpio.

Antes solo se miraba el texto visible: el `alt` («Foto del cliente pendiente…»), el nombre del archivo provisional y el `site_url`
de ejemplo (canonical, sitemap, Open Graph) pasaban sin aviso."""
import shutil
import subprocess
import sys
import unittest

from tests.test_build import Site

LIMPIO = {"legal_name": "Cliente Real S.L.", "cif": "B12345678", "address": "Calle Real 2, 18300 Loja (Granada)",
          "email": "hola@cliente-real.es", "phone": "+34 652 00 00 01", "registry": "", "social": {}}
ACC = {"estado": "total", "fecha_evaluacion": "2026-11-18", "metodo": "axe-core y revisión manual", "problemas": []}
ENC = {"encargados": [{"servicio": "alojamiento", "nombre": "Alojador S.L.", "pais": "España"}], "contacto_meses": 12, "pedidos_anios": 6}


def sitio(site_url="https://www.cliente-real.es", img="foto.svg", alt="Baño alicatado en blanco"):
    s = Site(site_url=site_url, languages=["es"], company=LIMPIO, accesibilidad=ACC, privacidad=ENC,
             contact_form={"endpoint": ""})
    shutil.rmtree(s.dir / "content")
    es = s.dir / "content" / "es"
    es.mkdir(parents=True)
    (s.dir / "static" / "img" / img).write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 4 3" width="4" height="3"/>')
    (es / "home.md").write_text(
        "---\nkey: home\ntitle: Inicio\ndescription: Alicatados y solados en Loja: pide presupuesto por teléfono o WhatsApp.\n---\n\n"
        f":::hero\n# Alicatados en Loja\n\nTexto propio.\n\n[Contacto](@contacto)\n\n![{alt}](/img/{img})\n:::\n", encoding="utf-8")
    (es / "contacto.md").write_text("---\nkey: contacto\ntitle: Contacto\nnav: 10\ndescription: Llama o escribe para pedir presupuesto.\n---\n\n"
                                    ":::contact\nLlámanos.\n:::\n", encoding="utf-8")
    return s


def release(s):
    r = subprocess.run([sys.executable, "-B", "tools/check.py", "--release"], cwd=s.dir, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


class Relleno(unittest.TestCase):
    def run_case(self, **kw):
        s = sitio(**kw)
        self.addCleanup(s.cleanup)
        code, out = s.build()
        self.assertEqual(code, 0, out)
        return release(s)

    def test_sitio_limpio_se_puede_publicar(self):
        code, out = self.run_case()
        self.assertNotIn("relleno", out)
        self.assertNotIn("site_url", out)

    def test_alt_de_foto_pendiente_bloquea(self):
        code, out = self.run_case(alt="Foto del cliente pendiente: baño alicatado")
        self.assertNotEqual(code, 0)
        self.assertIn("«Foto del cliente»", out)

    def test_imagen_provisional_bloquea_aunque_el_alt_este_bien(self):
        code, out = self.run_case(img="portada-provisional.svg")
        self.assertNotEqual(code, 0)
        self.assertIn("imagen provisional", out)

    def test_dominio_de_ejemplo_bloquea(self):
        code, out = self.run_case(site_url="https://www.ejemplo-cliente.es")
        self.assertNotEqual(code, 0)
        self.assertIn("site.json: site_url", out)


if __name__ == "__main__":
    unittest.main()
